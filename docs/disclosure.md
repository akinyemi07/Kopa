# Disclosure

The hackathon rules require entrants to declare pre-existing work, AI models,
code, datasets, APIs, and third-party tools, and state that false claims may
disqualify an entry. This document is that declaration.

## Pre-existing work

**None of the judged solution.** Every line of `kopa_app/`, `kopa_backend/`,
`scripts/` and `docs/` was written during the official build period.

Two files at the repository root pre-date the build and are **not** part of the
judged solution:

| File | What it is |
|---|---|
| `Hackathon-Competition-Requirements.md` | The published brief |
| `KOPA_BUILD_GUIDE.md` | A build plan written before the build started |

No prior codebase, template, boilerplate beyond `flutter create`, or previously
written module was carried into this project.

## AI models

| Model | Provider | Used for |
|---|---|---|
| `claude-sonnet-5` | Anthropic | Narrating the safety engine's output |

Accessed through the official `anthropic` Python SDK (v0.42.0) via the Messages
API. Configured in `kopa_backend/app/services/ai_copilot.py`.

**Scope of use in the product:** the model writes two to four sentences
explaining figures that have already been computed. It performs no financial
calculation and cannot alter a verdict. See
[responsible-ai.md](responsible-ai.md).

**Current state:** at the time of writing, the Anthropic account has no
credit, so the API returns a billing error and KOPA serves its deterministic
fallback explanation. This is disclosed rather than hidden — the integration is
complete and tested, and the fallback path is itself a tested feature.

**Development assistance:** Claude Code was used as a coding assistant during
the build. All output was reviewed, executed and tested; no code was accepted
without being run.

## External APIs

| API | Environment | Used for |
|---|---|---|
| BMONI Embedded REST API | Sandbox, `embedded-dev.bmoni.com` | Users, wallets, KYC, rails, balances, transfers |
| Anthropic Messages API | Production | Explanation text |

No other external service is called.

## BMONI SDKs and packages

| Package | Version | Source |
|---|---|---|
| `bmoni_embedded_sdk` | 0.0.2 | pub.dev |
| `bkey_uikit` | 0.0.1 | pub.dev |
| `bmoni_embedded_wallets_cards` | 0.0.1 | pub.dev |

The BMONI partner API key used is the **shared sandbox key published in BMONI's
own public quickstart documentation**. It is not committed to this repository.

## Open-source dependencies

**Mobile** — Flutter 3.47.2 / Dart 3.13.2, `http`, `intl`, `flutter_riverpod`,
`flutter_secure_storage` (transitive, via the BMONI SDK), `cupertino_icons`.

**Backend** — FastAPI, Uvicorn, SQLAlchemy 2.0, Alembic, Pydantic v2,
pydantic-settings, psycopg 3, httpx, `anthropic`, pytest.

**Spike tooling only** — `eth-account`, used in `scripts/bmoni_spike.py` to
stand in for on-device signing while validating the BMONI chain before the
Flutter app existed. It is not a dependency of the shipped application and
appears nowhere in `kopa_backend/requirements.txt`.

**Infrastructure** — PostgreSQL 16.

## Data

**All data is sandbox or synthetic. No real funds and no real personal
financial data were used at any point.**

| Data | Nature |
|---|---|
| BMONI wallets and transfers | Sandbox environment, no value |
| Identity (Bunch Dillon, BVN `95888168924`) | BMONI's published fictional test persona |
| Demo balance, history, obligations | Synthetic, authored for this project, describing a fictional person |

No external dataset was used. The demo figures in
`kopa_backend/app/services/demo_data.py` were written by hand to make both a
safe and an unsafe verdict reachable on demand rather than by luck.

Synthetic data is never presented as real. Demo-mode figures are labelled
**DEMO DATA** in the UI, and a demo transfer carries no BMONI reference and a
distinct `DEMO` status in the database.

## Honest statement of what does and does not work

Included because overclaiming is disqualifying, and because a reviewer will
find this out anyway.

**Verified working against the live sandbox:**

- BMONI user creation, owner-proof challenge, EIP-191 signature accepted
- Smart wallet deployed on-chain (`0xbDD35d2daA61866c1cAa085A93e2B46eAE669768`)
- KYC profile submission and BVN resolution
- Nigeria rail activation (`hasBvn: true`, `hasLocalWallet: true`)
- Balance retrieval
- Safety engine and AI layer, end to end, 58 backend tests
- Flutter safety-result rendering, 17 widget tests, `flutter analyze` clean

**Not yet demonstrated:**

- **A settled sandbox transfer.** Sandbox wallets start empty and BMONI credits
  test tokens manually, on roughly a one-business-day turnaround. The proposal
  → approve → sign-payload → sign chain is implemented and the signing method
  is correct, but a completed transfer requires a funded balance.
- **A packaged Android APK.** The Dart code passes analysis and tests, but the
  Gradle build did not complete because the build machine ran out of disk
  space. The build is unverified.
- **Real AI narration in a live run**, pending Anthropic credit as noted above.

These are stated as limitations, not presented as successes.
