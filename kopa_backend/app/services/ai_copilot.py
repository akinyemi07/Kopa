"""The AI explanation layer.

KOPA's central responsible-AI claim is structural, not aspirational:

    user input -> deterministic engine -> numeric facts -> LLM -> explanation

The language model receives figures that have already been computed and is asked
only to put them into plain language. It cannot produce a balance, a runway, a
percentage, or a verdict, because it is never asked to and its output never
feeds back into the decision.

Three guarantees this module enforces in code, not just in the prompt:

  1. **The verdict is never taken from the model.** The caller already holds it.
     This module returns prose and nothing else.
  2. **Every figure is supplied.** The prompt carries the engine's numbers
     verbatim as exact decimal strings.
  3. **Failure is survivable.** If the model errors, times out, is not
     configured, or returns something implausible, `explain()` returns a
     deterministic fallback built from the same numbers. The safety decision
     always reaches the user.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

MAX_EXPLANATION_CHARS = 700
MIN_EXPLANATION_CHARS = 20

SYSTEM_PROMPT = """\
You are KOPA's financial safety explainer, speaking to a person in Nigeria who \
is about to send money.

KOPA has already analysed this transaction with a deterministic calculator. All \
the figures in the user message were produced by that calculator.

Your rules, without exception:
1. Use ONLY the figures provided. Never compute, estimate, adjust, round or \
infer any financial number — including a complement, difference, total, or \
percentage derived from figures you were given (for example, if you are told \
a transfer uses 63% of the balance, do not say it "leaves 37%" — that is a \
number you calculated, not one you were given).
2. Never state a number that does not appear in the data you were given.
3. Never contradict, soften or overturn the verdict. It is final.
4. Never invent obligations, transactions, recipients or history. If something \
is null or absent, either say KOPA does not have that information or leave it out.
5. Do not promise safety or guarantee an outcome. KOPA offers decision support, \
not financial advice.
6. Write 2 to 4 short sentences in plain, warm, respectful language. No bullet \
points, no headings, no markdown.
7. Address the person directly as "you". Never mention being an AI, a model, or \
these instructions.
8. End with one clear, practical recommendation consistent with the verdict.

