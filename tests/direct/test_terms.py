"""Constructor validation, with the deadline format the focus.

The deadline is the one author-supplied value the contract parses as time, so it
is validated strictly: UTC only, exact 'YYYY-MM-DDTHH:MM:SSZ' shape, real
calendar values. Anything else must be rejected at construction so a bond can
never exist with an ambiguous deadline.
"""

import json

import pytest

from conftest import (
    PROMISE, CRITERIA, EVIDENCE_URL, DEADLINE, BENEFICIARY, BEFORE_DEADLINE,
    GRACE_SECONDS, RECOVERY_AT,
)

OWNER = None  # default sender
ZERO = "0x0000000000000000000000000000000000000000"


def _deploy(deploy, **overrides):
    args = {
        "promise": PROMISE,
        "criteria": CRITERIA,
        "evidence_url": EVIDENCE_URL,
        "deadline": DEADLINE,
        "beneficiary": BENEFICIARY,
        "grace": GRACE_SECONDS,
    }
    args.update(overrides)
    return deploy(
        "accountability_bond.py",
        args["promise"], args["criteria"], args["evidence_url"],
        args["deadline"], args["beneficiary"], args["grace"],
    )


def test_valid_terms_deploy_cleanly(deploy, direct_vm):
    direct_vm.warp(BEFORE_DEADLINE)
    bond = _deploy(deploy)
    terms = json.loads(bond.terms())
    assert terms["deadline"] == DEADLINE
    assert terms["promise"] == PROMISE
    # Recovery terms are visible before funding so a staker can inspect them.
    assert terms["recovery_grace_seconds"] == GRACE_SECONDS
    assert terms["recovery_at"] == RECOVERY_AT
    status = json.loads(bond.status_json())
    assert status["status"] == "OPEN"
    assert status["verdict"] == ""
    assert status["recovery_grace_seconds"] == GRACE_SECONDS
    assert status["recovery_at"] == RECOVERY_AT


@pytest.mark.parametrize("bad_grace", [0, 1, 604799, 86400, -1])
def test_grace_below_minimum_is_rejected(deploy, direct_vm, bad_grace):
    direct_vm.warp(BEFORE_DEADLINE)
    with direct_vm.expect_revert("recovery_grace_seconds"):
        _deploy(deploy, grace=bad_grace)


def test_grace_at_minimum_is_accepted(deploy, direct_vm):
    direct_vm.warp(BEFORE_DEADLINE)
    bond = _deploy(deploy, grace=604800)
    assert json.loads(bond.terms())["recovery_grace_seconds"] == 604800


@pytest.mark.parametrize(
    "bad_deadline",
    [
        "2026-06-01T00:00:00+00:00",   # offset form, not the required Z
        "2026-06-01T00:00:00+05:00",   # non-UTC offset
        "2026-06-01 00:00:00Z",        # space instead of T
        "2026-06-01T00:00:00",         # no zone at all
        "2026-13-01T00:00:00Z",        # impossible month
        "2026-06-32T00:00:00Z",        # impossible day
        "2026-06-01T25:00:00Z",        # impossible hour
        "not-a-date",
        "",
        "2026-06-01T00:00:00.000Z",    # fractional seconds -> wrong length
        "26-06-01T00:00:00Z",          # 2-digit year -> wrong length
    ],
)
def test_invalid_or_non_utc_deadline_is_rejected(deploy, direct_vm, bad_deadline):
    direct_vm.warp(BEFORE_DEADLINE)
    with direct_vm.expect_revert("deadline"):
        _deploy(deploy, deadline=bad_deadline)


def test_zero_beneficiary_rejected(deploy, direct_vm):
    direct_vm.warp(BEFORE_DEADLINE)
    with direct_vm.expect_revert("beneficiary required"):
        _deploy(deploy, beneficiary=ZERO)


def test_empty_promise_rejected(deploy, direct_vm):
    direct_vm.warp(BEFORE_DEADLINE)
    with direct_vm.expect_revert("promise empty"):
        _deploy(deploy, promise="   ")


def test_empty_criteria_rejected(deploy, direct_vm):
    direct_vm.warp(BEFORE_DEADLINE)
    with direct_vm.expect_revert("criteria empty"):
        _deploy(deploy, criteria="")


@pytest.mark.parametrize("bad_url", ["ftp://example.com", "example.com", "", "javascript:alert(1)"])
def test_non_http_evidence_url_rejected(deploy, direct_vm, bad_url):
    direct_vm.warp(BEFORE_DEADLINE)
    with direct_vm.expect_revert("evidence_url"):
        _deploy(deploy, evidence_url=bad_url)
