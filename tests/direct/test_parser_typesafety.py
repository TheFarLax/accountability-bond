"""Regression tests for the 'satisfied' type-safety fix (judgment parser).

The bug: `kept = bool(data.get("satisfied"))` coerced the model's value, so the
string "false", the number 1, a non-empty list, etc. would become True and could
release funds. The fix requires `satisfied` to be an ACTUAL JSON boolean; any
other type is routed through the existing [LLM_ERROR] malformed path (fail
closed), never a KEPT payout.

These are MOCKED-model tests: they feed the parser specific JSON values and
assert the contract's handling. They cover both the production contract
(via resolve()) and the JudgeProbe (via judge_evidence()), since the parser is
copied into both.
"""

import json

import pytest

from conftest import AFTER_DEADLINE, BENEFICIARY, JUDGE_PROMPT, RENDER_URL, set_now, SDK_VERSION
from pathlib import Path

CONTRACTS = Path(__file__).parent.parent.parent / "contracts"
PROMISE = "I will publish version 1.0 by the deadline."
CRITERIA = "The evidence states that version 1.0 or later has been released."
EVIDENCE = "Some non-empty evidence text that the model will judge."

# Raw JSON strings for the "satisfied" field. json.dumps-free so we control the
# exact wire form the model is mocked to return.
ACCEPTED = {
    "json_true": '{"satisfied": true, "reason": "r"}',
    "json_false": '{"satisfied": false, "reason": "r"}',
}
REJECTED = {
    "string_true": '{"satisfied": "true", "reason": "r"}',
    "string_false": '{"satisfied": "false", "reason": "r"}',
    "number_zero": '{"satisfied": 0, "reason": "r"}',
    "number_one": '{"satisfied": 1, "reason": "r"}',
    "object": '{"satisfied": {}, "reason": "r"}',
    "array": '{"satisfied": [], "reason": "r"}',
    "null": '{"satisfied": null, "reason": "r"}',
}


# ===================================================== production contract
def _resolve_with(funded, direct_vm, llm_json):
    set_now(direct_vm, AFTER_DEADLINE)
    direct_vm.mock_web(RENDER_URL, {"status": 200, "body": EVIDENCE})
    direct_vm.mock_llm(JUDGE_PROMPT, llm_json)


def test_prod_json_true_is_accepted_as_kept(funded, direct_vm, direct_owner):
    _resolve_with(funded, direct_vm, ACCEPTED["json_true"])
    assert funded.resolve() == "KEPT"
    assert funded.claimable_of(direct_owner.as_hex) == 1000


def test_prod_json_false_is_accepted_as_broken(funded, direct_vm):
    _resolve_with(funded, direct_vm, ACCEPTED["json_false"])
    assert funded.resolve() == "BROKEN"
    assert funded.claimable_of(BENEFICIARY) == 1000


@pytest.mark.parametrize("label", list(REJECTED.keys()))
def test_prod_non_boolean_satisfied_is_rejected_not_kept(funded, direct_vm, label):
    """A non-boolean 'satisfied' must force the malformed path (revert in direct
    mode / rotation live), never a KEPT payout and never a silent settlement."""
    _resolve_with(funded, direct_vm, REJECTED[label])
    with direct_vm.expect_revert():
        funded.resolve()
    # Nothing settled: still FUNDED, nothing credited to either party.
    status = json.loads(funded.status_json())
    assert status["status"] == "FUNDED"
    assert funded.claimable_of(BENEFICIARY) == 0


# ============================================================ JudgeProbe
@pytest.fixture
def probe(direct_vm, direct_deploy):
    return direct_deploy(str(CONTRACTS / "judge_probe.py"), sdk_version=SDK_VERSION)


def test_probe_json_true_accepted(probe, direct_vm):
    direct_vm.mock_llm(JUDGE_PROMPT, ACCEPTED["json_true"])
    assert probe.judge_evidence(PROMISE, CRITERIA, EVIDENCE) == "KEPT"


def test_probe_json_false_accepted(probe, direct_vm):
    direct_vm.mock_llm(JUDGE_PROMPT, ACCEPTED["json_false"])
    assert probe.judge_evidence(PROMISE, CRITERIA, EVIDENCE) == "BROKEN"


@pytest.mark.parametrize("label", list(REJECTED.keys()))
def test_probe_non_boolean_satisfied_rejected(probe, direct_vm, label):
    direct_vm.mock_llm(JUDGE_PROMPT, REJECTED[label])
    with direct_vm.expect_revert():
        probe.judge_evidence(PROMISE, CRITERIA, EVIDENCE)


# ------------------------------------------- existing malformed cases still hold
def test_prod_missing_satisfied_still_rejected(funded, direct_vm):
    _resolve_with(funded, direct_vm, '{"reason": "no verdict field"}')
    with direct_vm.expect_revert():
        funded.resolve()
    assert json.loads(funded.status_json())["status"] == "FUNDED"


def test_probe_missing_satisfied_still_rejected(probe, direct_vm):
    direct_vm.mock_llm(JUDGE_PROMPT, '{"reason": "no verdict field"}')
    with direct_vm.expect_revert():
        probe.judge_evidence(PROMISE, CRITERIA, EVIDENCE)
