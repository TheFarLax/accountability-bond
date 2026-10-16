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
- 107 direct-mode tests passing. Live on Studionet (chain `61999`): on the
  earlier deployment the normal fund/resolve-KEPT/withdraw lifecycle and the full
  recovery lifecycle were both verified; model judgement spot-checked
  (irrelevant / claim-without-proof / ambiguous / error-page inputs all returned
  BROKEN). The current deployment has itself been deployed, funded, and read back
  so far.
- Current contract: `0x84C0F1B95Dbff655486bbBFA830Ca97C57a0175f` (Studionet),
  deployed 2026-10-16 from commit `4bada3a`. Funded 2026-10-16 with `0.5 GEN`
  (`500000000000000000 wei`): status `FUNDED`, holding that stake.
  - Deployment transaction (creates the contract, no value):
    `0x26a5baf2931ca69d72883e31d5a83acf711a97446efb416db70cea3433c28e20`.
  - Funding transaction (owner escrows the stake, one `fund()` call):
    `0x4d33f68b9c2d308b06d7923cafeec0f5c55bc210b0fad0360230202cae01999f`.
  Both reported `ACCEPTED` with consensus `MAJORITY_AGREE`; the state above was
  confirmed by reading `status_json()` from the live contract.
- Terms in force for the funded bond: the author publishes tagged release `v1.0.0`
  of `TheFarLax/accountability-bond` by deadline `2026-11-30T00:00:00Z`, judged
  against the project's releases page
  (`https://github.com/TheFarLax/accountability-bond/releases`); recovery opens
  `2026-12-07T00:00:00Z` (deadline plus the immutable 7-day grace). No release
  has been confirmed published yet, so the promise is **pending**, not fulfilled.
  After the deadline, `resolve()` may be called by anyone (KEPT returns the stake
  to the owner, BROKEN sends it to the beneficiary); if resolution never reaches
  consensus, `recover()` from `2026-12-07` splits it 50/50; the credited party
  claims via `withdraw()`.
- Previous contract: `0x625be5C311e7Cafde91477412c2157E46C7F7485` (Studionet),
  superseded. It coerced the model's `satisfied` field with `bool(...)`, so a
  malformed answer such as the string `"false"` could be read as `true`.
  The newer commit requires an actual JSON boolean, which fails closed.

**On the earlier rejection.** This project was previously submitted and
rejected; the corrected contract above is a fresh deployment, not a resubmission
claim. The reviewers' exact reason was not recorded, so no single cause is
asserted here. The parser type-safety bug was real and is fixed, but it is not
claimed to have been the only reason.

**Explicitly not claimed.** Not production-ready; no guarantee of model
accuracy. `web.render()` exposes no HTTP status, so error-page handling is
prompt-level, not structural. Recovery bounds but does not eliminate griefing.
Spot checks are indicative, not proof of general reliability.

**Scope.** Intelligent contract (`contracts/accountability_bond.py`) and its
test suite, plus a disposable judgement-probe harness used only for live model
spot-checks. No frontend or other application. See README.md, ARCHITECTURE.md,
SECURITY.md.
