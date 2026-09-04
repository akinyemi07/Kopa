"""Pins the exact figures the demo depends on.

The demo script quotes these numbers to the judges. If a threshold or the seed
data is ever changed, this test fails loudly rather than letting the
demonstration disagree with the documentation on stage.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.services.demo_data import (
    FIRST_TIME_COUNTERPART,
    RECURRING_COUNTERPART,
    SAFE_DEMO_AMOUNT,
    UNSAFE_DEMO_AMOUNT,
    demo_balance,
    demo_history,
    demo_obligations,
)
from app.services.safety_engine import Verdict, evaluate_transaction

# The demo is evaluated relative to a fixed date so the numbers never drift.
DEMO_DATE = date(2026, 9, 5)


def _evaluate(amount: Decimal, counterpart: str | None):
    return evaluate_transaction(
        current_balance=demo_balance(),
        proposed_amount=amount,
        obligations=demo_obligations(DEMO_DATE),
        history=demo_history(DEMO_DATE),
        counterpart=counterpart,
        as_of=DEMO_DATE,
    )


def test_demo_baseline_figures():
    assert demo_balance() == Decimal("47500.00")
    assert len(demo_obligations(DEMO_DATE)) == 2
    assert len(demo_history(DEMO_DATE)) == 23


def test_scenario_a_is_safe_with_the_documented_numbers():
    r = _evaluate(SAFE_DEMO_AMOUNT, RECURRING_COUNTERPART)
    j = r.to_numeric_justification()

    assert r.verdict is Verdict.SAFE
    assert j["proposed_amount"] == "3000.00"
    assert j["resulting_balance"] == "44500.00"
    assert j["pct_of_balance_used"] == 6.32
    assert j["daily_spend_estimate"] == "1397.22"
    assert j["daily_spend_source"] == "history"
    assert j["runway_days"] == 31
    assert j["at_risk_obligations"] == []


def test_scenario_b_is_unsafe_with_the_documented_numbers():
    r = _evaluate(UNSAFE_DEMO_AMOUNT, FIRST_TIME_COUNTERPART)
    j = r.to_numeric_justification()

    assert r.verdict is Verdict.UNSAFE
    assert j["proposed_amount"] == "30000.00"
    assert j["resulting_balance"] == "17500.00"
    assert j["pct_of_balance_used"] == 63.16
    assert j["runway_days"] == 12
    assert [o["description"] for o in j["at_risk_obligations"]] == [
        "Rent",
        "Data subscription",
    ]


def test_scenario_b_fires_three_independent_reasons():
    """The unsafe demo is not resting on a single rule."""
    r = _evaluate(UNSAFE_DEMO_AMOUNT, FIRST_TIME_COUNTERPART)
    prefixes = {reason.split(":")[0] for reason in r.reasons}
    assert "obligation_at_risk" in prefixes
    assert "large_share_of_balance" in prefixes
    assert "first_time_counterpart" in prefixes


def test_recurring_counterpart_is_recognised_from_demo_history():
    r = _evaluate(SAFE_DEMO_AMOUNT, RECURRING_COUNTERPART)
    ctx = r.counterpart_context
    assert ctx is not None
    assert ctx.is_first_time_counterpart is False
    assert ctx.previous_payment_count == 3
    assert ctx.historical_average_amount == Decimal("1800.00")


def test_first_time_counterpart_is_recognised_from_demo_history():
    r = _evaluate(SAFE_DEMO_AMOUNT, FIRST_TIME_COUNTERPART)
    ctx = r.counterpart_context
    assert ctx is not None
    assert ctx.is_first_time_counterpart is True
    assert ctx.previous_payment_count == 0
