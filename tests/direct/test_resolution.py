"""Resolution: the deadline gate, the fail-closed verdict rules, idempotency, and
the credit/withdraw flow including the native transfer.

Resolution is the heart of the contract. KEPT (stake back to the author) is the
privileged outcome, reachable only on a clear agreed "satisfied". Everything the
model cannot clearly confirm -- a BROKEN judgement, an empty/unreachable page, a
malformed response -- credits the beneficiary. Validator *disagreement* is a
separate thing: it is not a verdict at all, it fails consensus and changes no
state, so the bond can be resolved again later.
"""

import json

import pytest

from conftest import (
    AFTER_DEADLINE,
    set_now,
    BENEFICIARY,
    EVIDENCE_BROKEN,
    EVIDENCE_KEPT,
    JUDGE_PROMPT,
    RENDER_URL,
    judgement,
)


def _mock(direct_vm, page, satisfied):
    direct_vm.mock_web(RENDER_URL, {"status": 200, "body": page})
    direct_vm.mock_llm(JUDGE_PROMPT, judgement(satisfied))


# --------------------------------------------------------------- deadline gate
def test_cannot_resolve_before_deadline(funded, direct_vm):
    _mock(direct_vm, EVIDENCE_KEPT, True)
    with direct_vm.expect_revert("too early"):
        funded.resolve()


def test_cannot_resolve_an_unfunded_bond(bond, direct_vm):
    set_now(direct_vm, AFTER_DEADLINE)
    with direct_vm.expect_revert("nothing funded"):
        bond.resolve()


# ----------------------------------------------------------- the KEPT path
def test_kept_credits_the_owner(funded, direct_vm, direct_owner):
    set_now(direct_vm, AFTER_DEADLINE)
    _mock(direct_vm, EVIDENCE_KEPT, True)
    assert funded.resolve() == "KEPT"

    status = json.loads(funded.status_json())
    assert status["status"] == "RESOLVED"
    assert status["verdict"] == "KEPT"
    assert status["held"] == 0
    assert funded.claimable_of(direct_owner.as_hex) == 1000
    assert funded.claimable_of(BENEFICIARY) == 0


# ----------------------------------------------------------- the BROKEN path
def test_broken_credits_the_beneficiary(funded, direct_vm, direct_owner):
    set_now(direct_vm, AFTER_DEADLINE)
    _mock(direct_vm, EVIDENCE_BROKEN, False)
    assert funded.resolve() == "BROKEN"

    assert funded.claimable_of(BENEFICIARY) == 1000
    assert funded.claimable_of(direct_owner.as_hex) == 0


# -------------------------------------------------------- fail-closed rules
def test_empty_page_fails_closed_to_broken(funded, direct_vm):
    """An unreachable/empty page can demonstrate nothing. It must never release
    to the author, and it must not even consult the model."""
    set_now(direct_vm, AFTER_DEADLINE)
    direct_vm.mock_web(RENDER_URL, {"status": 200, "body": ""})
    # Deliberately NO llm mock: if the contract tried to ask the model about an
    # empty page, this test would error on a missing mock. It must not.
    assert funded.resolve() == "BROKEN"
    assert funded.claimable_of(BENEFICIARY) == 1000


def test_whitespace_only_page_fails_closed(funded, direct_vm):
    set_now(direct_vm, AFTER_DEADLINE)
    direct_vm.mock_web(RENDER_URL, {"status": 200, "body": "   \n\t  "})
    assert funded.resolve() == "BROKEN"
    assert funded.claimable_of(BENEFICIARY) == 1000


def test_model_omitting_satisfied_field_disagrees_not_releases(funded, direct_vm):
    """A malformed model answer must force consensus failure (an [LLM_ERROR]),
    never a silent pass. In direct mode the leader raising surfaces as a revert;
    on a live network it rotates the leader. Either way no verdict is recorded."""
    set_now(direct_vm, AFTER_DEADLINE)
    direct_vm.mock_web(RENDER_URL, {"status": 200, "body": EVIDENCE_KEPT})
    direct_vm.mock_llm(JUDGE_PROMPT, json.dumps({"reason": "no verdict field"}))
    with direct_vm.expect_revert():
        funded.resolve()
    # Nothing settled: still FUNDED, nothing credited.
    assert json.loads(funded.status_json())["status"] == "FUNDED"
    assert funded.claimable_of(BENEFICIARY) == 0


# ------------------------------------------------------------- idempotency
def test_resolving_twice_is_a_no_op(funded, direct_vm, direct_owner):
    set_now(direct_vm, AFTER_DEADLINE)
    _mock(direct_vm, EVIDENCE_KEPT, True)
    assert funded.resolve() == "KEPT"

    direct_vm.clear_mocks()  # a second consensus round would need mocks; it must not run one
    assert funded.resolve() == "KEPT"
    assert funded.claimable_of(direct_owner.as_hex) == 1000  # not doubled


# ----------------------------------------------------- credit + withdraw flow
def test_owner_withdraws_after_kept(funded, direct_vm, direct_owner):
    set_now(direct_vm, AFTER_DEADLINE)
    _mock(direct_vm, EVIDENCE_KEPT, True)
    funded.resolve()

    assert funded.withdraw() == 1000
    assert funded.claimable_of(direct_owner.as_hex) == 0
    # second withdraw has nothing left
    with direct_vm.expect_revert("nothing to withdraw"):
        funded.withdraw()


def test_beneficiary_withdraws_after_broken(funded, direct_vm, direct_bob):
    set_now(direct_vm, AFTER_DEADLINE)
    _mock(direct_vm, EVIDENCE_BROKEN, False)
    funded.resolve()

    # The beneficiary address in conftest; drive withdraw as that account.
    from genlayer.py.types import Address
    direct_vm.sender = Address(BENEFICIARY)
    assert funded.withdraw() == 1000
    assert funded.claimable_of(BENEFICIARY) == 0


def test_withdraw_with_nothing_owed_reverts(funded, direct_vm, direct_bob):
    set_now(direct_vm, AFTER_DEADLINE)
    _mock(direct_vm, EVIDENCE_KEPT, True)
    funded.resolve()  # credits the owner
    direct_vm.sender = direct_bob  # a stranger
    with direct_vm.expect_revert("nothing to withdraw"):
        funded.withdraw()