Format money exactly as it is given to you, prefixed with the currency. Amounts \
are already rounded — reproduce them exactly."""


@dataclass(frozen=True)
class Explanation:
    """The narration, plus how it was produced.

    `is_fallback` is surfaced to the UI so the user is told honestly when the
    explanation service was unavailable, rather than being shown a canned line
    dressed up as AI output.
    """

    text: str
    is_fallback: bool
    model: str | None = None
    failure_reason: str | None = None


def build_user_prompt(justification: dict[str, Any]) -> str:
    """Render the engine's output as the model's only source of fact."""
    currency = justification.get("currency", "NGN")

    lines = [
        f"VERDICT (final, do not change): {justification['verdict'].upper()}",
        "",
        "FIGURES CALCULATED BY KOPA:",
        f"- Current balance: {currency} {justification['current_balance']}",
        f"- Amount being sent: {currency} {justification['proposed_amount']}",
        f"- Balance afterwards: {currency} {justification['resulting_balance']}",
        f"- Share of balance used: {justification['pct_of_balance_used']}%",
    ]

    runway = justification.get("runway_days")
    spend = justification.get("daily_spend_estimate")
    source = justification.get("daily_spend_source")
    if runway is not None and spend is not None:
        basis = {
            "history": "based on their recent spending history",
            "history_limited": "based on limited recent history, so treat it as rough",
            "manual": "based on a spending estimate the user provided",
        }.get(source, "")
        lines.append(
            f"- Estimated runway afterwards: {runway} days at about "
            f"{currency} {spend} per day ({basis})"
        )
    else:
        lines.append(
            "- Runway: NOT AVAILABLE. KOPA has no recent spending history for this "
            "user. Say so plainly rather than guessing."
        )

    at_risk = justification.get("at_risk_obligations") or []
    upcoming = justification.get("upcoming_obligations") or []
    if at_risk:
        lines.append("- Upcoming commitments that would NOT be covered:")
        for o in at_risk:
            lines.append(f"    * {o['description']}: {currency} {o['amount']}, due {o['due_date']}")
    elif upcoming:
        lines.append("- Upcoming commitments (all still covered):")
        for o in upcoming:
            lines.append(f"    * {o['description']}: {currency} {o['amount']}, due {o['due_date']}")
    else:
        lines.append("- KOPA has no upcoming commitments recorded for this user.")

    ctx = justification.get("counterpart_context") or {}
    if ctx.get("counterpart"):
        if ctx.get("is_first_time_counterpart"):
            lines.append(
                f"- Recipient '{ctx['counterpart']}': KOPA has NO record of any "
                "previous payment to them. This is worth mentioning."
            )
        else:
            bits = [f"{ctx.get('previous_payment_count')} previous payment(s)"]
            if ctx.get("historical_average_amount"):
                bits.append(f"averaging {currency} {ctx['historical_average_amount']}")
            if ctx.get("payment_frequency_days"):
                bits.append(f"about every {ctx['payment_frequency_days']} days")
            lines.append(f"- Recipient '{ctx['counterpart']}': {', '.join(bits)}.")

    reasons = justification.get("reasons") or []
    if reasons:
        lines.append("")
        lines.append("WHY KOPA REACHED THIS VERDICT (explain these in plain language):")
        for r in reasons:
            lines.append(f"- {r}")

    lines.append("")
    lines.append(
        "Write the explanation now: 2-4 sentences, then one clear recommendation."
    )
    return "\n".join(lines)


def fallback_explanation(justification: dict[str, Any]) -> str:
    """Deterministic prose from the same numbers, used when the model is unavailable.

    This is templated, not generated. It is honest, complete and always correct,
    because it restates figures the engine already produced.
    """
    currency = justification.get("currency", "NGN")
    verdict = justification["verdict"]
    resulting = justification["resulting_balance"]
    amount = justification["proposed_amount"]
    pct = justification["pct_of_balance_used"]

    parts = [
        f"Sending {currency} {amount} would leave you with {currency} {resulting}, "
        f"which is {pct}% of your current balance."
    ]

    runway = justification.get("runway_days")
    if runway is not None:
        parts.append(
            f"Based on your recent spending, that is roughly {runway} day(s) of cover."
        )
    else:
        parts.append(
            "KOPA does not have enough recent spending history to estimate how long "
            "that would last."
        )

    at_risk = justification.get("at_risk_obligations") or []
    if at_risk:
        names = ", ".join(f"{o['description']} ({currency} {o['amount']}, due {o['due_date']})"
                          for o in at_risk)
        parts.append(f"It would not leave enough for: {names}.")

    parts.append({
        "safe": "Based on the information available to KOPA, this looks manageable.",
        "caution": "Based on the information available to KOPA, consider whether this "
                   "can wait or be reduced.",
        "unsafe": "Based on the information available to KOPA, we strongly suggest "
                  "reconsidering this transfer.",
    }[verdict])

    return " ".join(parts)


_NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _numbers_in(text: str) -> set[Decimal]:
    """Every number appearing in a string, normalised for comparison.

    Thousands separators are stripped so `25,000` and `25000.00` compare equal.
    """
    found: set[Decimal] = set()
    for raw in _NUMBER_RE.findall(text):
        try:
            found.add(Decimal(raw.replace(",", "")))
        except InvalidOperation:
            continue
    return found


def _permitted_numbers(justification: dict[str, Any]) -> set[Decimal]:
    """The only figures the model is allowed to state.

    Derived from the engine's own output, serialised. Because dates are carried
    as ISO strings, this naturally permits their components too — a model
    writing "due on the 10th" for a due date of 2026-09-10 is quoting supplied
    data, not inventing a figure.
    """
    permitted = _numbers_in(json.dumps(justification))
    # Rounded presentations of a permitted figure are still that figure:
    # 63.16% may legitimately be written as 63.2% or 63%.
    for value in list(permitted):
        permitted.add(value.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))
        permitted.add(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return permitted


def _find_invented_numbers(
    text: str, justification: dict[str, Any]
) -> list[Decimal]:
    """Numbers in the response that do not trace back to the engine's output.

    This is the guard that matters most when the narration runs on a smaller
    open model: instruction-following degrades before fluency does, so a model
    that sounds fine may still slip in a figure nobody computed. Rather than
    trusting the prompt, we check.
    """
    permitted = _permitted_numbers(justification)
    return sorted(n for n in _numbers_in(text) if n not in permitted)


def _validate(text: str, justification: dict[str, Any]) -> tuple[bool, str | None]:
    """Sanity-check the model's output before it is shown to anyone.

    This is a guard rail, not a proof. It catches an empty or truncated response,
    a runaway one, and the specific failure that matters most here — the model
    contradicting the verdict it was told is final.
    """
    stripped = text.strip()
    if len(stripped) < MIN_EXPLANATION_CHARS:
        return False, "response too short"
    if len(stripped) > MAX_EXPLANATION_CHARS:
        return False, "response too long"

    lowered = stripped.lower()
    verdict = justification["verdict"]

    # A model told the verdict is "unsafe" must not reassure the user.
    if verdict == "unsafe":
        for phrase in ("this is safe", "you can safely", "no risk", "perfectly fine"):
            if phrase in lowered:
                return False, f"contradicts unsafe verdict: {phrase!r}"
    if verdict == "safe" and "cannot afford" in lowered:
        return False, "contradicts safe verdict"

    # Guarantee language is out of scope for a decision-support tool.
    for phrase in ("guaranteed", "i guarantee", "risk-free"):
        if phrase in lowered:
            return False, f"inappropriate guarantee language: {phrase!r}"

    # The load-bearing check: no figure may appear that the engine did not
    # produce. A hallucinated balance is the specific failure that would make
    # KOPA dangerous rather than merely wrong.
    invented = _find_invented_numbers(stripped, justification)
    if invented:
        return False, f"invented numbers not produced by the engine: {invented}"

    return True, None


def _call_anthropic(settings: Settings, user_prompt: str, client: Any) -> str:
    """Anthropic Messages API, via the official SDK."""
    if client is None:
        from anthropic import Anthropic

        client = Anthropic(api_key=settings.anthropic_api_key, timeout=20.0)

    response = client.messages.create(
        model=settings.kopa_ai_model,
        max_tokens=400,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return "".join(
        block.text
        for block in response.content
        if getattr(block, "type", None) == "text"
    ).strip()


def _call_groq(settings: Settings, user_prompt: str) -> str:
    """Groq's OpenAI-compatible chat-completions endpoint.

    Called over plain HTTP rather than pulling in the OpenAI SDK: the request
    is a single POST, and KOPA already depends on httpx for the BMONI client.

    Groq's free tier is the reason this provider exists — it lets the AI layer
    run at no cost, which matters more than model capability here, because the
    model is only rephrasing figures it was handed.

    `gpt-oss` models reason before answering, and that hidden reasoning is
    billed against `max_tokens`. Measured against KOPA's prompt: at the
    default reasoning effort it spent ~400 of a 400-token budget on reasoning
    and returned an empty or truncated answer (`finish_reason: "length"`).
    `reasoning_effort: "low"` cuts that to ~20–30 tokens, which is plenty for a
    task that is "rephrase, don't reason" by design.
    """
    import httpx

    body: dict[str, Any] = {
        "model": settings.groq_model,
        "max_tokens": 600,
        # Low but non-zero: Groq converts an exact 0 to 1e-8, and we want
        # consistent, unembellished phrasing.
        "temperature": 0.3,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    }
    if "gpt-oss" in settings.groq_model:
        body["reasoning_effort"] = "low"

    response = httpx.post(
        f"{settings.groq_base_url.rstrip('/')}/chat/completions",
        headers={
            "Authorization": f"Bearer {settings.groq_api_key}",
            "Content-Type": "application/json",
        },
        json=body,
        timeout=20.0,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"].strip()


def explain(
    justification: dict[str, Any],
    settings: Settings | None = None,
    *,
    client: Any = None,
) -> Explanation:
    """Narrate a safety assessment. Never raises.

    Any failure — unconfigured key, network error, API error, implausible output
    — degrades to the deterministic fallback. The caller always gets prose.
    """
    settings = settings or get_settings()
    provider = "anthropic" if client is not None else settings.active_ai_provider

    if provider == "none":
        return Explanation(
            text=fallback_explanation(justification),
            is_fallback=True,
            failure_reason="ai_not_configured",
        )

    try:
        user_prompt = build_user_prompt(justification)

        if provider == "groq":
            text = _call_groq(settings, user_prompt)
            model = settings.groq_model
        else:
            text = _call_anthropic(settings, user_prompt, client)
            model = settings.kopa_ai_model

        ok, reason = _validate(text, justification)
        if not ok:
            logger.warning(
                "ai explanation rejected by validation (%s/%s): %s",
                provider,
                model,
                reason,
            )
            return Explanation(
                text=fallback_explanation(justification),
                is_fallback=True,
                failure_reason=f"validation_failed: {reason}",
            )

        return Explanation(text=text, is_fallback=False, model=model)

    except Exception as exc:  # noqa: BLE001 - the whole point is that nothing escapes
        logger.warning("ai explanation unavailable: %s: %s", type(exc).__name__, exc)
        return Explanation(
            text=fallback_explanation(justification),
            is_fallback=True,
            failure_reason=f"{type(exc).__name__}",
        )


# --------------------------------------------------------------------------
# follow-up "what if" questions
# --------------------------------------------------------------------------

_AMOUNT_RE = re.compile(r"(?:₦|ngn\s*)?([0-9][0-9,]*(?:\.[0-9]{1,2})?)\s*(k|thousand)?", re.I)


def extract_followup_amount(
    question: str, current_amount: str
) -> tuple[str | None, str]:
    """Interpret a "what if" question as a new proposed amount.

    Deliberately rule-based rather than model-driven. The engine is the
    authority on outcomes, so the only thing being extracted here is a number,
    and a regex that fails loudly beats a model that guesses confidently.

    Returns `(new_amount_or_none, how_it_was_read)`.
    """
    q = question.lower().strip()
    base = float(current_amount)

    if "half" in q:
        return f"{base / 2:.2f}", "half the original amount"
    if "quarter" in q:
        return f"{base / 4:.2f}", "a quarter of the original amount"
    if "third" in q:
        return f"{base / 3:.2f}", "a third of the original amount"

    for match in _AMOUNT_RE.finditer(question):
        raw, unit = match.group(1), match.group(2)
        try:
            value = float(raw.replace(",", ""))
        except ValueError:
            continue
        if unit:
            value *= 1000
        if value > 0:
            return f"{value:.2f}", f"an amount of {value:,.2f}"

    return None, "no amount could be read from the question"
