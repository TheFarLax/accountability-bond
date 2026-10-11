"""Direct-mode (MOCKED model) tests for JudgeProbe.

IMPORTANT: these mock the model via `direct_vm.mock_llm`, so they prove only that
the probe maps a given model verdict to the right output and fails closed on
empty evidence. They do NOT exercise the real model -- that is the job of
tests/integration/test_judge_probe_live.py, which runs on Studionet. Keep the
two clearly separate.
"""

import json

import pytest

from conftest import SDK_VERSION  # reuse pin
from pathlib import Path

CONTRACTS = Path(__file__).parent.parent.parent / "contracts"
JUDGE_PROMPT = r"verifying whether a public commitment was kept"

PROMISE = "I will publish version 1.0 by the deadline."
CRITERIA = "The evidence states that version 1.0 or later has been released."


@pytest.fixture
def probe(direct_vm, direct_deploy):
    return direct_deploy(str(CONTRACTS / "judge_probe.py"), sdk_version=SDK_VERSION)


def test_mocked_satisfied_maps_to_kept(probe, direct_vm):
    direct_vm.mock_llm(JUDGE_PROMPT, json.dumps({"satisfied": True, "reason": "x"}))
    assert probe.judge_evidence(PROMISE, CRITERIA, "v1.0 released") == "KEPT"


def test_mocked_unsatisfied_maps_to_broken(probe, direct_vm):
    direct_vm.mock_llm(JUDGE_PROMPT, json.dumps({"satisfied": False, "reason": "x"}))
    assert probe.judge_evidence(PROMISE, CRITERIA, "still working on it") == "BROKEN"


def test_empty_evidence_fails_closed_without_model(probe, direct_vm):
    # No llm mock: empty evidence must not reach the model.
    assert probe.judge_evidence(PROMISE, CRITERIA, "   ") == "BROKEN"


def test_malformed_model_output_forces_disagreement(probe, direct_vm):
    direct_vm.mock_llm(JUDGE_PROMPT, json.dumps({"reason": "no verdict"}))
    with direct_vm.expect_revert():
        probe.judge_evidence(PROMISE, CRITERIA, "some evidence")


def test_validator_agrees_on_matching_boolean(probe, direct_vm):
    direct_vm.mock_llm(JUDGE_PROMPT, json.dumps({"satisfied": True, "reason": "a"}))
    probe.judge_evidence(PROMISE, CRITERIA, "v1.0 shipped")
    assert direct_vm.run_validator() is True


def test_validator_rejects_flipped_boolean(probe, direct_vm):
    direct_vm.mock_llm(JUDGE_PROMPT, json.dumps({"satisfied": True, "reason": "a"}))
    probe.judge_evidence(PROMISE, CRITERIA, "v1.0 shipped")
    direct_vm.clear_mocks()
    direct_vm.mock_llm(JUDGE_PROMPT, json.dumps({"satisfied": False, "reason": "b"}))
    assert direct_vm.run_validator() is False
