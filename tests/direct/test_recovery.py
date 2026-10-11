"""Recovery backstop: the deterministic escape hatch for a stake that resolve()
never finalized.

Recovery is reachable ONLY while still FUNDED and once deadline + grace has
elapsed. A finalized verdict (RESOLVED) forecloses it; recovery (RECOVERED)
forecloses resolution. The stake splits 50/50, odd remainder to the beneficiary.

These tests assert the deterministic state machine and the ledger math. They do
NOT need the model (recover() runs no nondet block). The clock is advanced with
set_now() because the direct harness does not refresh the contract's datetime on
a bare warp after deploy.

NOTE on scope: recovery bounds, but does not eliminate, griefing -- a party who
can force non-resolution still captures half. That is a property of the design,
not something a test can "pass away"; it is documented, not asserted here.
"""

import json

import pytest

from conftest import (
    AFTER_DEADLINE,
    AFTER_RECOVERY,
    BEFORE_RECOVERY,
    BENEFICIARY,
    EVIDENCE_KEPT,
    JUDGE_PROMPT,
    RENDER_URL,
    judgement,
    set_now,
)


# ----------------------------------------------------------- availability gate
def test_recover_before_grace_elapses_reverts(funded, direct_vm):
    """Past the deadline but inside the grace window: not yet recoverable."""
    set_now(direct_vm, BEFORE_RECOVERY)
    with direct_vm.expect_revert("recovery grace period has not elapsed"):
        funded.recover()
    assert json.loads(funded.status_json())["status"] == "FUNDED"


def test_recover_on_unfunded_bond_reverts(bond, direct_vm):
    """OPEN (never funded) -> nothing to recover."""
    set_now(direct_vm, AFTER_RECOVERY)
    with direct_vm.expect_revert("not recoverable"):
        bond.recover()


# ------------------------------------------------------------- the split path
def test_recover_after_grace_splits_50_50(funded, direct_vm, direct_owner):
    set_now(direct_vm, AFTER_RECOVERY)
    assert funded.recover() == "RECOVERED"

    status = json.loads(funded.status_json())
    assert status["status"] == "RECOVERED"
    assert status["verdict"] == "RECOVERED"
    assert status["held"] == 0
    # 1000 splits evenly.
    assert funded.claimable_of(direct_owner.as_hex) == 500
    assert funded.claimable_of(BENEFICIARY) == 500


def test_odd_stake_remainder_goes_to_beneficiary(bond, direct_vm, direct_owner):
    # Fund an odd amount so the split has a remainder.
    direct_vm.value = 1001
    bond.fund()
    direct_vm.value = 0
    set_now(direct_vm, AFTER_RECOVERY)
    assert bond.recover() == "RECOVERED"
    assert bond.claimable_of(direct_owner.as_hex) == 500       # floor
    assert bond.claimable_of(BENEFICIARY) == 501               # remainder


# ------------------------------------------- mutual exclusion with resolution
def test_recovery_cannot_override_a_finalized_verdict(funded, direct_vm):
    """A resolved bond is terminal: recover() must refuse even after the grace
    window, so a valid verdict can never be undone."""
    set_now(direct_vm, AFTER_DEADLINE)
    direct_vm.mock_web(RENDER_URL, {"status": 200, "body": EVIDENCE_KEPT})
    direct_vm.mock_llm(JUDGE_PROMPT, judgement(True))
    assert funded.resolve() == "KEPT"

    set_now(direct_vm, AFTER_RECOVERY)
    with direct_vm.expect_revert("not recoverable"):
        funded.recover()
    # Verdict and credit are unchanged.
    assert json.loads(funded.status_json())["verdict"] == "KEPT"


def test_resolution_cannot_override_a_recovery(funded, direct_vm):
    """A recovered bond is terminal: resolve() must refuse."""
    set_now(direct_vm, AFTER_RECOVERY)
    assert funded.recover() == "RECOVERED"

    # Even with a would-be KEPT judgement available, resolve must not run.
    direct_vm.mock_web(RENDER_URL, {"status": 200, "body": EVIDENCE_KEPT})
    direct_vm.mock_llm(JUDGE_PROMPT, judgement(True))
    with direct_vm.expect_revert("nothing funded to resolve"):
        funded.resolve()
    assert json.loads(funded.status_json())["verdict"] == "RECOVERED"


# ------------------------------------------------------- no double recovery
def test_double_recover_is_rejected_and_credits_once(funded, direct_vm, direct_owner):
    set_now(direct_vm, AFTER_RECOVERY)
    funded.recover()
    with direct_vm.expect_revert("not recoverable"):
        funded.recover()
    # Credited exactly once.
    assert funded.claimable_of(direct_owner.as_hex) == 500
    assert funded.claimable_of(BENEFICIARY) == 500


# ------------------------------------------------- withdrawal after recovery
def test_both_parties_withdraw_their_halves_once(funded, direct_vm, direct_owner):
    set_now(direct_vm, AFTER_RECOVERY)
    funded.recover()

    # Owner pulls their half.
    assert funded.withdraw() == 500
    assert funded.claimable_of(direct_owner.as_hex) == 0
    with direct_vm.expect_revert("nothing to withdraw"):
        funded.withdraw()

    # Beneficiary pulls their half.
    from genlayer.py.types import Address
    direct_vm.sender = Address(BENEFICIARY)
    assert funded.withdraw() == 500
    assert funded.claimable_of(BENEFICIARY) == 0
    with direct_vm.expect_revert("nothing to withdraw"):
        funded.withdraw()
