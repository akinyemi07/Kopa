# KOPA

**Financial safety analysis before you sign.**

KOPA tells you what a transfer will actually do to your money — your balance,
how long it lasts, and which bills it puts at risk — *before* you sign it,
not after.

Built for the NITHUB Innovation Fair Hackathon 2026 — *Intelligent Money for
Everyone*, on BMONI Embedded.

---

## The problem

A wallet balance is the least useful number in personal finance, because it
answers the wrong question.

₦47,500 looks like plenty. It stops looking like plenty when you remember rent
is ₦25,000 and due on Thursday. The person most likely to be hurt by that gap
is the person least likely to have a spreadsheet: paid irregularly, juggling
obligations mentally, and making send-money decisions on a phone in the moment
someone asks.

Every wallet app in the market answers *"can this transfer go through?"* —
a question about the ledger. Nobody answers *"should it?"* — the question the
person is actually asking.

That gap is where money goes wrong. Not through fraud, usually, but through a
transfer that was affordable on Tuesday and left rent unpayable on Thursday.

## The solution

KOPA inserts one screen between "send" and "signed".

That screen shows the resulting balance, an estimated runway in days, the
specific upcoming obligations the transfer would break, and what KOPA knows
about the recipient — then explains it in plain language and lets the user
decide.

KOPA **advises; it never blocks.** "Send anyway" is always available. The goal
is an informed decision, not an enforced one.

## Why BMONI

KOPA is not an app with a wallet bolted on — the wallet *is* the product
surface. BMONI Embedded provides:

- an on-device Ethereum key in the Android Keystore, so the user genuinely
  controls their own funds
- a deployed smart wallet on the CNGN (Naira stablecoin) rail
- Nigerian KYC and identity verification
- a proposal → approve → sign transfer flow that gives KOPA a natural,
  non-contrived place to intervene *between intent and settlement*

That last point is the whole architecture. Because BMONI separates creating a
proposal from signing it, KOPA can run its safety analysis in the gap. On a
rail where sending is a single atomic call, this product could not exist.

## Why AI

The safety verdict is **not** produced by AI, and this is deliberate.

A deterministic engine computes every figure and reaches the verdict. The
language model receives those figures and writes two to four sentences of
plain-language explanation. It cannot compute, override, or invent a number,
because it is never asked to and its output never re-enters the decision.

```
user input → deterministic engine → numeric facts → LLM → explanation
                      ▲                                        │
                      └──────── never flows back ──────────────┘
```

A model cannot hallucinate a balance it was never asked to calculate. See
[docs/responsible-ai.md](docs/responsible-ai.md).

---

## Architecture

```
                    ┌──────────────────────┐
                    │    KOPA Flutter app  │
                    │  ┌────────────────┐  │
                    │  │ bmoni_embedded │  │  private key
                    │  │      _sdk      │  │  NEVER leaves
                    │  └───────┬────────┘  │  the device
                    └──────┬───┴───────────┘
                           │            │
              HTTPS        │            │ on-device signing only
        (no credentials)   │            │ (address + 2 signatures out)
                           ▼            ▼
                 ┌──────────────────┐   │
                 │  KOPA FastAPI    │   │
                 │  ─ holds the ─   │   │
                 │  x-api-key ONLY  │   │
                 └───┬──────┬───────┘   │
                     │      │           │
       ┌─────────────┘      └────────┐  │
       ▼                             ▼  ▼
┌─────────────┐            ┌──────────────────┐
│ PostgreSQL  │            │  BMONI Embedded  │
│ obligations │            │     sandbox      │
│ history     │            └──────────────────┘
│ audit log   │
└─────────────┘
       │
       ▼
┌──────────────────┐      ┌─────────────────┐
│  Safety engine   │─────▶│   AI copilot    │
│  deterministic   │facts │  explains only  │
│  LLM-free        │      │  (Claude)       │
└──────────────────┘      └─────────────────┘
```

| Concern | Where it lives |
|---|---|
| Wallet private key | Android Keystore, on device. Never on any server. |
| BMONI partner key | `kopa_backend` environment only. Never in the app. |
| Anthropic key | `kopa_backend` environment only. |
| Financial calculation | `app/services/safety_engine.py` — pure, deterministic |
| AI | `app/services/ai_copilot.py` — narration only |
| User confirmation | Flutter, after the safety screen, gated by PIN |

Full detail: [docs/architecture.md](docs/architecture.md) ·
[docs/bmoni-integration.md](docs/bmoni-integration.md) ·
[docs/security.md](docs/security.md)

