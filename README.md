# AccountabilityBond

**A trustless commitment contract on GenLayer.** Stake GEN on a promise about
your own future conduct, written in plain prose. At a deadline the contract
reads a public evidence URL you nominated, asks a model whether a concrete
success criterion was met, and -- only if the validator set *agrees* on that one
verdict -- returns your stake. Otherwise it goes to a beneficiary you named up
front. A trustless StickK/Beeminder: no human referee, no oracle.

> Status: hackathon submission, deployed and verified on **GenLayer Studionet**.
> This is **not** production-ready and makes **no guarantee of model accuracy**
> (see [Limitations](#limitations)).

## The problem

Commitment devices ("I'll ship v1 by Friday or $100 goes to charity") work, but
every existing one depends on a *trusted referee* to decide whether you kept the
promise. A normal smart contract can't judge "did they actually do it" from a
prose promise and a live web page -- that is a judgement over unstructured,
real-world data.

## The solution

GenLayer Intelligent Contracts can call a model and read the live web under
validator consensus. `AccountabilityBond` spends that judgement **once**, at the
deadline: each validator independently fetches the evidence, judges the author's
criterion, and consensus settles on a single boolean verdict (not the raw page,
which legitimately differs between fetches). The payout is then recomputed
deterministically on-chain -- the model's wording never moves funds directly.

## Contract lifecycle

```
deploy(promise, criteria, evidence_url, deadline, beneficiary, recovery_grace_seconds)
        |                                   terms are immutable
        v
      OPEN --fund() [owner, once, before deadline, payable]--> FUNDED
        |
 FUNDED --resolve() [anyone, at/after deadline]--------------> RESOLVED  (KEPT|BROKEN)
        |         real web.render + model, consensus on the boolean verdict
        |
 FUNDED --recover() [anyone, at/after deadline + grace]------> RECOVERED (50/50 split)
                  deterministic backstop; no model call

RESOLVED and RECOVERED are terminal and mutually exclusive.
withdraw() [pull-payment] pays whoever the verdict credited.
```

Verdicts: `KEPT` (stake -> author), `BROKEN` (stake -> beneficiary),
`RECOVERED` (stake split 50/50). Resolution is **fail-closed**: anything short
of a clear agreed "criterion met" -- ambiguity, an empty/unreachable page, a
malformed model answer -- is not `KEPT`.

## Public methods

| Method | Kind | Who | Notes |
|---|---|---|---|
| `fund()` | write, payable | owner | once, before the deadline |
| `resolve()` | write | anyone | at/after deadline; model judgement; idempotent |
| `recover()` | write | anyone | at/after deadline+grace, still FUNDED; 50/50 split |
| `withdraw()` | write | credited party | pull-payment, ledger cleared before transfer |
| `status_json()` | view | anyone | status, verdict, held, deadline, recovery terms |
| `terms()` | view | anyone | immutable terms + `recovery_at` (inspect before funding) |
| `claimable_of(addr)` | view | anyone | amount an address can withdraw |

## Setup

Requires Python 3.12+. The contract itself has no dependencies -- it is a single
GenVM file whose only import is `from genlayer import *`.

```bash
python3.12 -m venv .venv && . .venv/bin/activate
pip install genlayer-test==0.29.2        # provides `gltest` and the direct runner
```

Deployer account (persistent, controllable) is read from a **gitignored** `.env`:

```bash
cp .env.example .env
# put a 64-hex private key in .env as ACCOUNT_PRIVATE_KEY_1 (never commit it)
```

`gltest.config.yaml` pins the studionet deployer to `${ACCOUNT_PRIVATE_KEY_1}`
so the same address is used across separate Python processes. The private key
lives only in `.env`.

## Tests

```bash
# Direct mode: in-process, no network, no model, deterministic, fast.
pytest tests/direct                                   # 107 tests

# Integration (live Studionet; sends transactions, needs a funded deployer):
gltest --network studionet tests/integration/test_integration.py       # fund/resolve/withdraw
gltest --network studionet tests/integration/test_recovery_live.py     # recovery lifecycle
gltest --network studionet tests/integration/test_judge_probe_live.py  # model judgement spot-checks
```

**Live-tested vs. direct-mode only** -- see [SECURITY.md](SECURITY.md#coverage).
In short: funding, KEPT resolution, owner withdrawal + double-withdraw
rejection, native transfer out, and the full recovery path are **verified live**;
the BROKEN payout, fail-closed edges, consensus agree/reject, grace-floor
rejection, and the beneficiary's actual `withdraw()` are **direct-mode only**.

## Network details

| | |
|---|---|
| Network | GenLayer **Studionet** |
| Chain ID | `61999` (`0xf22f`) |
| RPC | `https://studio.genlayer.com/api` |
| Primary contract | `0x625be5C311e7Cafde91477412c2157E46C7F7485` |
| Recovery test instance | `0x4f6D4C024760DD88aD6828B1D2E9461FbB44bF03` |

Studionet state is resettable, so these addresses are evidence of the verified
runs, not permanent guarantees.

## Recovery mechanism

If `resolve()` can never reach consensus (e.g. a criterion so vague that
independent judges never converge), the stake would otherwise be locked forever.
`recover()` is a **deterministic** backstop: once the deadline **plus an
immutable grace period** has passed and the bond is still `FUNDED`, anyone may
split the stake **50/50** (odd remainder to the beneficiary). The grace is fixed
per bond at construction and must be **>= 7 days** (`604800s`). Because
`recover()` runs no model/web call, it cannot itself get stuck. A successful
`resolve()` forecloses it, so recovery can never override a valid verdict.

Recovery **bounds but does not eliminate griefing**: a party who can force
non-resolution still captures half, so the 50/50 fallback can disadvantage the
beneficiary relative to the verdict they would otherwise have won. There is no
burn -- destroying the honest party's funds to deter a griefer is not justified.

## Limitations

- **Model-judgment uncertainty.** Resolution relies on a model's judgement,
  which can be wrong and varies run to run. Spot checks are encouraging, not a
  guarantee. No claim of general reliability or production readiness.
- **No structural HTTP error detection.** `gl.nondet.web.render()` returns only
  page text -- **no HTTP status, headers, or redirect info** (only
  `web.request/get` expose a status, and the contract does not use them). So an
  error/404/paywall page reaches the model as ordinary text; the hardened prompt
  instructs the model to treat such pages as non-demonstrations, but this is
  prompt-level, not a structural guarantee.
- **Author controls the evidence URL** -- intended (own bond, own reputation);
  see [SECURITY.md](SECURITY.md).

See [ARCHITECTURE.md](ARCHITECTURE.md) and [SECURITY.md](SECURITY.md) for detail.
