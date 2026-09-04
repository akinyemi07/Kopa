# BMONI integration

Every endpoint and behaviour below was verified against the live sandbox at
`https://embedded-dev.bmoni.com` on 2026-09-04. Nothing here is transcribed
from documentation without being run.

## Verified milestone

Real values produced by the M0a spike (`scripts/bmoni_spike.py`):

| Stage | Result |
|---|---|
| `POST /v1/users` | `bmoniUserId` `2633ed62-0938-4666-8604-8565c712ddf5` |
| Owner-proof challenge | `challengeId` issued, EIP-191 message returned |
| EIP-191 signature | **accepted** |
| `POST /smart-wallets/create-managed` | wallet deployed, `isActive: true` |
| Smart wallet address | `0xbDD35d2daA61866c1cAa085A93e2B46eAE669768` (NGN) |
| `GET /kyc/bvn-lookup/95888168924` | resolves → Bunch Dillon, Lagos |
| `POST /onboarding/start-nigeria` | `200` — `hasBvn: true`, `hasLocalWallet: true` |
| `GET /smart-wallets/account/balances` | `NGN "0"` (awaiting manual token credit) |

## The lifecycle, and where KOPA sits in it

BMONI's six stages run in a fixed order; each depends on the one before.

```
1. user      POST /v1/users                         → bmoniUserId
2. wallet    owner-proof-challenge → sign → create-managed
3. KYC       PATCH /kyc
4. rail      POST /onboarding/start-nigeria         → NGN active
5. fund      (manual test-token credit in sandbox)
6. move      proposal → approve → sign-payload → sign
                              ▲
                    KOPA'S SAFETY CHECK GOES HERE
```

Stage 6 is why KOPA is a BMONI product rather than an app that happens to use
BMONI. Because creating a proposal is separate from signing it, there is a real
gap between *intent* and *settlement* — and that gap is exactly where a safety
check belongs. On a rail where sending is one atomic call, there is nowhere to
stand.

## Who calls what

The division is strict and is the core of KOPA's security posture.

### Device → BMONI SDK (never the network)

Only three operations, all local to the device:

| Operation | SDK call |
|---|---|
| Generate the owner keypair | `BmoniEmbeddedSdk.initWallet()` |
| Sign the owner-proof challenge | `signMessage(message, pin:)` |
| Sign a transfer proposal | `signTransactionHash(hash, pin:)` |

The private key is generated inside the Android Keystore, encrypted with a
platform-managed wrapping key, and zeroized in RAM. It never leaves the device.
KOPA's backend never sees it, and neither does BMONI.

### Device → KOPA backend (HTTPS, no credentials)

The app holds no API keys of any kind. It sends the wallet address and the two
signatures, and receives balances, verdicts and proposals.

### KOPA backend → BMONI (`x-api-key`)

Everything else. The partner key exists only in `kopa_backend`'s environment.

```
POST /v1/users
POST /v1/users/{id}/smart-wallets/owner-proof-challenges
POST /v1/users/{id}/smart-wallets/create-managed
PATCH /v1/users/{id}/kyc
GET  /v1/users/{id}/kyc/bvn-lookup/{bvn}
GET  /v1/users/{id}/kyc/readiness
POST /v1/users/{id}/onboarding/start-nigeria
GET  /v1/users/{id}/onboarding/status
GET  /v1/users/{id}/smart-wallets/account/wallets
GET  /v1/users/{id}/smart-wallets/account/balances
POST /v1/users/{id}/smart-wallets/{walletId}/proposals
POST /v1/users/{id}/smart-wallets/proposals/{id}/approve
GET  /v1/users/{id}/smart-wallets/proposals/{id}/sign-payload
POST /v1/users/{id}/smart-wallets/proposals/{id}/sign
```

## The full send flow

```
 user enters amount + recipient
            │
            ▼
 POST /decisions/evaluate  ──────────────┐
   backend: GET balances (BMONI)         │  ← NOTHING HAS MOVED
   backend: obligations + history (DB)   │
   backend: safety_engine (deterministic)│
   backend: ai_copilot (narration)       │
            │                            │
            ▼                            │
   SAFETY SCREEN — user decides ─────────┘
            │  proceeds
            ▼
 POST /transactions
   backend → BMONI: create proposal
   backend → BMONI: approve
   backend → BMONI: GET sign-payload  → hashToSign
            │
            ▼
 PIN entry → SDK.signTransactionHash(hashToSign, pin)   ← ON DEVICE
            │
            ▼
 POST /transactions/sign
   backend → BMONI: submit signature
   backend → BMONI: poll proposal status
            │
            ▼
 PENDING_SIGNATURES → COMPLETED
```

## The two signatures

The single most common way to stall a BMONI integration. They are different
methods over different payloads, and the error on getting it wrong does not say
which mistake was made.

| | Owner proof (wallet creation) | Proposal (transfer) |
|---|---|---|
| What is signed | The challenge **text** | A 32-byte **digest** |
| EIP-191 prefix | **Yes** | **No** |
| SDK call | `signMessage()` | `signTransactionHash()` |
| Server equivalent | `Account.sign_message(encode_defunct(...))` | `Account.unsafe_sign_hash(...)` |

Using `signMessage` for a proposal produces a signature that recovers to a
different address, and BMONI rejects it.

## Documentation defects found

Three, all found by probing the live API rather than trusting the docs. All are
worked around in `app/services/bmoni_client.py` with inline notes.

**1. `PATCH /kyc` rejects `addressDetails`.** The published quickstart shows it;
the live API returns `400 — property addressDetails should not exist`. The
accepted top-level properties, mapped against the live NestJS validator, are:

```
personalInfo, address, employment, sourceOfFunds, identificationNumbers
```

**2. `identificationNumbers` must be an array.** Sending it as an object
returns `400 — identificationNumbers must be an array`.

**3. `BmoniSignerErrorCode` is not a Dart enum.** The Flutter SDK docs imply
an enum; it is a class of `static const int` values, and `BmoniSignerException.errorCode`
is an `int`. There is no `walletNotFound` member. Code written against the
documented shape does not compile.

## Sandbox constraints encountered

**Both test personas were already registered.** The partner key published in
BMONI's quickstart is shared by every hackathon participant, so
`POST /v1/users` returned `409 — User already exists with this phoneNumber`
for both `+2348000000000` and `+2348000000001`.

Resolution: identity verification matches on **name + BVN**, not phone. KOPA
registers the persona's name and BVN against a freshly generated phone number.
Confirmed by observing that other participants had done the same. The BVN
look-up resolves correctly against this user.

**Funding is manual.** Sandbox wallets start empty and there is no faucet
endpoint — BMONI credits ₦1,000 / $10 by hand after a form submission, within
about one business day. A settled transfer therefore depends on that credit
landing. Everything up to and including a real on-device signature over a real
proposal works without it.

**Security observation.** `GET /v1/users` on the shared key returns every
participant's name, email and phone number. Sandbox-only and no action was
taken beyond confirming the persona collision, but it is worth BMONI's
attention.

## Demo mode

When `KOPA_DEMO_MODE=true`, balance and history come from seeded synthetic data
instead of BMONI, so sandbox instability cannot break a demonstration. The
safety engine and the AI layer still run for real.

Demo transactions are distinguishable at every layer, by design:

- `bmoni_txn_ref` is `NULL` and status is `DEMO` in the database
- the API returns `is_demo: true`
- the UI shows a **DEMO DATA** chip and states that no money moved

A demo transfer is never presented as a real BMONI transaction.
