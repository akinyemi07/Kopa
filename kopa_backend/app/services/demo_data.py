"""Seeded demo data for KOPA.

Two jobs, one dataset:

  1. **Demo mode.** When `KOPA_DEMO_MODE=true`, balance and history are served
     from here instead of BMONI, so a flaky sandbox cannot break a live
     demonstration. The safety engine and the AI layer still run for real on
     top of this data — only the BMONI reads are substituted.

  2. **Seeding.** `scripts/seed_demo.py` writes the same figures into Postgres.

The numbers are chosen so that both verdicts are reachable on demand rather than
by luck. See docs/demo-script.md for the exact expected output.

This is SYNTHETIC data describing a fictional person. It is not, and is never
presented as, a real user's financial record.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from app.services.safety_engine import HistoricalTransaction, Obligation

DEMO_USER_NAME = "Amaka O."
DEMO_CURRENCY = "NGN"

#: A month's earnings already partly spent — the position a typical user is in
#: when a request for money arrives.
DEMO_BALANCE = Decimal("47500.00")

#: Deliberate demo amounts. Verified against the engine in tests.
SAFE_DEMO_AMOUNT = Decimal("3000.00")
UNSAFE_DEMO_AMOUNT = Decimal("30000.00")

RECURRING_COUNTERPART = "Mama Nkechi Stores"
FIRST_TIME_COUNTERPART = "QuickLoan NG"

#: 18 days of outflows: daily transport and food, a weekly shop at the same
#: vendor, and a couple of one-off payments. Amounts vary the way real spending
#: does, so the runway estimate is not an artefact of a flat series.
_DAILY_PATTERN: list[tuple[int, str, str | None]] = [
    # (days_ago, amount, counterpart)
    (1, "850", "Danfo transport"),
    (1, "1200", "Mama Nkechi Stores"),
    (2, "600", "Danfo transport"),
    (2, "2500", "MTN airtime"),
    (3, "900", "Danfo transport"),
    (4, "750", "Danfo transport"),
    (4, "1800", "Shoprite"),
    (5, "600", "Danfo transport"),
    (6, "1100", "Danfo transport"),
    (7, "800", "Danfo transport"),
    (8, "2000", "Mama Nkechi Stores"),
    (8, "650", "Danfo transport"),
    (9, "900", "Danfo transport"),
    (10, "1500", "NEPA prepaid"),
    (11, "700", "Danfo transport"),
    (12, "850", "Danfo transport"),
    (13, "1200", "Shoprite"),
    (14, "600", "Danfo transport"),
    (15, "2200", "Mama Nkechi Stores"),
    (15, "800", "Danfo transport"),
    (16, "750", "Danfo transport"),
    (17, "1000", "MTN data"),
    (18, "900", "Danfo transport"),
]


def demo_history(as_of: date) -> list[HistoricalTransaction]:
    """18 days of synthetic outflows, ending yesterday."""
    return [
        HistoricalTransaction(
            amount=Decimal(amount),
            occurred_on=as_of - timedelta(days=days_ago),
            counterpart=counterpart,
        )
        for days_ago, amount, counterpart in _DAILY_PATTERN
    ]


def demo_obligations(as_of: date) -> list[Obligation]:
    """The commitments that make a merely-affordable transfer actually unsafe."""
    return [
        Obligation("Rent", Decimal("25000.00"), as_of + timedelta(days=6)),
        Obligation("Data subscription", Decimal("5000.00"), as_of + timedelta(days=12)),
    ]


def demo_balance() -> Decimal:
    return DEMO_BALANCE
