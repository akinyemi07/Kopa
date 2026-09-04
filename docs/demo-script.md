# KOPA — demo script

Roughly 4 minutes. Every figure below is produced by the deterministic engine
and pinned by `kopa_backend/tests/test_demo_scenarios.py`, so the demo and this
document cannot drift apart. If a number here is wrong, that test fails.

## Setup

```bash
# Terminal 1 — backend in demo mode (no database, no BMONI needed)
cd kopa_backend
KOPA_DEMO_MODE=true ../.venv/Scripts/python.exe -m uvicorn app.main:app --port 8000

# Terminal 2 — app
cd kopa_app
flutter run
```

Confirm before starting:

```bash
curl -s localhost:8000/health
```

Expect `"status":"ok"` and `"demo_mode":true`.

### The demo persona

Amaka is a fictional trader in Lagos. Her figures are synthetic.

| | |
|---|---|
| Wallet balance | **₦47,500.00** |
| Spending history | 18 days, 23 transactions |
| Typical daily spend | **₦1,397.22** (derived, not assumed) |
| Rent | **₦25,000** due in 6 days |
| Data subscription | **₦5,000** due in 12 days |
| Regular vendor | Mama Nkechi Stores — 3 payments, avg ₦1,800 |

---

## 1. The problem (20 seconds)

> "Amaka has ₦47,500. Her wallet app will happily let her send ₦30,000 right
> now — the money is there, the transfer clears.
>
> But her rent is ₦25,000 and it's due Thursday. Every wallet in the market
> answers 'can this go through?'. None of them answer 'should it?'"

Show the home screen: balance and upcoming commitments together.

---

## 2. Scenario A — a safe transfer (45 seconds)

**Send money → ₦3,000 → Mama Nkechi Stores → Check before sending**

Expected, exactly:

| Field | Value |
|---|---|
| Verdict | **Looks manageable** (green, ✓ icon) |
| Balance now | ₦47,500.00 |
| Sending | − ₦3,000.00 |
| Balance afterwards | **₦44,500.00** |
| Share of balance | **6.3%** |
| How long that lasts | **about 31 days** |
| At risk | *(none shown)* |
| Recipient | 3 previous payments, averaging ₦1,800.00 |

> "KOPA says this is fine, and shows why: ₦44,500 left, about a month of
> cover, rent still safe. It also recognises the recipient — she shops here
> regularly."

---

## 3. Scenario B — the one that matters (75 seconds)

Back, then **₦30,000 → QuickLoan NG → Check before sending**

Expected, exactly:

| Field | Value |
|---|---|
| Verdict | **Not recommended** (red, ⚠ icon) |
| Balance afterwards | **₦17,500.00** |
| Share of balance | **63.2%** |
| How long that lasts | **about 12 days** |
| At risk | **Rent ₦25,000.00** and **Data subscription ₦5,000.00** |
| Recipient | *"first time KOPA has seen you pay QuickLoan NG"* |

> "This is the moment. The transfer is affordable — she has the money. But
> ₦17,500 does not cover ₦25,000 of rent due in six days.
>
> KOPA is flagging three independent things: the rent would break, it's 63% of
> her balance, and she has never paid this recipient before. That last signal
> is how a lot of money is actually lost."

**Point out the buttons:** "Don't send" is primary; "Send anyway" is still
there.

> "KOPA advises. It never blocks. It's her money — the goal is an informed
> decision, not an enforced one."

---

## 4. Responsible AI — the question judges will ask (45 seconds)

> "The obvious question: how do I know the AI didn't make those numbers up?
>
> Because it never saw them until they were final. A deterministic Python
> engine computes every figure and reaches the verdict. The model receives
> those numbers and writes two sentences. It cannot calculate, and its output
> never re-enters the decision."

If asked to prove it, run:

```bash
cd kopa_backend
../.venv/Scripts/python.exe -m pytest tests/test_ai_copilot.py -q -k contradicting -v
```

> "That test feeds the AI layer a model response saying 'this is safe, there's
> no risk' against an unsafe verdict — and asserts the user is shown the
> deterministic explanation instead. The model is not permitted to overrule the
> maths."

**Optional — kill the AI live:**

```bash
# restart with no key
ANTHROPIC_API_KEY= KOPA_DEMO_MODE=true ../.venv/Scripts/python.exe -m uvicorn app.main:app --port 8000
```

Re-run Scenario B. Same verdict, same numbers, explanation now generated
deterministically, and the UI says so honestly.

> "AI failure degrades the explanation. It never degrades the safety decision."

---

## 5. BMONI (45 seconds)

> "The wallet isn't decoration. BMONI gives us an on-device Ethereum key in the
> Android Keystore, a deployed smart wallet on the Naira stablecoin rail, and —
> critically — a transfer flow that separates *proposing* from *signing*.
>
> That gap is where KOPA lives. On a rail where sending is one atomic call,
> this product has nowhere to stand."

Proceed through **Send anyway → PIN → sign**.

> "The PIN unlocks a key that never leaves the phone. Our backend holds the
> BMONI partner key; the device holds the wallet key. Neither has both."

Show the verified sandbox chain (`docs/bmoni-integration.md`):

```
bmoniUserId    2633ed62-0938-4666-8604-8565c712ddf5
smart wallet   0xbDD35d2daA61866c1cAa085A93e2B46eAE669768   isActive: true
start-nigeria  hasBvn: true, hasLocalWallet: true
```

**Be straight about funding:** sandbox wallets start empty and BMONI credits
test tokens manually. Say so rather than implying a settled transfer.

---

## 6. Close (20 seconds)

> "KOPA doesn't replace anyone's judgement. It gives them the one thing their
> wallet never does — what happens next — at the only moment it can still
> change the outcome: before they sign."

---

## Q&A — likely questions

**"What if the user has money elsewhere?"**
KOPA says so in the UI: it can only see what it knows about. It's decision
support, not an oracle.

**"Isn't the runway estimate weak for irregular earners?"**
Yes, and that's the honest weakness. KOPA labels thin history as rough and
refuses to show a runway at all when there isn't enough — rather than
inventing one.

**"Where's the BMONI API key?"**
`kopa_backend` environment only. `grep -r "x-api-key" kopa_app/` returns
nothing.

**"Where's the private key?"**
Android Keystore. Never on our server, never in a backup, never in a log.

**"What if the sandbox is down mid-demo?"**
Demo mode, and it's already on. The engine and AI run for real over seeded
data; anything seeded is labelled DEMO DATA and demo transfers carry no BMONI
reference.

**"Why not let AI do the calculation?"**
Because then it could be wrong about someone's rent.

---

## Pre-demo checklist

- [ ] `curl -s localhost:8000/health` → `demo_mode: true`
- [ ] `pytest -q` in `kopa_backend` → 58 passed
- [ ] `flutter test` in `kopa_app` → 17 passed
- [ ] Scenario A shows ₦44,500.00 / 31 days / SAFE
- [ ] Scenario B shows ₦17,500.00 / 12 days / UNSAFE + Rent at risk
- [ ] Phone on Do Not Disturb
