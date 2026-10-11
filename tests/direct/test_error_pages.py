"""Error-page / unreliable-evidence handling for AccountabilityBond.resolve().

HONEST SCOPE. `gl.nondet.web.render(url, mode="text")` returns ONLY the rendered
page text -- no HTTP status code, no headers, no redirect info (confirmed against
the installed SDK and the GenLayer web-access docs: only `web.request`/`get`
expose `.status`, and the contract uses `render`). So the contract CANNOT detect
an error page structurally. A 404/403/503 body is just non-empty text and is
handed to the model like any other page.

What the contract CAN guarantee deterministically, and what these tests pin:
  * truly empty / whitespace-only evidence never reaches the model and is BROKEN;
  * every non-empty page (including an error page) is judged, and whatever boolean
    comes back maps faithfully to the payout with no default-allow path.

Whether an error/access-denied/unrelated page is correctly judged BROKEN is a
MODEL property, not a contract one. The prompt now explicitly instructs the model
to treat error pages, access-denied/login/paywall screens, and claim-without-proof
pages as non-demonstrations -- but these mocked tests cannot prove the model
obeys that. That is validated separately and non-exhaustively by the live
JudgeProbe run. These tests therefore assert the CONTRACT mapping, and are
labelled so no one mistakes them for proof the model classifies error pages.
"""

import json

import pytest

from conftest import AFTER_DEADLINE, BENEFICIARY, JUDGE_PROMPT, RENDER_URL, judgement, set_now


def _page(direct_vm, body, satisfied):
    direct_vm.mock_web(RENDER_URL, {"status": 200, "body": body})
    direct_vm.mock_llm(JUDGE_PROMPT, judgement(satisfied))


# ---- deterministic: empty-ish evidence never reaches the model, always BROKEN
@pytest.mark.parametrize("body", ["", "   ", "\n\t  \n", "\r\n"])
def test_blank_evidence_is_broken_without_model(funded, direct_vm, body):
    set_now(direct_vm, AFTER_DEADLINE)
    direct_vm.mock_web(RENDER_URL, {"status": 200, "body": body})
    # No LLM mock: reaching the model would error on a missing mock.
    assert funded.resolve() == "BROKEN"
    assert funded.claimable_of(BENEFICIARY) == 1000


# ---- error / access-denied / unrelated pages: non-empty text, so they DO reach
# the model. The contract must honour the model's boolean. We pin the fail-closed
# expectation (model judges these unmet -> BROKEN), which is what the hardened
# prompt instructs; the model's actual compliance is a live-run matter.
@pytest.mark.parametrize(
    "label,body",
    [
        ("not_found", "404 Not Found. The requested URL /proof was not found on this server."),
        ("forbidden", "403 Forbidden. You do not have permission to access this resource."),
        ("server_error", "500 Internal Server Error. Something went wrong."),
        ("unavailable", "503 Service Temporarily Unavailable."),
        ("login_wall", "Sign in to continue. Please log in to view this page."),
        ("paywall", "This content is for subscribers only. Subscribe to read more."),
        ("unrelated", "Buy cheap sunglasses now! Limited time offer, free shipping."),
    ],
)
def test_error_or_blocked_pages_map_broken_when_model_rejects(funded, direct_vm, label, body):
    set_now(direct_vm, AFTER_DEADLINE)
    _page(direct_vm, body, satisfied=False)
    assert funded.resolve() == "BROKEN", label
    assert funded.claimable_of(BENEFICIARY) == 1000


def test_error_page_still_reaches_the_model_as_text():
    """Documents, by construction, that render() gives no status: an error body
    is indistinguishable from content to the contract, so it is sent to the model
    rather than special-cased. If a future SDK exposes status on render(), this is
    where a deterministic short-circuit would be added."""
    from pathlib import Path
    src = Path(__file__).parent.parent.parent / "contracts" / "accountability_bond.py"
    text = src.read_text()
    # The contract reads only render(..., mode="text"); it never inspects an HTTP
    # status (render exposes none). Guard against the specific status-access forms
    # web.request/get would use, not the contract's own `self.status` field.
    assert 'web.render(url, mode="text")' in text
    assert ".status_code" not in text
    assert "web.request" not in text
    assert "web.get(" not in text
