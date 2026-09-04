# Architecture

## Components

```
┌──────────────────────────────────────────────────────────┐
│  kopa_app  (Flutter 3.47 / Dart 3.13, Android 24+)       │
│                                                          │
│  screens/  home · send · safety_result · pin · success   │
│  services/wallet_service.dart ──► bmoni_embedded_sdk     │
│  core/api_client.dart ─────────► kopa_backend            │
│                                                          │
│  Holds: the wallet private key (Android Keystore)        │
│  Holds no API credentials of any kind                    │
└───────────────┬──────────────────────────┬───────────────┘
                │ HTTPS (no credentials)   │ local, on-device
                ▼                          ▼
┌───────────────────────────────┐   ┌──────────────────────┐
│  kopa_backend  (FastAPI)      │   │  Android Keystore    │
│                               │   │  secp256k1 key       │
│  api/       decisions ·       │   │  never leaves device │
│             wallets ·         │   └──────────────────────┘
│             transactions      │
│  services/  safety_engine ◄── deterministic, LLM-free
│             ai_copilot    ◄── narration only
│             bmoni_client  ◄── the ONLY holder of x-api-key
│             decision_service  │
│  models/    SQLAlchemy        │
└──────┬────────────────┬───────┘
       │                │
       ▼                ▼
┌──────────────┐  ┌──────────────────┐   ┌──────────────┐
│ PostgreSQL   │  │ BMONI Embedded   │   │  Anthropic   │
│ users        │  │ sandbox          │   │  Messages    │
│ wallets      │  │ embedded-dev     │   │  API         │
│ transactions │  └──────────────────┘   └──────────────┘
│ obligations  │
│ ai_decision  │
│      _log    │
└──────────────┘
```

## Where each concern lives

| Concern | Location | Why there |
|---|---|---|
| Wallet private key | Android Keystore, on device | Only the user should be able to move their money |
| BMONI `x-api-key` | `kopa_backend` env | A key shipped in an app is a published key |
| Anthropic key | `kopa_backend` env | Same |
| Financial calculation | `safety_engine.py` | Must be deterministic and auditable |
| AI | `ai_copilot.py` | Explanation is the only safe job for a model here |
| Obligations & history | PostgreSQL | BMONI is a rail, not KOPA's ledger |
| User confirmation | Flutter, post-safety-screen | The decision belongs to the user |

## The request that defines the product

`POST /decisions/evaluate` — everything KOPA is, in one call.

```
1. gather   balance    ← BMONI (or seeded, in demo mode)
            obligations ← PostgreSQL
            history     ← PostgreSQL
                │
2. decide   safety_engine.evaluate_transaction(...)
            pure function · no I/O · no clock read · Decimal money
                │  SafetyAssessment (verdict + every figure)
                │
3. narrate  ai_copilot.explain(justification)
            receives the numbers · writes prose · cannot raise
                │
4. record   ai_decision_log  (verdict + figures + prose)
                │
5. respond  DecisionResponse
```

Steps 3 and 4 cannot affect step 2. If the model fails, step 3 returns a
deterministic template. If the audit write fails, it is logged and the user
still gets their verdict — an audit failure must not deny someone a safety
check.

## Design decisions worth defending

**The engine reads no clock.** `evaluate_transaction` requires an explicit
`as_of` date. A pure function that calls `date.today()` is not pure, and a
decision that cannot be recomputed cannot be audited. Every test pins the date,
so the suite is stable indefinitely.

**Money is `Decimal` everywhere, and crosses the wire as strings.** Floats are
never used for currency. The JSON carries `"17500.00"`, not `17500.0`, and
Flutter formats that string without parsing it back to a number — so the figure
the user reads is bit-for-bit the figure the engine computed.

**The obligation horizon is fixed at 30 days, not scaled to the runway.** An
early version widened the horizon with the runway; a large balance then
produced a runway of years and pulled next year's rent into today's decision,
making every healthy account look encumbered. A caught bug, and the reason
`test_obligations_beyond_the_horizon_are_ignored` exists.

**Obligations are settled in due-date order.** Each is tested against the
running total of everything due before it, so KOPA identifies *which* specific
commitment breaks rather than reporting a vague shortfall.

**Verdicts are additive.** Every rule is evaluated and all reasons are
collected; the most severe wins. A transfer can be unsafe for three independent
reasons and the user is shown all three — which is both more honest and more
persuasive than a single flag.

**The safety check is on every path to signing.** It is not a setting, not
dismissible, and not skippable. That is the product.

## Data model

```
users ──┬── wallets ──── transactions
        ├── obligations
        └── ai_decision_log ──(nullable)── transactions
```

Deliberately absent: private keys, PINs, KYC document images, BVN, NIN. See
[security.md](security.md).

`ai_decision_log.numeric_justification` is JSONB holding the engine's exact
output. Combined with a deterministic engine, this makes every past decision
reproducible and checkable.

## Failure behaviour

| Failure | Effect |
|---|---|
| Anthropic down / unfunded | Deterministic explanation, user told |
| BMONI balance unreachable | Seeded balance, labelled as demo |
| PostgreSQL down | Demo-mode decisions still work; audit log skipped |
| Sandbox down mid-demo | `KOPA_DEMO_MODE=true`, engine and AI still real |
| Wrong PIN | Inline error, retry without leaving the screen |
| Signing payload not ready | Retried with backoff, then a clear message |

The pattern throughout: degrade the periphery, never the safety decision.
