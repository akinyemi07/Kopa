# KOPA — Step-by-Step Build Guide

How to use this document:
- Each step has an **Action** (what we're accomplishing) and a **Prompt** (copy-paste this into your AI coding assistant, e.g. Claude Code, in your project directory).
- Run steps **in order**. Don't skip ahead — later prompts assume earlier ones are done.
- After each prompt runs, actually verify the exit criteria before moving on. Don't trust "looks done."
- Where a step depends on BMONI-specific details (endpoint names, SDK method signatures, sandbox credentials), the prompt explicitly tells the assistant to consult BMONI's real documentation rather than guessing — because I don't have BMONI's actual API reference in front of me, and neither should your coding assistant pretend to.

---

## PHASE 0 — Environment & Scaffolding

### Step 1: Confirm tooling
**Action:** Make sure Flutter, Python, and PostgreSQL are installed and working before writing any app code — a broken toolchain is the worst thing to discover at hour 2.

**Prompt:**
```
Check that Flutter (stable channel), Dart, Python 3.11+, and PostgreSQL are
installed on this machine. Run `flutter doctor`, `python3 --version`, and
`psql --version`. Report any missing pieces or setup issues clearly, and
fix anything you can (e.g. missing Flutter dependencies) before proceeding.
Do not create any project files yet — this step is verification only.
```

### Step 2: Scaffold the Flutter app
**Action:** Create the mobile app project skeleton.

**Prompt:**
```
Create a new Flutter app called "kopa_app" targeting Android 24+ and iOS 13+.
Set up a clean folder structure: /lib/screens, /lib/services, /lib/models,
/lib/widgets. Add a basic MaterialApp with a placeholder home screen that
just says "KOPA" so we can confirm the app builds and runs on a simulator
or emulator. Do not add any BMONI or backend dependencies yet.
```

### Step 3: Scaffold the FastAPI backend
**Action:** Create the backend project skeleton, separate from the Flutter app.

**Prompt:**
```
Create a new Python project called "kopa_backend" using FastAPI. Set up a
clean structure: /app/main.py, /app/api (routers), /app/models (DB models),
/app/services (business logic), /app/core (config/secrets loading). Add a
single health check endpoint GET /health that returns {"status": "ok"}.
Use a .env file (gitignored) for configuration, loaded via pydantic-settings
or python-dotenv. Confirm the server runs locally with uvicorn.
```

### Step 4: Stand up PostgreSQL
**Action:** Get a local database running and connected to the backend.

**Prompt:**
```
Set up a local PostgreSQL database called "kopa" for the kopa_backend
project. Add SQLAlchemy (or SQLModel) and Alembic for migrations. Create
the initial empty migration and confirm the backend can connect to the
database on startup — add a startup check that fails loudly if the DB
connection is broken. Do not create any tables yet beyond a placeholder
to confirm connectivity.
```

---

## PHASE 1 — Milestone 0: "It's Alive" (BMONI wallet + one sandbox transaction)

This is the highest-risk phase. Everything else is worthless until this works.

### Step 5: Add the BMONI Flutter SDK
**Action:** Integrate BMONI's official embedded SDK into the Flutter app.

**Prompt:**
```
I need to integrate BMONI's official embedded Flutter SDK into the
kopa_app project. Before writing any code, find and read BMONI's actual
Flutter SDK documentation (package name, installation instructions,
initialization requirements, minimum SDK versions). Do not guess at
package names or API surface — if you cannot find the real documentation,
stop and tell me what you need from me (e.g. a doc link, API credentials,
or sandbox account details) rather than fabricating an integration.

Once you have real documentation: add the SDK dependency, initialize it
in the app (using sandbox/test credentials I will provide), and add a
screen that shows the SDK's initialization status (success/failure) so
we can visually confirm it's wired up correctly.
```

*(Note: have your BMONI sandbox API credentials and a link to their Flutter SDK docs ready before running this step — the assistant should ask for them if it doesn't have them.)*

### Step 6: Create a wallet via the SDK
**Action:** Provision a wallet for a test user from inside the app.

**Prompt:**
```
Using the BMONI embedded Flutter SDK we just integrated, add a "Create
Wallet" screen and flow. On button press, call the SDK's wallet creation/
provisioning method (consult the real SDK docs for the exact method name
and required parameters — do not guess). Display the resulting wallet
reference/ID on screen along with any status returned. Handle and display
errors clearly rather than failing silently.
```

### Step 7: Complete sandbox KYC
**Action:** Run the sandbox KYC flow required to activate the wallet.

**Prompt:**
```
Add the KYC step required by BMONI to activate a wallet in sandbox mode.
Consult BMONI's documentation for what sandbox KYC requires (it may be a
simplified/mock flow in sandbox — confirm this rather than assuming).
Build a simple form screen for any required fields, submit via the SDK
or API as documented, and show the resulting KYC status on screen.
```

### Step 8: Fund the sandbox wallet
**Action:** Get test funds into the wallet so a transaction is possible.

**Prompt:**
```
Add a "Fund Wallet" action that uses BMONI's sandbox funding mechanism
(check their docs for how sandbox funding works — it may be a faucet-style
endpoint or a mock rail). After funding, display the updated wallet
balance on screen, fetched fresh from the SDK or API rather than assumed.
```

### Step 9: Execute one real sandbox transaction
**Action:** The single most important step in this entire build — prove the full signing + submission chain works.

**Prompt:**
```
Add a "Send Test Transaction" screen: a simple form (amount, recipient
reference) that, on submit, uses the BMONI embedded SDK to sign the
transaction on-device and submit it to BMONI's sandbox. Display the
resulting transaction ID/reference and status on screen. Log the full
request/response (excluding any secrets) to the console for debugging.

After this runs successfully, tell me explicitly: "Milestone 0 complete —
transaction ID is [X]." If it fails, do not move on — help me debug the
SDK integration until a real transaction ID is produced.
```

**⏸ CHECKPOINT: Do not proceed past this point until Step 9 has actually produced a transaction ID from BMONI's sandbox. If you're stuck here past hour 3–4, stop all other planning and debug this exclusively.**

---

## PHASE 2 — Milestone 1: Backend Becomes the Brain

### Step 10: Move BMONI's API key to the backend
**Action:** Establish the security boundary — no secrets in the Flutter app.

**Prompt:**
```
Set up secure storage of the BMONI x-api-key in kopa_backend only, via
the .env file, never committed to git and never referenced anywhere in
the kopa_app Flutter project. Add a backend service module
(app/services/bmoni_client.py) that wraps calls to BMONI's server API
(for anything that does NOT require on-device signing, e.g. balance
lookups, transaction status/history) using this key in request headers.
Consult BMONI's server API docs for exact endpoint paths and auth header
format — do not guess. Add one working example call: fetch wallet balance
by wallet reference.
```

### Step 11: Define the database schema
**Action:** Create the tables that will hold users, wallets, transactions, and AI decisions.

**Prompt:**
```
In kopa_backend, define SQLAlchemy models and an Alembic migration for:
- users (id, bmoni_user_ref, kyc_status, created_at)
- wallets (id, user_id FK, bmoni_wallet_ref, status)
- transactions (id, wallet_id FK, bmoni_txn_ref, amount, direction,
  counterpart, status, created_at)
- obligations (id, user_id FK, description, amount, due_date)
- ai_decision_log (id, user_id FK, transaction_id FK nullable, verdict,
  numeric_justification JSONB, ai_explanation_text, created_at)

Run the migration against the local kopa database and confirm all tables
exist with correct types and foreign keys.
```

### Step 12: Build the core API endpoints
**Action:** Expose the endpoints the Flutter app will actually call.

**Prompt:**
```
In kopa_backend, implement these endpoints, backed by the models from
Step 11 and the BMONI client from Step 10:
- POST /users — create a KOPA user record
- POST /wallets/kyc — record KYC submission/status
- POST /wallets/fund — record a funding event (relay to BMONI if the
  sandbox funding mechanism is server-side; otherwise just record it)
- GET /wallets/{id}/balance — fetch live balance via the BMONI client
- POST /transactions — record a transaction that was signed and submitted
  from the Flutter app, and reconcile its status via BMONI's API
- GET /transactions — return transaction history for a user

Write basic request/response validation with Pydantic schemas. Add a
short README section documenting each endpoint's expected payload.
```

### Step 13: Rewire Flutter to talk to the backend
**Action:** Replace any direct-to-BMONI calls in Flutter (except signing) with calls to KOPA's own API.

**Prompt:**
```
Refactor kopa_app so that all wallet/transaction data (balance, history,
KYC status) is fetched from the kopa_backend API endpoints built in
Step 12, NOT directly from BMONI's server API. The ONLY thing that should
still go directly through the BMONI SDK on-device is transaction signing
itself (since the private key never leaves the device). After signing,
the app should submit the signed transaction to BMONI via the SDK as
before, then immediately POST the result to kopa_backend's
POST /transactions endpoint so it gets recorded and reconciled.

Add a Dart service class (lib/services/kopa_api.dart) that centralizes
all HTTP calls to the backend. Confirm the app still successfully
completes a full send-transaction flow end to end through this new path.
```

**⏸ CHECKPOINT: Confirm no BMONI x-api-key appears anywhere in the Flutter codebase (grep for it). Confirm the app works purely through kopa_backend for everything except signing.**

---

## PHASE 3 — Milestone 2: Deterministic Safety Engine

### Step 14: Build the safety calculation logic
**Action:** Write the pure-math engine that decides "safe / caution / unsafe" — no AI involved yet.

**Prompt:**
```
In kopa_backend, create app/services/safety_engine.py with a function
evaluate_transaction(current_balance, obligations, proposed_amount) that:
- Computes resulting_balance = current_balance - proposed_amount
- Computes a "runway" estimate: how many days of typical spending the
  resulting balance would cover (use average of recent transaction
  amounts from history as the daily spend estimate; if no history exists,
  accept a manual daily_spend_estimate parameter)
- Flags obligations due before the runway runs out
- Returns a verdict: "safe", "caution", or "unsafe", plus a structured
  dict of the numbers used to reach that verdict (resulting_balance,
  runway_days, at_risk_obligations, pct_of_balance_used)

Write unit tests covering: plenty of buffer (safe), tight buffer
(caution), would go negative or breaks an obligation (unsafe). Do not
involve any LLM or external API in this file — it must be pure,
deterministic, testable logic.
```

### Step 15: Expose the safety engine via API
**Action:** Let the app request a verdict before a transaction happens.

**Prompt:**
```
Add POST /decisions/evaluate to kopa_backend, accepting
{user_id, proposed_amount, counterpart, type}. It should fetch the
user's current balance (via the BMONI client) and obligations (from the
database), call evaluate_transaction() from Step 14, log the result to
ai_decision_log, and return the verdict + numeric_justification as JSON.
Do not add any AI-generated text yet — return the raw structured verdict
only. Test this endpoint with at least three scenarios matching Step 14's
test cases.
```

### Step 16: Surface the verdict in the app
**Action:** Show the user a safety check before they confirm a transaction.

**Prompt:**
```
In kopa_app, before the "Send Transaction" screen actually submits (from
Step 9's flow), call POST /decisions/evaluate first and show the verdict
(safe/caution/unsafe) plus the key numbers (resulting balance, runway
days) in a confirmation dialog. Let the user proceed or cancel. Only
continue to on-device signing and submission if they confirm. Style this
clearly: green for safe, yellow for caution, red for unsafe.
```

---

## PHASE 4 — Milestone 3: AI Co-Pilot Layer

### Step 17: Add the LLM narration layer
**Action:** Turn the raw verdict into a natural-language explanation — without letting the LLM invent numbers.

**Prompt:**
```
In kopa_backend, add app/services/ai_copilot.py that takes the verdict +
numeric_justification dict from the safety engine and calls an LLM
(Anthropic API — use the Claude Python SDK) to generate a short, plain-
language explanation and recommendation. The prompt to the LLM must:
- Explicitly include the exact numbers computed by the safety engine
- Explicitly instruct the model to only reference these provided numbers
  and never calculate or estimate new financial figures itself
- Ask for a short (2-4 sentence) conversational explanation plus a clear
  recommendation

Wire this into POST /decisions/evaluate so the response now includes
both the raw verdict/numbers AND the ai_explanation text. Store the
explanation in ai_decision_log alongside the numeric justification.
```

### Step 18: Add conversational follow-up
**Action:** Let the user ask "what if" questions that re-run the deterministic engine.

**Prompt:**
```
Add a simple chat-style interface in kopa_app for the decision screen:
after showing the initial verdict, let the user type follow-up questions
like "what if I wait until Friday?" or "what if I only send half?". In
kopa_backend, add POST /decisions/followup that takes the original
context plus the user's free-text question, uses the LLM to extract
adjusted parameters (e.g. a different amount or a different date) from
the question, re-runs evaluate_transaction() with those adjusted
parameters, and returns a new verdict + explanation using the same
narrate-don't-calculate pattern from Step 17.
```

---

## PHASE 5 — Milestone 4: Merchant-Decision Mode

### Step 19: Add merchant-decision context
**Action:** Build the second target direction — safety framing for paying a merchant/counterpart.

**Prompt:**
```
Extend the safety engine and /decisions/evaluate endpoint to accept a
"merchant" transaction type. When type is "merchant", pull additional
context from transaction history: has this counterpart been paid before,
how often, and average amount. Add this to the numeric_justification
payload (e.g. is_first_time_counterpart, payment_frequency). Update the
AI narration prompt from Step 17 to mention this context when relevant
(e.g. "this is your first payment to this recipient" or "this matches
your usual monthly payment to them").
```

### Step 20: Build the merchant-decision screen
**Action:** Give this mode its own clear UI moment in the app, distinct from the personal-transaction flow.

**Prompt:**
```
In kopa_app, add a "Pay a Merchant" flow, visually distinct from the
personal transaction flow, that collects a merchant/counterpart
reference and amount, calls /decisions/evaluate with type="merchant",
and displays the verdict plus counterpart-specific context (first-time
vs. recurring, frequency) before allowing the user to confirm and sign.
```

---

## PHASE 6 — Milestone 5: Demo Hardening

### Step 21: Build a demo fallback mode
**Action:** Protect the demo from live sandbox flakiness.

**Prompt:**
```
Add a "demo mode" flag to kopa_backend that, when enabled, returns
cached/seeded realistic responses for balance, history, and BMONI
transaction submission instead of hitting the live sandbox — while
still running the real safety engine and real LLM narration logic on
top of that seeded data. Add a toggle (env variable) to switch between
live and demo mode without code changes, so we can flip to demo mode
instantly if the live sandbox has issues during judging.
```

### Step 22: Seed realistic demo data
**Action:** Make sure the demo tells a clear story.

**Prompt:**
```
Write a database seed script for kopa_backend that creates one demo user
with: a wallet with a realistic balance, 15-20 days of varied transaction
history (including at least one recurring monthly payment to the same
counterpart), and 1-2 upcoming obligations. Ensure this seed data is
specifically crafted so that: one proposed transaction amount clearly
triggers a "safe" verdict, and another clearly triggers "unsafe" or
"caution" — so both states are demonstrable live without luck.
```

### Step 23: Final UI polish pass
**Action:** Clean up the happy path for the screens judges will actually see.

**Prompt:**
```
Review the full user flow in kopa_app end to end: onboarding → wallet
creation → KYC → funding → personal transaction with safety check →
merchant payment with safety check → transaction history. Fix any
obviously broken layouts, add loading states for all network calls,
and make sure error states are handled gracefully (no raw stack traces
or blank screens). Do not add new features — this pass is polish only.
```

### Step 24: Dry-run the demo script
**Action:** Rehearse the exact sequence you'll show judges.

**Prompt:**
```
Based on the seed data from Step 22, write out a step-by-step demo script
(as a markdown file, demo_script.md) listing the exact screens to tap
through, in order, to show: wallet creation, a safe transaction, an
unsafe transaction (with the AI explanation clearly visible), and the
merchant-decision mode. Include the exact numbers expected at each step
so we can catch any discrepancy before judging.
```

---

## Summary: What "Done" Looks Like

By the end of Step 24, you should have:
- A Flutter app that creates a real BMONI sandbox wallet, completes KYC, funds itself, and executes signed transactions on-device.
- A FastAPI backend that holds all secrets, exposes clean endpoints, and reconciles transaction state with BMONI.
- A deterministic safety engine producing auditable numeric verdicts.
- An LLM layer that explains those verdicts in plain language without inventing numbers.
- A merchant-decision mode addressing the second hackathon target direction.
- A demo-safe fallback mode and a rehearsed script.

If you run out of time, cut from the bottom of this list upward — never skip Phase 1 (Milestone 0). A working wallet-to-transaction chain with no AI beats a beautiful AI chat layer with no working BMONI integration.
