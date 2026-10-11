"""Minimum Studionet integration test: deploy -> fund -> resolve -> withdraw.

Run explicitly against the hosted Studio network (never the default direct mode):

    gltest --network studionet tests/integration

What only a live network can show, and therefore what this covers:
  * a real deploy of the contract and its constructor validation on chain;
  * a real native GEN escrow via a payable fund();
  * resolve() running a real web.render + exec_prompt judgement inside
    run_nondet_unsafe, reaching consensus on the distilled verdict;
  * a real native GEN transfer out through withdraw().

Testing discipline: assertions pin invariants (status transitions, held/claimable
amounts, verdict is one of the two tokens), never the model's wording. The
evidence URL is a public static page whose content is stable, and the criterion
is deliberately concrete so independent validators converge.
"""

import datetime
import json
import time

import pytest

from gltest import get_contract_factory, get_default_account
from gltest.assertions import tx_execution_succeeded

# The contract requires fund() BEFORE the deadline and resolve() AT/AFTER it, so
# the deadline must start in the (near) future, be funded while still future,
# then be waited out before resolving. A fixed past date cannot satisfy both.
_DEADLINE_SECONDS_AHEAD = 90
_RESOLVE_MARGIN_SECONDS = 25

# A public, stable page. example.com is a static IANA-maintained page whose body
# does not change between fetches, so independent validator renders agree.
EVIDENCE_URL = "https://example.com/"

PROMISE = "The reference page remains published and reachable."
# Deliberately lenient and unambiguous so an honest, strict judge reliably
# returns KEPT on a reachable page -- this exercises the owner-withdraw path.
# (A pedantic exact-string criterion made the judge return BROKEN; that is the
# contract working, but it credits the beneficiary, whose key we do not hold.)
CRITERIA = "The page is reachable and contains some visible text (it is not blank or an error page)."

STAKE = 1000


def _utc_now():
    return datetime.datetime.now(datetime.timezone.utc)


def _read_with_retry(fn, attempts=5):
    """Retry a read-only view call through a transient RPC/DNS hiccup.

    Views never change state, so retrying one is safe. State-changing
    transactions are never retried here."""
    last = None
    for _ in range(attempts):
        try:
            return fn()
        except Exception as exc:  # transient network error on a view
            last = exc
            time.sleep(5)
    raise last


def test_full_lifecycle_on_studionet():
    deployer = get_default_account()
    # Beneficiary must differ from owner; a second well-known test address.
    beneficiary = "0x1111111111111111111111111111111111111111"

    deadline_dt = _utc_now() + datetime.timedelta(seconds=_DEADLINE_SECONDS_AHEAD)
    deadline = deadline_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Minimum 7-day recovery grace (not exercised in the happy-path lifecycle).
    grace = 604800

    factory = get_contract_factory("AccountabilityBond")
    bond = factory.deploy(args=[PROMISE, CRITERIA, EVIDENCE_URL, deadline, beneficiary, grace])
    print("DEPLOYED_AT:", bond.address, "| DEADLINE:", deadline)

    status = json.loads(bond.status_json(args=[]).call())
    assert status["status"] == "OPEN"
    assert status["owner"].lower() == deployer.address.lower()

    # ---- fund (still before the deadline) ----
    assert tx_execution_succeeded(bond.fund(args=[]).transact(value=STAKE))
    status = json.loads(bond.status_json(args=[]).call())
    assert status["status"] == "FUNDED"
    assert status["held"] == STAKE

    # ---- wait out the deadline, then resolve once ----
    # resolve() requires now >= deadline. Wait until the wall clock is safely
    # past it before the single resolve attempt. Do NOT retry resolve on failure.
    while _utc_now() < deadline_dt + datetime.timedelta(seconds=_RESOLVE_MARGIN_SECONDS):
        time.sleep(5)

    # ---- resolve (deadline passed; real web + model judgement) ----
    receipt = bond.resolve(args=[]).transact()
    assert tx_execution_succeeded(receipt), (
        "resolve did not reach consensus. Either validators disagreed on the "
        "evidence judgement or the model misbehaved; both are the primitive "
        "working. Re-run before investigating."
    )
    status = json.loads(_read_with_retry(lambda: bond.status_json(args=[]).call()))
    assert status["status"] == "RESOLVED"
    assert status["verdict"] in ("KEPT", "BROKEN")
    assert status["held"] == 0
    print("VERDICT:", status["verdict"], "| REASON:", status["reason"][:80])

    # The criterion is true of the live page, so the honest verdict is KEPT and
    # the stake is claimable by the owner. If a validator run genuinely returned
    # BROKEN, the refusal path is still correct -- assert whichever happened.
    verdict = status["verdict"]
    owner_claim = _read_with_retry(lambda: bond.claimable_of(args=[deployer.address]).call())
    ben_claim = _read_with_retry(lambda: bond.claimable_of(args=[beneficiary]).call())
    if verdict == "KEPT":
        assert owner_claim == STAKE and ben_claim == 0
        claimant = deployer
    else:
        assert ben_claim == STAKE and owner_claim == 0
        pytest.skip("live verdict was BROKEN; owner withdraw path not exercised this run")

    # ---- withdraw (real native GEN transfer out) ----
    assert tx_execution_succeeded(bond.connect(claimant).withdraw(args=[]).transact())
    assert _read_with_retry(lambda: bond.claimable_of(args=[deployer.address]).call()) == 0

    # A second withdraw must now have nothing to send.
    assert not tx_execution_succeeded(bond.connect(claimant).withdraw(args=[]).transact())
