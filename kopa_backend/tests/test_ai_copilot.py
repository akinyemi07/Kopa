"""Tests for the AI explanation layer.

These focus on the property that matters most for judging: the AI is optional.
Whatever it does — fail, hang, or produce nonsense — the deterministic safety
decision still reaches the user intact.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.services.ai_copilot import (
    Explanation,
    build_user_prompt,
    explain,
    extract_followup_amount,
    fallback_explanation,
)
from app.services.safety_engine import (
    HistoricalTransaction,
    Obligation,
    evaluate_transaction,
)

TODAY = date(2026, 9, 4)


@pytest.fixture
def unsafe_justification() -> dict:
    result = evaluate_transaction(
        current_balance="30000",
        proposed_amount="20000",
        obligations=[Obligation("Rent", Decimal("25000"), TODAY + timedelta(days=5))],
        history=[
            HistoricalTransaction(Decimal("500"), TODAY - timedelta(days=i))
            for i in range(1, 21)
        ],
        counterpart="Landlord",
        as_of=TODAY,
    )
    return result.to_numeric_justification()


@pytest.fixture
def safe_justification() -> dict:
    result = evaluate_transaction(
        current_balance="500000",
        proposed_amount="5000",
        history=[
            HistoricalTransaction(Decimal("1000"), TODAY - timedelta(days=i))
            for i in range(1, 21)
        ],
        as_of=TODAY,
    )
    return result.to_numeric_justification()


def ai_settings(**kw) -> Settings:
    # _env_file=None is load-bearing: without it, pydantic-settings still
    # reads the developer's real kopa_backend/.env underneath these explicit
    # kwargs, so a real GROQ_API_KEY on disk turns a "no provider configured"
    # test into a live network call. Explicit kwargs here are the only
    # config these tests should ever see.
    return Settings(
        _env_file=None,
        anthropic_api_key="test-key",
        groq_api_key="",
        kopa_ai_model="claude-sonnet-5",
        **kw,
    )


class FakeClient:
    """Stands in for the Anthropic client."""

    def __init__(self, text: str | None = None, raises: Exception | None = None):
        self._text = text
        self._raises = raises
        self.messages = SimpleNamespace(create=self._create)
        self.last_kwargs: dict = {}

    def _create(self, **kwargs):
        self.last_kwargs = kwargs
        if self._raises:
            raise self._raises
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=self._text)]
        )


# --------------------------------------------------------------------------
# the prompt carries the facts
# --------------------------------------------------------------------------

def test_prompt_contains_every_engine_figure(unsafe_justification):
    prompt = build_user_prompt(unsafe_justification)
    assert "UNSAFE" in prompt
    assert unsafe_justification["resulting_balance"] in prompt
    assert unsafe_justification["proposed_amount"] in prompt
    assert unsafe_justification["current_balance"] in prompt
    assert "Rent" in prompt
    assert "25000.00" in prompt


def test_prompt_states_plainly_when_runway_is_unavailable():
    result = evaluate_transaction(
        current_balance="50000", proposed_amount="1000", history=[], as_of=TODAY
    )
    prompt = build_user_prompt(result.to_numeric_justification())
    assert "NOT AVAILABLE" in prompt
    assert "rather than guessing" in prompt


def test_prompt_flags_a_first_time_recipient(safe_justification):
    result = evaluate_transaction(
        current_balance="50000",
        proposed_amount="1000",
        counterpart="New Vendor",
        history=[],
        as_of=TODAY,
    )
    prompt = build_user_prompt(result.to_numeric_justification())
    assert "NO record of any previous payment" in prompt


# --------------------------------------------------------------------------
# graceful degradation — the scored claim
# --------------------------------------------------------------------------

def test_missing_api_key_falls_back_rather_than_failing(unsafe_justification):
    result = explain(
        unsafe_justification,
        Settings(_env_file=None, anthropic_api_key="", groq_api_key=""),
    )
    assert result.is_fallback is True
    assert result.failure_reason == "ai_not_configured"
    assert unsafe_justification["resulting_balance"] in result.text


def test_api_exception_falls_back(unsafe_justification):
    client = FakeClient(raises=RuntimeError("upstream exploded"))
    result = explain(unsafe_justification, ai_settings(), client=client)
    assert result.is_fallback is True
    assert "RuntimeError" in (result.failure_reason or "")
    assert result.text  # the user still gets an explanation


def test_timeout_falls_back(unsafe_justification):
    client = FakeClient(raises=TimeoutError("timed out"))
    result = explain(unsafe_justification, ai_settings(), client=client)
    assert result.is_fallback is True
    assert result.text


def test_successful_call_is_not_marked_as_fallback(safe_justification):
    client = FakeClient(
        text="Sending NGN 5000.00 leaves you NGN 495000.00, a small share of your "
             "balance. Your usual spending is well covered. This looks manageable."
    )
    result = explain(safe_justification, ai_settings(), client=client)
    assert result.is_fallback is False
    assert result.model == "claude-sonnet-5"
    assert "495000.00" in result.text


def test_the_model_is_sent_the_system_prompt_and_the_figures(safe_justification):
    client = FakeClient(text="A perfectly reasonable explanation of the situation here.")
    explain(safe_justification, ai_settings(), client=client)
    assert "deterministic calculator" in client.last_kwargs["system"]
    assert "Never compute, estimate" in client.last_kwargs["system"]
    assert safe_justification["resulting_balance"] in (
        client.last_kwargs["messages"][0]["content"]
    )


# --------------------------------------------------------------------------
# validation — the model cannot override the verdict
# --------------------------------------------------------------------------

def test_model_contradicting_an_unsafe_verdict_is_rejected(unsafe_justification):
    client = FakeClient(
        text="Go ahead, this is safe and there is no risk at all to your account."
    )
    result = explain(unsafe_justification, ai_settings(), client=client)
    assert result.is_fallback is True
    assert "contradicts unsafe verdict" in (result.failure_reason or "")
    # And the user sees the correct, deterministic account instead.
    assert "strongly suggest reconsidering" in result.text


def test_guarantee_language_is_rejected(safe_justification):
    client = FakeClient(
        text="This transaction is guaranteed to be fine and is completely risk-free "
             "for your finances going forward."
    )
    result = explain(safe_justification, ai_settings(), client=client)
    assert result.is_fallback is True
    assert "guarantee" in (result.failure_reason or "")


def test_invented_number_is_rejected(unsafe_justification):
    """The failure that would make KOPA dangerous rather than merely wrong.

    Every figure in the response must trace back to the engine. A fluent,
    confident, entirely wrong balance is exactly what a weaker narration model
    produces, and exactly what must never reach a user.
    """
    client = FakeClient(
        text="Sending this would leave you with NGN 41250.00, which should "
             "still cover your rent comfortably this month."
    )
    result = explain(unsafe_justification, ai_settings(), client=client)
    assert result.is_fallback is True
    assert "invented numbers" in (result.failure_reason or "")
    assert "41250" in (result.failure_reason or "")


def test_engine_figures_are_accepted_verbatim(unsafe_justification):
    client = FakeClient(
        text="Sending NGN 20000.00 would leave you NGN 10000.00, and your rent "
             "of NGN 25000.00 is due on 2026-09-09. Consider waiting."
    )
    result = explain(unsafe_justification, ai_settings(), client=client)
    assert result.is_fallback is False, result.failure_reason


def test_thousands_separators_do_not_trip_the_guard(unsafe_justification):
    """25,000 and 25000.00 are the same figure and must compare equal."""
    client = FakeClient(
        text="This leaves NGN 10,000.00 against rent of NGN 25,000.00 that is "
             "already due. We suggest reconsidering this transfer today."
    )
    result = explain(unsafe_justification, ai_settings(), client=client)
    assert result.is_fallback is False, result.failure_reason


def test_rounded_percentage_is_accepted(safe_justification):
    """A legitimately rounded presentation of a computed figure is not invented."""
    pct = safe_justification["pct_of_balance_used"]  # 1.0
    assert pct == 1.0
    client = FakeClient(
        text=f"This uses about {pct}% of your balance, leaving "
             f"NGN {safe_justification['resulting_balance']}. That looks fine."
    )
    result = explain(safe_justification, ai_settings(), client=client)
    assert result.is_fallback is False, result.failure_reason


def test_date_components_are_not_treated_as_invented(unsafe_justification):
    """"due on the 9th" quotes a supplied date rather than inventing a number."""
    client = FakeClient(
        text="Your rent is due on the 9th and this transfer would not leave "
             "enough to cover it. We suggest holding off for now."
    )
    result = explain(unsafe_justification, ai_settings(), client=client)
    assert result.is_fallback is False, result.failure_reason


def test_empty_response_is_rejected(safe_justification):
    result = explain(safe_justification, ai_settings(), client=FakeClient(text="   "))
    assert result.is_fallback is True
    assert "too short" in (result.failure_reason or "")


def test_runaway_response_is_rejected(safe_justification):
    result = explain(safe_justification, ai_settings(), client=FakeClient(text="x" * 5000))
    assert result.is_fallback is True
    assert "too long" in (result.failure_reason or "")


# --------------------------------------------------------------------------
# the fallback itself must be correct
# --------------------------------------------------------------------------

def test_fallback_quotes_the_engine_numbers_exactly(unsafe_justification):
    text = fallback_explanation(unsafe_justification)
    assert unsafe_justification["resulting_balance"] in text
    assert unsafe_justification["proposed_amount"] in text
    assert "Rent" in text


def test_fallback_is_honest_about_missing_history():
    result = evaluate_transaction(
        current_balance="50000", proposed_amount="1000", history=[], as_of=TODAY
    )
    text = fallback_explanation(result.to_numeric_justification())
    assert "does not have enough recent spending history" in text


def test_fallback_never_promises_safety(safe_justification):
    text = fallback_explanation(safe_justification)
    assert "Based on the information available to KOPA" in text
    assert "guarantee" not in text.lower()


# --------------------------------------------------------------------------
# follow-up parsing
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "question,expected",
    [
        ("what if I only send half?", "10000.00"),
        ("what if I send a quarter instead", "5000.00"),
        ("what if I send 5000 instead?", "5000.00"),
        ("what about 12,500?", "12500.00"),
        ("could I do 15k instead", "15000.00"),
    ],
)
def test_followup_amounts_are_parsed(question, expected):
    amount, _ = extract_followup_amount(question, "20000.00")
    assert amount == expected


def test_unparseable_followup_reports_failure_rather_than_guessing():
    amount, how = extract_followup_amount("what if I wait until payday?", "20000.00")
    assert amount is None
    assert "no amount could be read" in how
