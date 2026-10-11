"""Validator agreement -- the consensus-safety argument for resolving over live web.

Leader and validators fetch the evidence independently and may see different
bytes. The contract therefore agrees only on the distilled boolean verdict, not
on the page or the model's wording. These tests re-run the captured validator
against the same and against divergent evidence to prove exactly that boundary.
"""

import json

import pytest

from conftest import (
    AFTER_DEADLINE,
    set_now,
    EVIDENCE_BROKEN,
    EVIDENCE_KEPT,
    JUDGE_PROMPT,
    RENDER_URL,
    judgement,
)


def _resolve_kept(funded, direct_vm):
    set_now(direct_vm, AFTER_DEADLINE)
    direct_vm.mock_web(RENDER_URL, {"status": 200, "body": EVIDENCE_KEPT})
    direct_vm.mock_llm(JUDGE_PROMPT, judgement(True))
    funded.resolve()


def test_validator_agrees_on_identical_evidence(funded, direct_vm):
    _resolve_kept(funded, direct_vm)
    assert direct_vm.run_validator() is True


def test_validator_agrees_when_wording_differs_but_verdict_matches(funded, direct_vm):
    """A different page and a differently worded reason still agree, as long as
    the boolean verdict matches -- this is what makes resolution survive the
    independent-fetch reality instead of failing on every run."""
    _resolve_kept(funded, direct_vm)
    direct_vm.clear_mocks()
    direct_vm.mock_web(RENDER_URL, {"status": 200, "body": "v1.0 is now live! see notes."})
    direct_vm.mock_llm(JUDGE_PROMPT, judgement(True, reason="phrased entirely differently"))
    assert direct_vm.run_validator() is True


def test_validator_rejects_a_flipped_verdict(funded, direct_vm):
    """If a second node judges the opposite, it must reject -- no tolerance, the
    verdict is a single boolean about release-or-not."""
    _resolve_kept(funded, direct_vm)
    direct_vm.clear_mocks()
    direct_vm.mock_web(RENDER_URL, {"status": 200, "body": EVIDENCE_BROKEN})
    direct_vm.mock_llm(JUDGE_PROMPT, judgement(False))
    assert direct_vm.run_validator() is False


def test_validator_rejects_a_malformed_leader_result(funded, direct_vm):
    _resolve_kept(funded, direct_vm)
    # Leader returned something that is not the agreed JSON shape.
    assert direct_vm.run_validator(leader_result="not json") is False


def test_validator_rejects_a_leader_error(funded, direct_vm):
    _resolve_kept(funded, direct_vm)
    assert direct_vm.run_validator(leader_error=RuntimeError("[LLM_ERROR] boom")) is False
