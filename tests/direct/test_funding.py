"""Funding guards: owner-only, once, positive stake, and only before the deadline."""

import json

import pytest

from conftest import AFTER_DEADLINE, BEFORE_DEADLINE, set_now


def test_fund_escrows_the_stake(bond, direct_vm):
    direct_vm.value = 1000
    bond.fund()
    direct_vm.value = 0
    status = json.loads(bond.status_json())
    assert status["status"] == "FUNDED"
    assert status["held"] == 1000


def test_fund_requires_positive_value(bond, direct_vm):
    with direct_vm.expect_revert("stake must be positive"):
        bond.fund()


def test_only_owner_may_fund(bond, direct_vm, direct_bob):
    direct_vm.sender = direct_bob
    direct_vm.value = 1000
    with direct_vm.expect_revert("only owner may fund"):
        bond.fund()


def test_cannot_fund_twice(funded, direct_vm):
    direct_vm.value = 500
    with direct_vm.expect_revert("already funded"):
        funded.fund()


def test_cannot_fund_after_deadline(bond, direct_vm):
    set_now(direct_vm, AFTER_DEADLINE)
    direct_vm.value = 1000
    with direct_vm.expect_revert("deadline already passed"):
        bond.fund()
