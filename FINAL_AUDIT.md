# KOPA — final audit

Honest status. Anything unverified is marked as such rather than claimed.

Last updated: 2026-09-04.

## Competition requirements

| Requirement | Status | Evidence |
|---|---|---|
| Specific financial-inclusion problem | ✅ | [README](README.md#the-problem) — irregular earners deciding on obligations mentally |
| Meaningful AI | ✅ | [responsible-ai.md](docs/responsible-ai.md); 20 tests |
| Functional BMONI sandbox integration | ⚠️ **Partial** | Wallet deployed, KYC + rail active, balances read. **Settled transfer blocked on manual funding.** |
| Test data only | ✅ | Sandbox + synthetic; [disclosure.md](docs/disclosure.md) |
| Working prototype | ⚠️ **Partial** | Backend fully runnable; app analyzes + tests clean; **APK build unverified** |
| GitHub-ready repository | ✅ | Committed, no secrets, `.gitignore` in place |
| Architecture documented | ✅ | [architecture.md](docs/architecture.md) |
| AI architecture documented | ✅ | [responsible-ai.md](docs/responsible-ai.md) |
| APIs / models / dependencies disclosed | ✅ | [disclosure.md](docs/disclosure.md) |
| Pre-existing work disclosed | ✅ | None — declared explicitly |
| Privacy + security documented | ✅ | [security.md](docs/security.md) |
| Accessibility addressed | ✅ | Four-signal verdicts; semantics; tested |
| Demo script with exact numbers | ✅ | [demo-script.md](docs/demo-script.md), pinned by tests |
| Pitch deck | ❌ **Not done** | Content exists in README; no deck built |
| Demo video | ❌ **Not done** | Script written; not recorded |

## Technical

| Item | Status | Notes |
|---|---|---|
| Backend starts | ✅ | `/health` returns ok |
| Backend tests | ✅ | **58 passed** |
| Safety engine deterministic | ✅ | Asserted by test |
| AI explanation works | ✅ | Integration complete and tested |
| AI narration live | ⚠️ | Anthropic account has **no credit**; fallback in use |
| AI failure handled | ✅ | 7 failure modes tested |
| BMONI user creation | ✅ | `2633ed62-0938-4666-8604-8565c712ddf5` |
| BMONI wallet deployed | ✅ | `0xbDD35d2daA61866c1cAa085A93e2B46eAE669768` |
| EIP-191 owner proof | ✅ | Accepted by BMONI |
| KYC + Nigeria rail | ✅ | `hasBvn: true`, `hasLocalWallet: true` |
| Balance retrieval | ✅ | Returns `NGN 0` — unfunded |
| **Settled sandbox transfer** | ❌ **Blocked** | Wallet unfunded; BMONI credits tokens manually |
| Transaction signing code | ✅ | Implemented; correct method (`signTransactionHash`) |
| Flutter analyze | ✅ | No issues |
| Flutter tests | ✅ | **17 passed** |
| **Android APK build** | ❌ **Unverified** | Build machine out of disk space |
| Database migrations | ⚠️ | Models + seed script written; **Alembic migration not generated** |
| Demo mode | ✅ | Runs with no DB and no BMONI |
| No secrets committed | ✅ | Verified by grep; see below |
| Merchant mode | ⚠️ **Partial** | Counterpart context implemented and tested; folded into the main flow rather than a separate screen |
| Follow-up "what if" | ⚠️ **Partial** | Backend endpoint + parser tested; **no UI** |

## Security audit

```
grep -rn "sk-ant-"                                    → no matches (repo-wide)
grep -rn "pk_a025cacbf33a"                            → no matches (repo-wide)
grep -rn "x-api-key|BMONI_API_KEY|ANTHROPIC_API_KEY" kopa_app/
    → 1 match, a comment in api_client.dart asserting their absence
```

- `.env` gitignored and confirmed via `git check-ignore`
- `.env.example` ships an **empty** `BMONI_API_KEY`
- No BMONI base URL or client in the Flutter app
- Logs redact `x-api-key`, signatures, `bvn`, `nin`, photo blobs
- All DB access via SQLAlchemy bound parameters
- Money is `Decimal` / `NUMERIC` throughout

Known gaps, documented in [security.md](docs/security.md): no user
authentication, no rate limiting, HTTP in local dev, shared public sandbox key.

## Judge-proofing

**What problem does KOPA solve?** A balance doesn't tell you whether you can
afford something. ₦47,500 looks fine until rent is due Thursday.

**Why does it need AI?** It doesn't, for the decision — deliberately. AI turns
an auditable number set into a sentence a person acts on. The verdict is
deterministic.

**What stops the AI inventing numbers?** It never computes any. It receives
final figures, its output is validated, and the verdict is never parsed from
its response. Tested.

**Where is BMONI used?** Wallet provisioning, KYC, the NGN rail, balances, and
the proposal/sign flow. The proposal-then-sign split is *why* KOPA can exist.

**Where is the BMONI key?** Backend environment only.

**Where is the private key?** Android Keystore. Never on a server.

**What if the LLM fails?** Deterministic explanation, and the user is told.

**What if the sandbox fails during judging?** Demo mode — engine and AI still
real, seeded data clearly labelled.

**Can I test it?** Yes — demo mode needs no database and no BMONI credentials.

## What I would not claim

- KOPA has **not** completed a settled sandbox transfer. The chain is built and
  the signing method is correct, but the wallet is unfunded.
- The **APK has never been built**. The Dart code is verified by analysis and
  tests; the packaged artifact is not.
- **Live AI narration has not run** against a funded account.
- There is **no pitch deck and no demo video**.
- **No Alembic migration** has been generated; `Base.metadata.create_all` is
  used by the seed script.

## To finish

Blocking, needs a human:

1. **Free ~10 GB disk** → build and verify the APK
2. **Add Anthropic credit** → live AI narration
3. **Submit the BMONI token request** (phone `+2348088485390`) → settled transfer

Then, in priority order:

4. Generate the Alembic migration
5. Record the demo video against [demo-script.md](docs/demo-script.md)
6. Build the pitch deck from the README
7. Follow-up "what if" UI (backend already works)
