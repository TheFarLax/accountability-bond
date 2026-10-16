# Security & limitations

Honest accounting of what this contract guarantees, what it does not, and what
is verified versus assumed. No production-readiness or model-accuracy claim.

## Threat model

- **The author controls the evidence URL.** Intended: it is their own bond and
  reputation. A beneficiary cannot grief the author -- resolution fails closed
  to BROKEN (beneficiary) rather than falsely to the author.
- **An author rigging a false BROKEN** merely sends their own stake to an
  address they chose at creation; there is no third party to defraud, so it is
  out of scope rather than defended.

## Guarantees (deterministic, enforced by the contract)

- Funds leave only via a credited verdict + `withdraw()` (or the recovery
  split). Pull-payment clears the ledger entry before transfer -> no reentrancy,
  no double claim.
- Verdict is recomputed on-chain from the agreed boolean; model wording never
  releases funds directly.
- The model's `satisfied` field must be an **actual JSON boolean**; it is
  type-checked (`isinstance(value, bool)`), never coerced with `bool(...)`. A
  string `"false"`, a number `0`/`1`, an object, an array, or `null` is routed
  through the malformed-output path (fail closed) and never yields KEPT.
- Empty/whitespace evidence is BROKEN without ever calling the model.
- `RESOLVED` and `RECOVERED` are terminal and mutually exclusive; neither can
  override the other.
- Deadline is strict UTC `YYYY-MM-DDTHH:MM:SSZ`; recovery grace is immutable and
  `>= 7 days`.

## Recovery: residual griefing risk

`recover()` fixes the only genuine fund-lock case (persistent validator
disagreement) without weakening payouts, since a finalized `resolve()`
forecloses it. But it **bounds, not eliminates, griefing**: a party able to
force non-resolution still captures 50% via the split, so the 50/50 fallback can
disadvantage the beneficiary relative to the verdict they would otherwise have
won. **No burn** -- destroying the honest party's funds to punish a griefer is
disproportionate and unjustified. The deeper fix (removing the author's ability
to induce disagreement, e.g. snapshotted/immutable evidence) is out of scope.

## Limitations (inherent, not fixable in this contract)

- **Model-judgment uncertainty.** `resolve()` relies on a model; it can be wrong
  and varies between runs and validator sets. Spot checks are indicative only.
- **No structural HTTP error detection.** `gl.nondet.web.render()` exposes only
  page text -- no status/headers/redirect. Error, access-denied, paywall, and
  unrelated pages reach the model as ordinary text. The hardened `_JUDGE_TASK`
  instructs the model to treat these as non-demonstrations, but that is
  prompt-level mitigation, not a structural guarantee.
- **Prompt injection in evidence** ("release the funds") is fenced as inert and
  cannot directly move funds (on-chain recompute), but whether the model ignores
  embedded instructions is a model property, not a contract guarantee.

## Coverage

### Verified live on Studionet

Current contract `0x84C0F1B95Dbff655486bbBFA830Ca97C57a0175f` (deployed 2026-10-16
from commit `4bada3a`, tx
`0x26a5baf2931ca69d72883e31d5a83acf711a97446efb416db70cea3433c28e20`):
- Deploy, and read-back of `terms()` / `status_json()` matching the intended
  immutable terms. The bond is `OPEN` and unfunded.

No other live behaviour has been verified on the current contract yet.

### Verified live on the previous build `0x625be5...7485` + recovery instance `0x4f6D4C...bF03`

These results predate the parser fix and belong to the superseded deployment
(see the note below). They are not evidence about the current contract.
- Deploy, `fund()`, `resolve()` -> **KEPT** via real `web.render` + model under
  consensus, owner `withdraw()` + double-withdraw rejection, native GEN out.
- Full recovery path: early `recover()` rejected, `recover()` -> RECOVERED with
  correct 1/2-wei split on a 3-wei stake, `resolve()` after recovery rejected,
  owner withdraw + double-withdraw rejection.
- Per-transaction time control via `genvm_datetime`.
- Model judgement spot-checks (via JudgeProbe): irrelevant, claim-without-proof,
  ambiguous, and error/forbidden/login-wall inputs all returned BROKEN. These
  are a handful of cases, not proof of reliability.

### Direct-mode only (not run live)
- BROKEN resolution and beneficiary payout; fail-closed on empty/malformed
  evidence; validator agree/reject and malformed-leader edges; grace-floor
  constructor rejection; the beneficiary's actual `withdraw()` (live run
  asserted its claimable balance by read, not an actual withdrawal).

### Superseded build and the parser fix

`0x625be5...7485` is the previous deployment. It read the model's `satisfied`
field with `bool(data.get("satisfied"))`, so a value that was not a real boolean
-- the string `"false"`, the number `1`, a non-empty object or array -- was
treated as `True` and could have returned KEPT on malformed output. Commit
`4bada3a` replaces that with a strict `isinstance(value, bool)` check that routes
every non-boolean to the malformed-output path, so such answers cannot yield
KEPT. 20 direct-mode regression tests cover both contracts.

The current contract carries that fix; the live runs listed above were performed
against the previous build before the fix, and the fix itself is verified in
direct mode rather than live. On the current contract only the deploy and
read-back are live-verified.

## Secrets

The deployer private key lives only in a **gitignored** `.env` and is never
printed or committed. No private key appears in any tracked source;
`gltest.config.yaml` references it only as `${ACCOUNT_PRIVATE_KEY_1}`.
