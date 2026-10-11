# Hackathon submission: AccountabilityBond

**One line.** A trustless commitment contract: stake GEN on a prose promise
about your own conduct; at the deadline the contract reads your nominated
evidence URL, has validators judge a concrete success criterion under consensus,
and returns the stake on success or sends it to a chosen beneficiary on failure.

**Why GenLayer.** Deciding "did they actually keep the promise" from a prose
rule and a live web page is a judgement over unstructured real-world data that
no deterministic contract can make. GenLayer settles it with model + web access
under validator consensus, removing the trusted referee every existing
commitment device relies on.

**What's implemented and verified (contract + tests only).**
- Lifecycle: `fund` (payable, owner, pre-deadline) -> `resolve` (anyone, at/after
  deadline; real `web.render` + model, consensus on a single boolean verdict) ->
  `withdraw` (pull-payment). Fail-closed: only a clear, agreed "criterion met"
  yields KEPT.
- Deterministic recovery backstop: `recover` splits the stake 50/50 (odd
  remainder to beneficiary) once deadline + an immutable grace (>= 7 days) has
  passed and the bond is still unresolved; mutually exclusive with a finalized
  verdict.
- 87 direct-mode tests passing. Live on Studionet (chain `61999`): normal
  fund/resolve-KEPT/withdraw lifecycle and the full recovery lifecycle both
  verified; model judgement spot-checked (irrelevant / claim-without-proof /
  ambiguous / error-page inputs all returned BROKEN).
- Primary contract: `0x625be5C311e7Cafde91477412c2157E46C7F7485` (Studionet).

**Explicitly not claimed.** Not production-ready; no guarantee of model
accuracy. `web.render()` exposes no HTTP status, so error-page handling is
prompt-level, not structural. Recovery bounds but does not eliminate griefing.
Spot checks are indicative, not proof of general reliability.

**Scope.** Intelligent contract (`contracts/accountability_bond.py`) and its
test suite, plus a disposable judgement-probe harness used only for live model
spot-checks. No frontend or other application. See README.md, ARCHITECTURE.md,
SECURITY.md.
