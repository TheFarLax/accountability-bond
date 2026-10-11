# Architecture

A single GenVM contract, `contracts/accountability_bond.py`, plus a disposable
test harness `contracts/judge_probe.py`. One class per file (a GenVM
requirement). Source is pure ASCII (gltest hex-encodes source as ASCII; one
non-ASCII byte breaks deployment).

## Why GenLayer

The judgement -- "does this evidence meet this prose criterion?" -- is over
unstructured, real-world data and cannot be made deterministic. GenLayer settles
it by having each validator independently run the judgement and agree on the
distilled result. A normal chain would need a trusted oracle/referee; this
removes it.

## Resolution flow (`resolve()`)

1. Guard: must be `FUNDED` and `now >= deadline` (clock read from
   `gl.message_raw["datetime"]`; `gl.message` has no clock on this runner).
2. Inside `gl.vm.run_nondet_unsafe(judge, validate)`:
   - **leader** `judge()`: `gl.nondet.web.render(url, mode="text")`; empty page
     short-circuits to BROKEN *without* calling the model; otherwise builds the
     fenced prompt (`_JUDGE_TASK` + promise + criterion + inert-fenced evidence)
     and calls `gl.nondet.exec_prompt(..., response_format="json")`; returns a
     canonical `{"kept": bool, "reason": str}`.
   - **validator** `validate(leaders_res)`: re-runs `judge()` and agrees **only**
     when its boolean `kept` equals the leader's. Reason strings are excluded
     from the equivalence check (independent judges word them differently). A
     non-`Return` leader result (error) -> disagree -> leader rotation.
3. Post-consensus: the verdict is **recomputed on-chain** from the agreed
   boolean, and the stake is credited to the owner (KEPT) or beneficiary
   (BROKEN) in a `claimable` ledger.

This mirrors the "spend consensus on the judgement, act deterministically on the
result" pattern. The model's wording never releases funds directly.

## Recovery flow (`recover()`)

Pure deterministic: a time check (`now >= deadline + recovery_grace_seconds`)
plus a 50/50 ledger split. No model/web call, so it cannot get stuck in
consensus failure -- that is what makes it a reliable backstop for the one case
`resolve()` cannot self-resolve (persistent validator disagreement). See
[SECURITY.md](SECURITY.md).

## State

Immutable (constructor): `owner`, `beneficiary`, `promise`, `criteria`,
`evidence_url`, `deadline` (canonical `YYYY-MM-DDTHH:MM:SSZ`),
`recovery_grace_seconds` (`u256`, >= 604800). Mutable lifecycle: `status`
(`OPEN|FUNDED|RESOLVED|RECOVERED`), `verdict`, `reason`, `balance_held`,
`claimable: TreeMap[Address, u256]`.

## Payout

Pull-payment: `resolve()`/`recover()` only credit the `claimable` ledger;
`withdraw()` zeroes the caller's entry **before** `emit_transfer`, so there is
no reentrancy window and no double claim.

## Time control

- On-chain: `gl.message_raw["datetime"]`, injected per transaction.
- Live tests: `transaction_context={"genvm_datetime": "<ISO>"}` (-> gltest
  `SimConfig.genvm_datetime`) sets it per call -- this is how the 7-day grace is
  tested without waiting.
- Direct tests: the `set_now()` helper in `tests/direct/conftest.py` (the direct
  harness does not refresh the contract's datetime on a bare `warp()`).

## JudgeProbe (test harness, not a product)

`contracts/judge_probe.py` reuses `_JUDGE_TASK`, the inert-evidence fencing, and
the `run_nondet_unsafe` consensus logic **verbatim** from the bond (enforced by
`tests/direct/test_probe_parity.py`, which asserts byte-identical shared text).
It takes evidence as a direct argument instead of via `web.render`, has no
payable/escrow/transfer surface, and exists only to spot-check the live model's
judgement in isolation. Because GenVM forbids cross-file imports, the shared
logic is a parity-checked copy, not runtime-shared.
