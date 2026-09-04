# Responsible AI in KOPA

## The one-sentence version

KOPA's AI writes sentences. It does not do arithmetic, and it cannot change a
verdict.

## Why this matters here specifically

Language models are confidently wrong about numbers. In most products that is
an annoyance. In a product telling someone whether they can afford to send
money before rent is due, a hallucinated balance is a person who cannot pay
their rent.

The standard mitigations — "be careful", better prompts, asking the model to
double-check — are all probabilistic. They reduce how often the model is
wrong. They do not make it structurally incapable of being wrong.

KOPA takes the structural route instead: **the model is never asked to
calculate anything, so there is no financial arithmetic for it to get wrong.**

## The architecture

```
     user input
         │
         ▼
┌─────────────────────┐
│  safety_engine.py   │   pure Python. No LLM import. No network.
│  deterministic      │   No clock read. Decimal arithmetic.
└─────────┬───────────┘
          │  numeric facts (exact decimal strings)
          ▼
┌─────────────────────┐
│   ai_copilot.py     │   receives facts. Writes prose.
│   narration only    │   Output is validated, then displayed.
└─────────┬───────────┘
          │  prose
          ▼
      the user
```

The critical property is that **no arrow points back up.** The model's output
is never an input to the decision. `explain()` returns a string; the verdict
was already final before it was called.

## What AI does

- Turns `{"verdict": "unsafe", "resulting_balance": "17500.00",
  "at_risk_obligations": [{"description": "Rent", ...}]}` into
  *"Sending ₦30,000 would leave you ₦17,500, which is not enough for your rent
  of ₦25,000 due on the 10th."*
- Interprets the intent of a "what if" question well enough to extract a
  candidate amount.

## What AI does not do

It does not compute or influence:

- the balance, or the resulting balance
- the runway estimate
- the percentage of balance used
- which obligations are at risk
- the verdict

It also cannot introduce facts. Every figure it is permitted to mention is
supplied in the prompt; the system prompt forbids stating any other number.

## Enforcement, not just instruction

A prompt that says "do not invent numbers" is a request. These are the
mechanisms that make it more than that.

**1. The model never sees the raw data.** It receives only the engine's output.
It has no access to the database, the balance API, or the transaction history,
so there is nothing to miscount.

**2. Output is validated before display** (`ai_copilot._validate`). A response
is rejected if it is empty, truncated, runaway-long, uses guarantee language,
or contradicts the verdict — for instance saying "this is safe" when the
verdict is `unsafe`. A rejected response is replaced by the deterministic
fallback.

**3. The verdict is not parsed from the response.** The caller already holds
it. Even a model that ignored every instruction could not change the outcome,
because nothing reads its opinion of the verdict.

**4. Money is passed as exact decimal strings**, never floats, so the figure in
the prompt is bit-for-bit the figure the engine computed.

This is tested. `test_ai_copilot.py::test_model_contradicting_an_unsafe_verdict_is_rejected`
feeds the layer a model response saying *"Go ahead, this is safe and there is
no risk at all"* against an `unsafe` verdict, and asserts the user is shown the
deterministic explanation instead.

## Failure behaviour

**AI failure never blocks a safety decision.** `explain()` cannot raise — every
exception path returns a deterministic fallback built from the same numbers.

| Failure | Result |
|---|---|
| No API key configured | Fallback, reason `ai_not_configured` |
| Network error / timeout | Fallback |
| API error (rate limit, billing, 5xx) | Fallback |
| Empty or truncated response | Fallback, reason `too short` |
| Response contradicts the verdict | Fallback, reason `contradicts…` |
| Guarantee language | Fallback, reason `inappropriate guarantee language` |

The fallback is templated prose over the engine's figures — always correct,
because it only restates computed values.

Crucially, **the user is told**. The response carries `ai_is_fallback: true`
and the UI displays:

> KOPA's safety analysis is complete, but the explanation service is
> temporarily unavailable — this summary was generated directly from the
> figures above.

Silently downgrading and passing a template off as AI output would be a small
lie that undermines the honesty the rest of the product depends on.

## Honest limits

KOPA states these in the product, not only in this document.

**KOPA cannot see everything.** It knows the wallet it is connected to and the
obligations the user has entered. Cash under a mattress, another bank account,
or a bill never recorded are all invisible to it. The UI says so:

> Based on the information available to KOPA. This is decision support, not
> financial advice, and it cannot see money or commitments KOPA does not know
> about.

**The runway is an estimate.** It extrapolates from recent spending, which is a
weak predictor for irregular earners — precisely KOPA's target user. When
history is thin the estimate is labelled *"based on limited recent history, so
treat it as rough"*, and when it is absent KOPA says *"not enough history"*
rather than showing a fabricated number or a misleading zero.

**KOPA never guarantees safety.** The word "safe" never appears as a promise.
The verdict labels are *"Looks manageable"*, *"Think carefully"* and *"Not
recommended"* — judgements, not assurances.

**KOPA does not block.** "Send anyway" is always available. It is the user's
money, and a tool that overrides its user is not a safety tool; it is a
paternalistic one that people route around.

## Privacy

- Financial data is sent to Anthropic only as the aggregate figures needed for
  the explanation — balance, amount, runway, obligation descriptions.
- No BVN, no NIN, no phone number, no email, no wallet address, and no
  transaction identifiers are ever included in a prompt.
- Prompts are not logged; only the resulting explanation is stored, in
  `ai_decision_log`, alongside the numeric justification that produced it.

## Auditability

Every decision is recorded with its `numeric_justification`. Because the engine
is deterministic and reads no clock, any historical decision can be recomputed
from its stored inputs and checked against what the user was shown.

That is the difference between a system that claims its AI is safe and one that
can demonstrate it.
