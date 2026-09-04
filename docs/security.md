# Security and privacy

## The boundary

KOPA has two secrets that matter, and they live in different places on purpose.
Neither component holds both.

```
┌──────────────────────────────┐
│  Device (Flutter app)        │
│                              │
│  ✔ wallet private key        │  Android Keystore / iOS Secure Enclave
│  ✔ PIN digest (PBKDF2)       │
│  ✘ BMONI partner key         │  ← never present
│  ✘ Anthropic key             │  ← never present
└──────────────────────────────┘
              │ HTTPS, no credentials
              ▼
┌──────────────────────────────┐
│  kopa_backend                │
│                              │
│  ✔ BMONI x-api-key           │  environment only
│  ✔ Anthropic key             │  environment only
│  ✘ wallet private key        │  ← never present, by construction
│  ✘ user PIN                  │  ← never transmitted
└──────────────────────────────┘
```

**A compromised phone cannot spend other users' money** — it holds one wallet
key and no partner credential.

**A compromised backend cannot move funds** — it can create and approve
proposals, but a proposal without a device signature does nothing. Settlement
requires the user's device and their PIN.

That is not an accident of design; it is the reason the proposal → approve →
sign flow is used as-is rather than shortcut.

## Verifying it yourself

```bash
grep -rn "x-api-key\|BMONI_API_KEY\|ANTHROPIC_API_KEY\|sk-ant-" kopa_app/
```

Result, as of the last audit — a single hit, and it is a comment in
`lib/core/api_client.dart` stating that no such key exists:

```
kopa_app/lib/core/api_client.dart:7:
    // base URL, no x-api-key, and no Anthropic key anywhere in this project —
```

No credential value, no BMONI base URL, and no BMONI client exist in the app.
Across the whole repository, `sk-ant-` returns nothing.

The app has no BMONI base URL and no BMONI client. Its only network dependency
is `KOPA_API_BASE_URL`, which is a build-time define, not a secret.

## Secrets handling

- All credentials load from the environment via `pydantic-settings`
  (`app/core/config.py`). Nothing is hardcoded.
- `.env` is gitignored and never committed. `.env.example` ships with an
  **empty** `BMONI_API_KEY` — deliberately not pre-filled, even though BMONI
  publishes a shared sandbox key, because a working credential does not belong
  in version control.
- `/health` returns `bmoni_configured: true/false` and never the key itself.
- No secret is logged. `bmoni_client._redact()` strips `x-api-key`,
  `signature`, `ownerProofSignature`, `photo`, `bvn` and `nin` from anything
  written to a log, and truncates long blobs.

## What KOPA stores, and what it deliberately does not

**Stored** (`kopa_backend`, PostgreSQL):

| Data | Why |
|---|---|
| `bmoni_user_ref`, `bmoni_wallet_ref` | opaque references, needed to call BMONI |
| Smart wallet + owner **addresses** | public on-chain data, not secret |
| Transaction amounts, counterparts, dates | required for runway and counterpart context |
| Obligations | required for the safety verdict |
| `ai_decision_log` | audit trail of every decision |

**Not stored, anywhere:**

- Wallet private keys — they exist only inside the device's secure element
- PINs — the SDK holds a PBKDF2-HMAC-SHA256 digest, on device
- KYC document images — passed to BMONI, never retained by KOPA
- BVN or NIN — submitted to BMONI in transit, not persisted in KOPA's database

The BVN is a Nigerian national financial identifier. KOPA touches it exactly
once, to activate the rail, and does not keep it.

## Data sent to Anthropic

Only the aggregate figures needed to write an explanation: balance, amount,
resulting balance, runway, percentage, and obligation descriptions.

Never sent: BVN, NIN, phone number, email, wallet address, transaction
identifiers, or user id.

Prompts are not logged. Only the returned explanation is stored, next to the
numeric justification that produced it.

## Input validation

- Every request body is a Pydantic schema with explicit constraints —
  `proposed_amount` is `gt=0`, addresses match `^0x[0-9a-fA-F]{40}$`,
  signatures match `^0x[0-9a-fA-F]{130}$`, BVN is `^\d{11}$`.
- The safety engine validates independently of the API layer and raises
  `SafetyEngineError` on a non-positive amount, a negative balance, or a
  non-numeric input. It does not trust its caller.
- SQL injection is structurally excluded: all database access is through
  SQLAlchemy's expression language with bound parameters. No string-built SQL
  exists in the codebase.
- Money is `Decimal` end to end, and `NUMERIC` in Postgres. Floats are never
  used for currency.

## Error handling

Users see sentences; logs get the detail.

`bmoni_client._friendly_message()` maps upstream failures to user-facing text —
a `403` becomes *"KOPA could not authenticate with BMONI"*, not a stack trace.
Raw response bodies, status codes and exception types stay in the server log.

The app never renders a raw API body. `ApiException` carries a human message
and a retryability hint.

## Financial-safety guardrails

- KOPA never blocks a transfer. "Send anyway" is always present.
- KOPA never claims a guarantee. The word "guarantee" is absent from the UI and
  is an explicit rejection trigger in AI output validation.
- Every verdict is qualified: *"Based on the information available to KOPA."*
- Demo transactions are distinguishable at every layer — `NULL` BMONI
  reference, `DEMO` status, `is_demo: true`, and a labelled UI — so a seeded
  transfer can never be mistaken for a real one.

## Accessibility as a safety property

A safety warning that a user cannot perceive is not a safety warning.

Verdicts carry **four** independent signals — colour, icon, text label, and a
sentence. Removing colour entirely leaves the verdict unambiguous, which
matters because red/green is the most commonly affected pair in colour-vision
deficiency and is exactly what a naive safe/unsafe design would reach for.

Additionally: `Semantics` labels on the verdict, every figure row, and each
at-risk obligation; `liveRegion` on verdicts and errors so screen readers
announce them on arrival; full-sentence semantic labels (`"Balance afterwards:
₦17,500.00"`) rather than orphaned numbers; and standard touch target sizes.

## Known limitations

Stated plainly rather than omitted.

- **No user authentication yet.** The API identifies users by id without a
  session token. Acceptable for a sandbox prototype; a production deployment
  needs auth on every user-scoped route before it holds real data.
- **The shared sandbox key is public.** BMONI publishes it, and
  `GET /v1/users` on it exposes every participant's name, email and phone
  number. Sandbox-only, and reported rather than exploited — but a private key
  is required before production.
- **No rate limiting** on the backend.
- **HTTP in local development.** TLS is required for any real deployment.
- **No webhook signature verification** — KOPA polls rather than subscribing,
  so no webhook endpoint is exposed. If one is added, BMONI's signature
  verification must be implemented before it is trusted.
