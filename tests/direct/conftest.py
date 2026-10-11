"""Shared fixtures and the running example bond for the direct-mode suite.

Direct mode is in-process: no network, no model, no consensus. Web and LLM calls
are mocked, and a captured validator can be re-run to simulate a second node
seeing the same or different evidence. The one surface direct mode does NOT
implement is cross-contract calls; this contract makes none, so the whole bond
lifecycle -- including the native transfer in withdraw() -- is exercisable here.
"""

import json
import sys
from pathlib import Path

import pytest

SDK_VERSION = "v0.3.0-rc7"
CONTRACTS = Path(__file__).parent.parent.parent / "contracts"

BENEFICIARY = "0x2222222222222222222222222222222222222222"

PROMISE = "I will publish version 1.0 of my library by the deadline."
CRITERIA = "The evidence page states that version 1.0 (or later) has been released."
EVIDENCE_URL = "https://example.com/releases"
DEADLINE = "2026-06-01T00:00:00Z"

BEFORE_DEADLINE = "2026-01-01T00:00:00Z"
AFTER_DEADLINE = "2026-07-01T00:00:00Z"

# Recovery: a 7-day grace (the minimum). recovery_at = deadline + 7 days.
GRACE_SECONDS = 604800
RECOVERY_AT = "2026-06-08T00:00:00Z"       # DEADLINE (2026-06-01) + 7 days
BEFORE_RECOVERY = "2026-06-07T12:00:00Z"   # past deadline, before grace elapses
AFTER_RECOVERY = "2026-06-09T00:00:00Z"    # grace fully elapsed

# A page the criterion is clearly met on, and one it clearly is not.
EVIDENCE_KEPT = "Changelog: version 1.0 released today. Thanks to all contributors."
EVIDENCE_BROKEN = "Still a work in progress. No release yet, check back later."

JUDGE_PROMPT = r"verifying whether a public commitment was kept"
RENDER_URL = r".*example\.com.*"


def judgement(satisfied, reason="because"):
    return json.dumps({"satisfied": satisfied, "reason": reason})


def set_now(direct_vm, iso):
    """Set the on-chain clock a deployed contract will read.

    `direct_vm.warp()` updates the VM's time, but `gl.message_raw["datetime"]`
    is injected into the already-imported contract module only at deploy time
    and is not refreshed by a later warp. On a live network every transaction
    carries its own datetime, so this is purely a direct-mode harness quirk; we
    bridge it by also updating the live `message_raw` dict. Call this instead of
    `direct_vm.warp()` when the clock must change after deployment."""
    direct_vm.warp(iso)
    gl = sys.modules.get("genlayer.gl")
    if gl is not None and getattr(gl, "message_raw", None) is not None:
        gl.message_raw["datetime"] = iso


@pytest.fixture
def deploy(direct_vm, direct_deploy):
    def _deploy(name, *args):
        return direct_deploy(str(CONTRACTS / name), *args, sdk_version=SDK_VERSION)
    return _deploy


@pytest.fixture
def bond(deploy, direct_vm):
    """A freshly deployed, unfunded bond, with the clock before the deadline."""
    set_now(direct_vm, BEFORE_DEADLINE)
    return deploy(
        "accountability_bond.py",
        PROMISE, CRITERIA, EVIDENCE_URL, DEADLINE, BENEFICIARY, GRACE_SECONDS,
    )


@pytest.fixture
def funded(bond, direct_vm):
    """A bond with 1000 staked, still before the deadline."""
    direct_vm.value = 1000
    bond.fund()
    direct_vm.value = 0
    return bond
