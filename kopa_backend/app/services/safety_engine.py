"""KOPA's deterministic financial safety engine.

This module is the source of truth for every number KOPA shows a user and every
verdict it reaches. It is deliberately:

  * **Pure** — no I/O, no database, no network, no clock reads. Everything it
    needs arrives as an argument, including `as_of`.
  * **Deterministic** — the same inputs always produce the same output. This is
    what makes the verdict auditable and testable.
  * **LLM-free** — no language model is imported, called, or consulted here.

The AI copilot (`app/services/ai_copilot.py`) *narrates* the output of this
module. It never produces a figure of its own and never overrides a verdict.
That separation is the whole responsible-AI argument for KOPA: a language model
cannot hallucinate a balance it was never asked to compute.

Money is handled as `Decimal` throughout. Floats are not acceptable for currency.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Any, Iterable, Sequence

# --------------------------------------------------------------------------
# Tunable policy thresholds.
#
# These are product policy, not magic numbers scattered through the logic. They
# are stated here so a reviewer can see exactly what KOPA considers risky, and
# so the documentation and the code cannot drift apart.
# --------------------------------------------------------------------------

#: Days of runway at or below which a transaction is never "safe".
UNSAFE_RUNWAY_DAYS = 3

#: Days of runway at or below which a transaction is at best "caution".
CAUTION_RUNWAY_DAYS = 7

#: Share of the current balance that a single transaction may consume before
#: it is treated as material, even when the resulting balance looks healthy.
CAUTION_BALANCE_SHARE = Decimal("0.50")

#: How far ahead KOPA looks for obligations when there is no runway estimate.
DEFAULT_OBLIGATION_HORIZON_DAYS = 30

#: Window of history used to estimate typical daily spending.
SPEND_HISTORY_WINDOW_DAYS = 30

#: A resulting balance below this multiple of upcoming obligations is thin
#: even when every individual obligation is still technically covered.
OBLIGATION_BUFFER_MULTIPLE = Decimal("1.10")

TWO_PLACES = Decimal("0.01")


class Verdict(str, Enum):
    """The three states KOPA can reach. Ordered least to most severe."""

    SAFE = "safe"
    CAUTION = "caution"
    UNSAFE = "unsafe"


class SafetyEngineError(ValueError):
    """Raised when the caller supplies input the engine cannot evaluate."""


@dataclass(frozen=True)
class Obligation:
    """A known upcoming commitment — rent, school fees, a loan repayment."""

    description: str
    amount: Decimal
    due_date: date

    def days_until(self, as_of: date) -> int:
        return (self.due_date - as_of).days


@dataclass(frozen=True)
class HistoricalTransaction:
    """A past outflow, used to estimate typical spending and counterpart context."""

    amount: Decimal
    occurred_on: date
    counterpart: str | None = None


@dataclass(frozen=True)
class CounterpartContext:
    """What KOPA knows about the person or business being paid.

    Every field is derived from KOPA's own transaction records. When there is no
    history, the fields are `None` rather than a guess — the AI layer is
    instructed to say "KOPA has no record of this recipient" rather than invent
    one.
    """

    counterpart: str | None
    is_first_time_counterpart: bool
    previous_payment_count: int
    historical_average_amount: Decimal | None
    last_paid_on: date | None
    payment_frequency_days: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "counterpart": self.counterpart,
            "is_first_time_counterpart": self.is_first_time_counterpart,
            "previous_payment_count": self.previous_payment_count,
            "historical_average_amount": _money_or_none(self.historical_average_amount),
            "last_paid_on": self.last_paid_on.isoformat() if self.last_paid_on else None,
            "payment_frequency_days": self.payment_frequency_days,
        }


@dataclass(frozen=True)
class SafetyAssessment:
    """The complete, auditable result of one evaluation.

    `reasons` is the machine-readable list of rules that actually fired. It is
    what the AI copilot is asked to explain, and what a reviewer can check the
    verdict against.
    """

    verdict: Verdict
    current_balance: Decimal
    proposed_amount: Decimal
    resulting_balance: Decimal
    pct_of_balance_used: Decimal
    runway_days: int | None
    daily_spend_estimate: Decimal | None
    daily_spend_source: str
    at_risk_obligations: list[Obligation] = field(default_factory=list)
    upcoming_obligations: list[Obligation] = field(default_factory=list)
    obligations_total: Decimal = Decimal("0")
    counterpart_context: CounterpartContext | None = None
    reasons: list[str] = field(default_factory=list)
    currency: str = "NGN"

    def to_numeric_justification(self) -> dict[str, Any]:
        """The exact payload handed to the AI copilot, and stored in the log.

        Every number the AI is allowed to mention appears here. Nothing else does.
        """
        return {
            "currency": self.currency,
            "verdict": self.verdict.value,
            "current_balance": _money(self.current_balance),
            "proposed_amount": _money(self.proposed_amount),
            "resulting_balance": _money(self.resulting_balance),
            "pct_of_balance_used": float(self.pct_of_balance_used),
            "runway_days": self.runway_days,
            "daily_spend_estimate": _money_or_none(self.daily_spend_estimate),
            "daily_spend_source": self.daily_spend_source,
            "obligations_total": _money(self.obligations_total),
            "at_risk_obligations": [
                {
                    "description": o.description,
                    "amount": _money(o.amount),
                    "due_date": o.due_date.isoformat(),
                }
                for o in self.at_risk_obligations
            ],
            "upcoming_obligations": [
                {
                    "description": o.description,
                    "amount": _money(o.amount),
                    "due_date": o.due_date.isoformat(),
                }
                for o in self.upcoming_obligations
            ],
            "counterpart_context": (
                self.counterpart_context.to_dict() if self.counterpart_context else None
            ),
            "reasons": list(self.reasons),
        }


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _money(value: Decimal) -> str:
    """Render a money amount as a fixed 2dp decimal string.

    A string, not a float, so the value that reaches the AI prompt and the API
    response is exactly the value the engine computed.
    """
    return str(value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP))


def _money_or_none(value: Decimal | None) -> str | None:
    return _money(value) if value is not None else None


def _as_decimal(value: Any, field_name: str) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception as exc:  # noqa: BLE001 - surfaced as a domain error
        raise SafetyEngineError(f"{field_name} is not a valid amount: {value!r}") from exc


# --------------------------------------------------------------------------
# spending estimate
# --------------------------------------------------------------------------

def estimate_daily_spend(
    history: Sequence[HistoricalTransaction],
    as_of: date,
    window_days: int = SPEND_HISTORY_WINDOW_DAYS,
) -> tuple[Decimal | None, str]:
    """Estimate typical daily outflow from recent history.

    Returns `(estimate, source)`. The source string is carried all the way to the
    UI so the user is told how the figure was reached rather than being shown an
    unexplained number.

    Total outflow in the window is divided by the number of days actually
    covered by that history, not by the full window — three days of records
    should not be averaged as though they were thirty.
    """
    if not history:
        return None, "unavailable"

    window_start = as_of - timedelta(days=window_days)
    recent = [t for t in history if window_start <= t.occurred_on <= as_of]
    if not recent:
        return None, "unavailable"

    total = sum((t.amount for t in recent), Decimal("0"))
    if total <= 0:
        return None, "unavailable"

    earliest = min(t.occurred_on for t in recent)
    days_covered = max((as_of - earliest).days, 1)

    estimate = (total / Decimal(days_covered)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    if estimate <= 0:
        return None, "unavailable"

    source = "history" if days_covered >= 7 else "history_limited"
    return estimate, source


def build_counterpart_context(
    counterpart: str | None,
    history: Sequence[HistoricalTransaction],
    as_of: date,
) -> CounterpartContext:
    """Summarise KOPA's record of payments to one counterpart.

    Matching is case-insensitive and whitespace-trimmed. Anything KOPA cannot
    establish stays `None` — never a placeholder or an assumed value.
    """
    if not counterpart:
        return CounterpartContext(None, True, 0, None, None, None)

    key = counterpart.strip().casefold()
    matches = [
        t for t in history
        if t.counterpart and t.counterpart.strip().casefold() == key
    ]

    if not matches:
        return CounterpartContext(counterpart, True, 0, None, None, None)

    amounts = [t.amount for t in matches]
    average = (sum(amounts, Decimal("0")) / Decimal(len(amounts))).quantize(
        TWO_PLACES, rounding=ROUND_HALF_UP
    )
    dates = sorted(t.occurred_on for t in matches)
    last_paid = dates[-1]

    frequency: float | None = None
    if len(dates) >= 2:
        gaps = [(b - a).days for a, b in zip(dates, dates[1:])]
        frequency = round(sum(gaps) / len(gaps), 1)

    return CounterpartContext(
        counterpart=counterpart,
        is_first_time_counterpart=False,
        previous_payment_count=len(matches),
        historical_average_amount=average,
        last_paid_on=last_paid,
        payment_frequency_days=frequency,
    )


# --------------------------------------------------------------------------
# the engine
# --------------------------------------------------------------------------

def evaluate_transaction(
    current_balance: Decimal | str | int | float,
    proposed_amount: Decimal | str | int | float,
    obligations: Iterable[Obligation] | None = None,
    history: Sequence[HistoricalTransaction] | None = None,
    *,
    as_of: date,
    counterpart: str | None = None,
    daily_spend_estimate: Decimal | str | int | float | None = None,
    currency: str = "NGN",
) -> SafetyAssessment:
    """Evaluate one proposed outgoing transaction.

    `as_of` is required and never defaulted to "today" — a pure function must not
    read the clock, and tests must be able to pin the date.

    The verdict is reached by evaluating every rule, collecting the reasons that
    fired, and taking the most severe. Rules are additive: a transaction can be
    unsafe for several independent reasons and the user is shown all of them.
    """
    balance = _as_decimal(current_balance, "current_balance")
    amount = _as_decimal(proposed_amount, "proposed_amount")

    if amount <= 0:
        raise SafetyEngineError("proposed_amount must be greater than zero")
    if balance < 0:
        raise SafetyEngineError("current_balance cannot be negative")

    obligations = list(obligations or [])
    history = list(history or [])

    resulting_balance = balance - amount

    # Share of the balance this transaction consumes. Guard the zero-balance
    # case: spending anything from nothing is 100% of it.
    if balance > 0:
        pct_used = ((amount / balance) * Decimal("100")).quantize(
            TWO_PLACES, rounding=ROUND_HALF_UP
        )
    else:
        pct_used = Decimal("100.00")

    # --- daily spend + runway ------------------------------------------------
    if daily_spend_estimate is not None:
        spend = _as_decimal(daily_spend_estimate, "daily_spend_estimate")
        if spend <= 0:
            raise SafetyEngineError("daily_spend_estimate must be greater than zero")
        spend_source = "manual"
    else:
        spend, spend_source = estimate_daily_spend(history, as_of)

    if spend and spend > 0 and resulting_balance > 0:
        runway_days: int | None = int(resulting_balance / spend)
    elif spend and spend > 0:
        runway_days = 0
    else:
        runway_days = None

    # --- obligations ---------------------------------------------------------
    # A fixed planning horizon. It deliberately does not scale with the runway:
    # a large balance produces a runway of years, and pulling next year's rent
    # into today's decision would make every healthy account look encumbered.
    # Thirty days is the horizon a monthly earner actually plans against, and an
    # obligation 30 days out still counts when the runway is 4 days — which is
    # precisely the case KOPA exists to catch.
    horizon_days = DEFAULT_OBLIGATION_HORIZON_DAYS

    upcoming = sorted(
        (o for o in obligations if 0 <= o.days_until(as_of) <= horizon_days),
        key=lambda o: o.due_date,
    )
    obligations_total = sum((o.amount for o in upcoming), Decimal("0"))

    # An obligation is at risk when the resulting balance cannot cover it
    # *together with* everything already due before it. Obligations are settled
    # in date order, so each one is tested against the running total.
    at_risk: list[Obligation] = []
    running = Decimal("0")
    for ob in upcoming:
        running += ob.amount
        if resulting_balance < running:
            at_risk.append(ob)

    # --- rules ---------------------------------------------------------------
    reasons: list[str] = []
    severity = Verdict.SAFE

    def escalate(to: Verdict, reason: str) -> None:
        nonlocal severity
        reasons.append(reason)
        order = {Verdict.SAFE: 0, Verdict.CAUTION: 1, Verdict.UNSAFE: 2}
        if order[to] > order[severity]:
            severity = to

    if resulting_balance < 0:
        escalate(
            Verdict.UNSAFE,
            "insufficient_balance: the transaction exceeds the available balance",
        )

    if at_risk:
        names = ", ".join(o.description for o in at_risk)
        escalate(
            Verdict.UNSAFE,
            f"obligation_at_risk: not enough would remain to cover {names}",
        )

    if runway_days is not None and runway_days <= UNSAFE_RUNWAY_DAYS:
        escalate(
            Verdict.UNSAFE,
            f"runway_critical: about {runway_days} day(s) of typical spending would remain",
        )
    elif runway_days is not None and runway_days <= CAUTION_RUNWAY_DAYS:
        escalate(
            Verdict.CAUTION,
            f"runway_short: about {runway_days} day(s) of typical spending would remain",
        )

    if pct_used >= CAUTION_BALANCE_SHARE * Decimal("100"):
        escalate(
            Verdict.CAUTION,
            f"large_share_of_balance: this uses {pct_used}% of the current balance",
        )

    if (
        upcoming
        and not at_risk
        and resulting_balance < obligations_total * OBLIGATION_BUFFER_MULTIPLE
    ):
        escalate(
            Verdict.CAUTION,
            "thin_obligation_buffer: upcoming obligations would be covered with little to spare",
        )

    if spend is None:
        reasons.append(
            "no_spending_history: KOPA has no recent spending record, so no runway "
            "estimate is available"
        )

    context = build_counterpart_context(counterpart, history, as_of)

    if context.is_first_time_counterpart and counterpart:
        reasons.append("first_time_counterpart: KOPA has no record of paying this recipient")
    elif context.historical_average_amount and context.historical_average_amount > 0:
        ratio = amount / context.historical_average_amount
        if ratio >= Decimal("2"):
            escalate(
                Verdict.CAUTION,
                "unusual_amount_for_counterpart: this is much larger than previous "
                f"payments to {counterpart}",
            )

    if severity is Verdict.SAFE and not reasons:
        reasons.append("within_normal_limits: balance, runway and obligations all look comfortable")

    return SafetyAssessment(
        verdict=severity,
        current_balance=balance,
        proposed_amount=amount,
        resulting_balance=resulting_balance,
        pct_of_balance_used=pct_used,
        runway_days=runway_days,
        daily_spend_estimate=spend,
        daily_spend_source=spend_source,
        at_risk_obligations=at_risk,
        upcoming_obligations=upcoming,
        obligations_total=obligations_total,
        counterpart_context=context,
        reasons=reasons,
        currency=currency,
    )