---

## Running it

### Backend

```bash
cd kopa_backend
python -m venv ../.venv && ../.venv/Scripts/python.exe -m pip install -r requirements.txt
cp .env.example .env      # then fill in BMONI_API_KEY and ANTHROPIC_API_KEY
../.venv/Scripts/python.exe -m uvicorn app.main:app --reload
```

Interactive API docs at `http://localhost:8000/docs`.

Demo mode needs no database and no BMONI connectivity:

```bash
KOPA_DEMO_MODE=true ../.venv/Scripts/python.exe -m uvicorn app.main:app
```

### App

```bash
cd kopa_app
flutter run
```

The app defaults to `http://10.0.2.2:8000` (the Android emulator's route to the
host). Override for a physical device:

```bash
flutter run --dart-define=KOPA_API_BASE_URL=http://192.168.1.5:8000
```

### The one call that shows the whole product

```bash
curl -s -X POST http://localhost:8000/decisions/evaluate \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"11111111-1111-1111-1111-111111111111",
       "proposed_amount":30000,"counterpart":"QuickLoan NG","type":"personal"}'
```

---

## Testing

```bash
cd kopa_backend && ../.venv/Scripts/python.exe -m pytest -q   # 58 passed
cd kopa_app     && flutter analyze && flutter test            # 17 passed
```

**75 tests.** The suite deliberately concentrates on the two claims a judge
should be most sceptical of:

- *the engine is deterministic* — identical inputs produce byte-identical
  output; money never becomes a float; boundaries are pinned
- *the AI cannot override the verdict* — a model that contradicts an `unsafe`
  verdict is **rejected** and replaced with the deterministic explanation

See [docs/testing.md](docs/testing.md).

---

## Sandbox and demo mode

**All data is sandbox or synthetic. No real funds, no real personal data.**

- BMONI calls hit `embedded-dev.bmoni.com` with a sandbox partner key.
- Identity uses BMONI's published test persona (Bunch Dillon, BVN
  `95888168924`). It is fictional.
- Demo-mode balances and history are seeded synthetic data describing a
  fictional person, and are labelled **DEMO DATA** in the UI wherever shown.
- A demo transfer is recorded with no BMONI reference and a distinct
  `DEMO` status, and the success screen says plainly that no money moved.

Demo mode exists so a flaky sandbox cannot break a live demonstration. The
safety engine and the AI layer still run for real on top of seeded data — only
the BMONI *reads* are substituted.

---

## Disclosure

Per the hackathon's declaration requirement — full detail in
[docs/disclosure.md](docs/disclosure.md).

**Pre-existing work:** none. Every line in `kopa_app/` and `kopa_backend/` was
written during the official build period. The two documents at the repository
root (`KOPA_BUILD_GUIDE.md`, `Hackathon-Competition-Requirements.md`) are the
brief, authored before the build.

**AI models:** Anthropic Claude (`claude-sonnet-5`) via the official
`anthropic` Python SDK, used solely to narrate the safety engine's output.
Claude Code was used as a development assistant.

**External APIs:** BMONI Embedded REST API (sandbox); Anthropic Messages API.

**BMONI SDKs:** `bmoni_embedded_sdk` 0.0.2, `bkey_uikit` 0.0.1,
`bmoni_embedded_wallets_cards` 0.0.1.

**Key open-source dependencies:** Flutter 3.47.2 / Dart 3.13.2, FastAPI,
SQLAlchemy, Alembic, Pydantic, PostgreSQL, httpx, pytest.

**Data:** sandbox and synthetic only. No real user financial data was used at
any point.

---

## Notes for reviewers

Three defects were found in BMONI's published documentation by probing the live
API, and are worked around in `app/services/bmoni_client.py`:

1. `PATCH /kyc` rejects the `addressDetails` property shown in the published
   quickstart. The accepted top-level keys are `personalInfo`, `address`,
   `employment`, `sourceOfFunds`, `identificationNumbers`.
2. `identificationNumbers` must be an **array**, not an object.
3. The Flutter SDK's `BmoniSignerErrorCode` is a class of `static const int`
   values, not a Dart enum, and has no `walletNotFound` member.

One security observation, raised here rather than exploited: the sandbox
partner key published in BMONI's public quickstart is shared across all
hackathon participants, and `GET /v1/users` returns every participant's name,
email and phone number. This is sandbox-only, but worth BMONI's attention.

## Licence

Apache-2.0.
