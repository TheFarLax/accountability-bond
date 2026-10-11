"""LIVE focused recovery check on Studionet -- the recovery backstop only.

    gltest --network studionet tests/integration/test_recovery_live.py

TIME CONTROL (read before running). The 7-day grace cannot be waited out in wall
time, and the direct-mode `set_now` helper does NOT affect the live network --
it only patches the in-process VM. On Studionet the contract's clock is
`gl.message_raw["datetime"]`, which gltest sets PER TRANSACTION via
`transaction_context={"genvm_datetime": "<ISO>"}` (passed through to
`SimConfig.genvm_datetime`). So each fund/recover/resolve/withdraw call below
supplies its own genvm_datetime, and that is the ONLY time manipulation used:
no sleeping, no real-clock dependence.

Timeline used (all UTC):
    deadline      D   = 2030-01-01T00:00:00Z
    grace             = 604800s (7 days, the minimum)
    recovery_at   R   = 2030-01-08T00:00:00Z   (= D + grace)
    fund      at  t0  = 2029-12-01T00:00:00Z   (before D)       -> FUNDED
    recover   at  t1  = 2030-01-05T00:00:00Z   (> D, < R)       -> REJECTED
    recover   at  t2  = 2030-01-09T00:00:00Z   (>= R)           -> RECOVERED
    resolve   at  t3  = 2030-01-10T00:00:00Z   (after recovery) -> REJECTED

Each transaction is sent at most once; failures are reported, never retried.

STAKE: an odd 3 wei, so the 50/50 split is owner=1, beneficiary=2 (remainder to
beneficiary). Tiny on purpose -- this is test value on a test network.

BENEFICIARY WITHDRAWAL: exercising the beneficiary's withdraw() needs a second
account that holds gas, which would require extra faucet funding. Unless that is
set up, this test asserts the beneficiary's CLAIMABLE balance (a read) and
exercises only the owner's withdraw(); beneficiary withdrawal is covered in
direct mode. See the module-level BENEFICIARY_ACCOUNT switch.
"""

import json

import pytest

from gltest import get_contract_factory, get_default_account
from gltest.assertions import tx_execution_succeeded, tx_execution_failed

PROMISE = "I will publish version 1.0 of my library by the deadline."
CRITERIA = "The evidence page clearly states that version 1.0 or later was released."
EVIDENCE_URL = "https://example.com/releases"
DEADLINE = "2030-01-01T00:00:00Z"
GRACE = 604800
RECOVERY_AT = "2030-01-08T00:00:00Z"

T_FUND = "2029-12-01T00:00:00Z"
T_RECOVER_EARLY = "2030-01-05T00:00:00Z"
T_RECOVER_OK = "2030-01-09T00:00:00Z"
T_RESOLVE = "2030-01-10T00:00:00Z"

STAKE = 3  # odd, so split is owner=1 / beneficiary=2

# A dummy beneficiary we do NOT hold a key for. Beneficiary withdrawal is not
# exercised live unless a funded second account is provided (would need faucet).
BENEFICIARY = "0x1111111111111111111111111111111111111111"


def _at(ts):
    return {"genvm_datetime": ts}


def test_live_recovery_lifecycle():
    deployer = get_default_account()

    factory = get_contract_factory("AccountabilityBond")
    bond = factory.deploy(args=[PROMISE, CRITERIA, EVIDENCE_URL, DEADLINE, BENEFICIARY, GRACE])
    print("RECOVERY_PROBE_DEPLOYED_AT:", bond.address)

    terms = json.loads(bond.terms(args=[]).call())
    assert terms["recovery_grace_seconds"] == GRACE
    assert terms["recovery_at"] == RECOVERY_AT

    # 1. fund (before deadline)
    r_fund = bond.fund(args=[]).transact(value=STAKE, transaction_context=_at(T_FUND))
    print("TX_FUND:", r_fund.get("hash") if isinstance(r_fund, dict) else None)
    assert tx_execution_succeeded(r_fund), r_fund
    assert json.loads(bond.status_json(args=[]).call())["status"] == "FUNDED"

    # 2. recover BEFORE grace -> must be rejected (still FUNDED, nothing split)
    r_early = bond.recover(args=[]).transact(transaction_context=_at(T_RECOVER_EARLY))
    print("TX_RECOVER_EARLY:", r_early.get("hash") if isinstance(r_early, dict) else None)
    assert tx_execution_failed(r_early), "recover before grace should fail: %s" % r_early
    assert json.loads(bond.status_json(args=[]).call())["status"] == "FUNDED"

    # 3. recover AT/AFTER grace -> RECOVERED, 50/50 split
    r_ok = bond.recover(args=[]).transact(transaction_context=_at(T_RECOVER_OK))
    print("TX_RECOVER_OK:", r_ok.get("hash") if isinstance(r_ok, dict) else None)
    assert tx_execution_succeeded(r_ok), r_ok
    status = json.loads(bond.status_json(args=[]).call())
    assert status["status"] == "RECOVERED"
    assert status["verdict"] == "RECOVERED"
    assert status["held"] == 0
    owner_claim = bond.claimable_of(args=[deployer.address]).call()
    ben_claim = bond.claimable_of(args=[BENEFICIARY]).call()
    print("CLAIMS: owner=%s beneficiary=%s" % (owner_claim, ben_claim))
    assert owner_claim == 1          # floor of 3//2
    assert ben_claim == 2            # remainder to beneficiary

    # 4. resolve AFTER recovery -> must be rejected (terminal)
    r_resolve = bond.resolve(args=[]).transact(transaction_context=_at(T_RESOLVE))
    print("TX_RESOLVE_AFTER:", r_resolve.get("hash") if isinstance(r_resolve, dict) else None)
    assert tx_execution_failed(r_resolve), "resolve after recovery should fail: %s" % r_resolve
    assert json.loads(bond.status_json(args=[]).call())["verdict"] == "RECOVERED"

    # 5. owner withdraws their half once; second withdraw has nothing left
    r_wd = bond.withdraw(args=[]).transact(transaction_context=_at(T_RESOLVE))
    print("TX_WITHDRAW_OWNER:", r_wd.get("hash") if isinstance(r_wd, dict) else None)
    assert tx_execution_succeeded(r_wd), r_wd
    assert bond.claimable_of(args=[deployer.address]).call() == 0

    r_wd2 = bond.withdraw(args=[]).transact(transaction_context=_at(T_RESOLVE))
    print("TX_WITHDRAW_OWNER_2:", r_wd2.get("hash") if isinstance(r_wd2, dict) else None)
    assert tx_execution_failed(r_wd2), "second owner withdraw should fail: %s" % r_wd2

    # Beneficiary still has a claimable balance; withdrawing it live would need a
    # funded second account (extra faucet). Asserted as a read only.
    assert bond.claimable_of(args=[BENEFICIARY]).call() == 2
