"""Tests for the deterministic safety engine.

Every test pins `as_of` explicitly. The engine never reads the clock, so these
results are stable forever — a test that passes today passes in a year.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.services.safety_engine import (
    CAUTION_RUNWAY_DAYS,
    HistoricalTransaction,
    Obligation,
    SafetyEngineError,
    UNSAFE_RUNWAY_DAYS,
    Verdict,
    build_counterpart_context,
    estimate_daily_spend,
    evaluate_transaction,
)

TODAY = date(2026, 9, 4)


def steady_history(
    days: int = 30,
    per_day: str = "1000",
    counterpart: str | None = None,
) -> list[HistoricalTransaction]:
    """One transaction per day of a fixed size — a predictable ₦/day baseline."""
    return [
        HistoricalTransaction(
            amount=Decimal(per_day),
            occurred_on=TODAY - timedelta(days=i),
            counterpart=counterpart,
        )
        for i in range(1, days + 1)
    ]


# --------------------------------------------------------------------------
# core verdicts
# --------------------------------------------------------------------------

def test_plenty_of_buffer_is_safe():
    result = evaluate_transaction(
        current_balance="500000",
        proposed_amount="5000",
        obligations=[],
        history=steady_history(),
        as_of=TODAY,
    )
    assert result.verdict is Verdict.SAFE
    assert result.resulting_balance == Decimal("495000")
    assert result.runway_days is not None and result.runway_days > CAUTION_RUNWAY_DAYS


def test_negative_resulting_balance_is_unsafe():
    result = evaluate_transaction(
        current_balance="10000",
        proposed_amount="15000",
        history=steady_history(),
        as_of=TODAY,
    )
    assert result.verdict is Verdict.UNSAFE
    assert result.resulting_balance == Decimal("-5000")
    assert any(r.startswith("insufficient_balance") for r in result.reasons)


def test_obligation_left_uncovered_is_unsafe():
    """The classic KOPA case: affordable today, but rent is due on Friday."""
    result = evaluate_transaction(
        current_balance="30000",
        proposed_amount="20000",
        obligations=[
            Obligation("Rent", Decimal("25000"), TODAY + timedelta(days=5)),
        ],
        history=steady_history(per_day="500"),
        as_of=TODAY,
    )
    assert result.verdict is Verdict.UNSAFE
    assert [o.description for o in result.at_risk_obligations] == ["Rent"]
    assert any(r.startswith("obligation_at_risk") for r in result.reasons)


def test_tight_runway_is_caution_not_unsafe():
    """Balance survives, obligations are covered, but the buffer is thin."""
    result = evaluate_transaction(
        current_balance="12000",
        proposed_amount="5000",
        obligations=[],
        history=steady_history(per_day="1000"),
        as_of=TODAY,
    )
    assert result.runway_days == 7
    assert result.verdict is Verdict.CAUTION
    assert any(r.startswith("runway_short") for r in result.reasons)


def test_critically_short_runway_is_unsafe():
    result = evaluate_transaction(
        current_balance="12000",
        proposed_amount="9500",
        obligations=[],
        history=steady_history(per_day="1000"),
        as_of=TODAY,
    )
    assert result.runway_days is not None
    assert result.runway_days <= UNSAFE_RUNWAY_DAYS
    assert result.verdict is Verdict.UNSAFE


def test_large_share_of_balance_triggers_caution():
    """No obligations and adequate runway, but it still eats most of the balance."""
    result = evaluate_transaction(
        current_balance="100000",
        proposed_amount="60000",
        obligations=[],
        history=steady_history(per_day="500"),
        as_of=TODAY,
    )
    assert result.pct_of_balance_used == Decimal("60.00")
    assert result.verdict is Verdict.CAUTION
    assert any(r.startswith("large_share_of_balance") for r in result.reasons)


def test_obligation_covered_with_little_to_spare_is_caution():
    # 55,000 left against a 52,000 obligation — covered, but inside the 10% buffer.
    result = evaluate_transaction(
        current_balance="60000",
        proposed_amount="5000",
        obligations=[
            Obligation("School fees", Decimal("52000"), TODAY + timedelta(days=20)),
        ],
        history=steady_history(per_day="100"),
        as_of=TODAY,
    )
    assert result.at_risk_obligations == []
    assert result.verdict is Verdict.CAUTION
    assert any(r.startswith("thin_obligation_buffer") for r in result.reasons)


def test_obligation_buffer_boundary_is_not_caution():
    """Exactly at the buffer multiple is acceptable; only strictly below is thin.

    Boundary behaviour is pinned deliberately — in financial rules an
    off-by-one at the threshold is a real defect, not a rounding detail.
    """
    # 55,000 left against a 50,000 obligation == exactly 1.10x.
    result = evaluate_transaction(
        current_balance="60000",
        proposed_amount="5000",
        obligations=[
            Obligation("School fees", Decimal("50000"), TODAY + timedelta(days=20)),
        ],
        history=steady_history(per_day="100"),
        as_of=TODAY,
    )
    assert result.verdict is Verdict.SAFE
    assert not any(r.startswith("thin_obligation_buffer") for r in result.reasons)


# --------------------------------------------------------------------------
# obligation ordering
# --------------------------------------------------------------------------

def test_obligations_are_settled_in_due_date_order():
    """The earlier obligation is covered; the later one is what breaks."""
    result = evaluate_transaction(
        current_balance="60000",
        proposed_amount="10000",
        obligations=[
            Obligation("Electricity", Decimal("10000"), TODAY + timedelta(days=10)),
            Obligation("Rent", Decimal("45000"), TODAY + timedelta(days=20)),
        ],
        history=steady_history(per_day="100"),
        as_of=TODAY,
    )
    assert result.verdict is Verdict.UNSAFE
    assert [o.description for o in result.at_risk_obligations] == ["Rent"]


def test_obligations_beyond_the_horizon_are_ignored():
    result = evaluate_transaction(
        current_balance="500000",
        proposed_amount="1000",
        obligations=[
            Obligation("Next year's rent", Decimal("900000"), TODAY + timedelta(days=300)),
        ],
        history=steady_history(per_day="100"),
        as_of=TODAY,
    )
    assert result.upcoming_obligations == []
    assert result.verdict is Verdict.SAFE


def test_obligation_already_past_due_is_not_counted_as_upcoming():
    result = evaluate_transaction(
        current_balance="500000",
        proposed_amount="1000",
        obligations=[
            Obligation("Last month's rent", Decimal("400000"), TODAY - timedelta(days=5)),
        ],
        history=steady_history(per_day="100"),
        as_of=TODAY,
    )
    assert result.upcoming_obligations == []


# --------------------------------------------------------------------------
# input validation
# --------------------------------------------------------------------------

@pytest.mark.parametrize("bad_amount", ["0", "-1", "-5000"])
def test_zero_or_negative_amount_is_rejected(bad_amount):
    with pytest.raises(SafetyEngineError, match="greater than zero"):
        evaluate_transaction(
            current_balance="10000",
            proposed_amount=bad_amount,
            as_of=TODAY,
        )


def test_negative_balance_is_rejected():
    with pytest.raises(SafetyEngineError, match="cannot be negative"):
        evaluate_transaction(current_balance="-1", proposed_amount="100", as_of=TODAY)


def test_non_numeric_amount_is_rejected():
    with pytest.raises(SafetyEngineError, match="not a valid amount"):
        evaluate_transaction(
            current_balance="10000", proposed_amount="not-a-number", as_of=TODAY
        )


def test_zero_balance_reports_full_share_rather_than_dividing_by_zero():
    result = evaluate_transaction(
        current_balance="0", proposed_amount="100", as_of=TODAY
    )
    assert result.pct_of_balance_used == Decimal("100.00")
    assert result.verdict is Verdict.UNSAFE


# --------------------------------------------------------------------------
# spending estimate
# --------------------------------------------------------------------------

def test_no_history_yields_no_runway_and_says_so():
    result = evaluate_transaction(
        current_balance="50000",
        proposed_amount="1000",
        history=[],
        as_of=TODAY,
    )
    assert result.runway_days is None
    assert result.daily_spend_estimate is None
    assert result.daily_spend_source == "unavailable"
    assert any(r.startswith("no_spending_history") for r in result.reasons)


def test_manual_estimate_is_used_when_history_is_absent():
    result = evaluate_transaction(
        current_balance="50000",
        proposed_amount="20000",
        history=[],
        daily_spend_estimate="3000",
        as_of=TODAY,
    )
    assert result.daily_spend_source == "manual"
    assert result.runway_days == 10


def test_manual_estimate_overrides_history():
    result = evaluate_transaction(
        current_balance="50000",
        proposed_amount="20000",
        history=steady_history(per_day="1000"),
        daily_spend_estimate="3000",
        as_of=TODAY,
    )
    assert result.daily_spend_source == "manual"
    assert result.daily_spend_estimate == Decimal("3000")


def test_sparse_history_is_flagged_as_limited():
    """Three days of records must not be averaged as though they were thirty."""
    history = [
        HistoricalTransaction(Decimal("2000"), TODAY - timedelta(days=i))
        for i in range(1, 4)
    ]
    estimate, source = estimate_daily_spend(history, TODAY)
    assert source == "history_limited"
    assert estimate == Decimal("2000.00")  # 6000 over 3 days, not over 30


def test_history_outside_the_window_is_excluded():
    old = [
        HistoricalTransaction(Decimal("9999"), TODAY - timedelta(days=200))
        for _ in range(5)
    ]
    estimate, source = estimate_daily_spend(old, TODAY)
    assert estimate is None
    assert source == "unavailable"


def test_zero_manual_estimate_is_rejected():
    with pytest.raises(SafetyEngineError, match="greater than zero"):
        evaluate_transaction(
            current_balance="1000",
            proposed_amount="100",
            daily_spend_estimate="0",
            as_of=TODAY,
        )


# --------------------------------------------------------------------------
# counterpart / merchant context
# --------------------------------------------------------------------------

def test_first_time_counterpart_is_reported():
    result = evaluate_transaction(
        current_balance="500000",
        proposed_amount="5000",
        history=steady_history(counterpart="Mama Nkechi Stores"),
        counterpart="Brand New Vendor",
        as_of=TODAY,
    )
    ctx = result.counterpart_context
    assert ctx is not None
    assert ctx.is_first_time_counterpart is True
    assert ctx.previous_payment_count == 0
    assert ctx.historical_average_amount is None
    assert any(r.startswith("first_time_counterpart") for r in result.reasons)


def test_recurring_counterpart_reports_average_and_frequency():
    history = [
        HistoricalTransaction(Decimal("15000"), TODAY - timedelta(days=60), "Landlord"),
        HistoricalTransaction(Decimal("15000"), TODAY - timedelta(days=30), "Landlord"),
        HistoricalTransaction(Decimal("15000"), TODAY - timedelta(days=1), "Landlord"),
    ]
    ctx = build_counterpart_context("Landlord", history, TODAY)
    assert ctx.is_first_time_counterpart is False
    assert ctx.previous_payment_count == 3
    assert ctx.historical_average_amount == Decimal("15000.00")
    assert ctx.payment_frequency_days == 29.5
    assert ctx.last_paid_on == TODAY - timedelta(days=1)


def test_counterpart_matching_ignores_case_and_whitespace():
    history = [
        HistoricalTransaction(Decimal("500"), TODAY - timedelta(days=2), "  Mama Nkechi  ")
    ]
    ctx = build_counterpart_context("mama nkechi", history, TODAY)
    assert ctx.is_first_time_counterpart is False
    assert ctx.previous_payment_count == 1


def test_amount_far_above_the_counterpart_norm_triggers_caution():
    history = [
        HistoricalTransaction(Decimal("2000"), TODAY - timedelta(days=i * 7), "Mama Nkechi")
        for i in range(1, 5)
    ]
    result = evaluate_transaction(
        current_balance="500000",
        proposed_amount="20000",  # 10x the usual
        history=history,
        counterpart="Mama Nkechi",
        as_of=TODAY,
    )
    assert result.verdict is Verdict.CAUTION
    assert any(r.startswith("unusual_amount_for_counterpart") for r in result.reasons)


def test_amount_in_line_with_the_counterpart_norm_stays_safe():
    history = [
        HistoricalTransaction(Decimal("2000"), TODAY - timedelta(days=i * 7), "Mama Nkechi")
        for i in range(1, 5)
    ]
    result = evaluate_transaction(
        current_balance="500000",
        proposed_amount="2100",
        history=history,
        counterpart="Mama Nkechi",
        as_of=TODAY,
    )
    assert result.verdict is Verdict.SAFE


# --------------------------------------------------------------------------
# determinism + the AI contract
# --------------------------------------------------------------------------

def test_identical_inputs_produce_identical_output():
    kwargs = dict(
        current_balance="47500",
        proposed_amount="12000",
        obligations=[Obligation("Rent", Decimal("25000"), TODAY + timedelta(days=6))],
        history=steady_history(per_day="900"),
        counterpart="Landlord",
        as_of=TODAY,
    )
    first = evaluate_transaction(**kwargs)
    second = evaluate_transaction(**kwargs)
    assert first.to_numeric_justification() == second.to_numeric_justification()


def test_numeric_justification_is_json_safe_and_complete():
    """Every figure the AI may quote must be present, and serialisable."""
    import json

    result = evaluate_transaction(
        current_balance="47500",
        proposed_amount="12000",
        obligations=[Obligation("Rent", Decimal("25000"), TODAY + timedelta(days=6))],
        history=steady_history(per_day="900", counterpart="Landlord"),
        counterpart="Landlord",
        as_of=TODAY,
    )
    payload = result.to_numeric_justification()

    json.dumps(payload)  # must not raise

    for key in (
        "verdict",
        "current_balance",
        "proposed_amount",
        "resulting_balance",
        "pct_of_balance_used",
        "runway_days",
        "daily_spend_estimate",
        "daily_spend_source",
        "at_risk_obligations",
        "upcoming_obligations",
        "counterpart_context",
        "reasons",
    ):
        assert key in payload

    # Money must survive as exact 2dp strings, never floats.
    assert payload["resulting_balance"] == "35500.00"
    assert isinstance(payload["current_balance"], str)


def test_money_is_never_rendered_as_a_float():
    result = evaluate_transaction(
        current_balance="0.10", proposed_amount="0.07", as_of=TODAY
    )
    payload = result.to_numeric_justification()
    assert payload["resulting_balance"] == "0.03"
