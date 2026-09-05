"""In-memory running ledger for demo-mode sends.

Deliberately separate from `demo_data.py`, which stays pure and side-effect
free so the safety-engine tests it feeds stay deterministic. This module is
the opposite on purpose: it is process-level mutable state, and exists for
two things a live demo needs that a pure function cannot give it — a balance
that actually drops after a send, and a history of what was sent.

This build has exactly one simulated demo user, so one shared ledger is
enough; there is no per-user keying to get wrong. It resets whenever the
server process restarts, which is a feature for a repeatable demo, not a
limitation — every fresh deploy starts from the same clean ₦47,500 with an
empty history.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

_spent: Decimal = Decimal("0")
_sends: list["DemoSend"] = []


@dataclass(frozen=True)
class DemoSend:
    id: uuid.UUID
    amount: Decimal
    counterpart: str | None
    occurred_at: datetime


def demo_spent() -> Decimal:
    return _spent


def record_demo_send(amount: Decimal, counterpart: str | None = None) -> DemoSend:
    global _spent
    _spent += amount
    record = DemoSend(
        id=uuid.uuid4(),
        amount=amount,
        counterpart=counterpart,
        occurred_at=datetime.now(timezone.utc),
    )
    _sends.append(record)
    return record


def demo_sends() -> list[DemoSend]:
    """Most recent first, matching the real transaction history's ordering."""
    return list(reversed(_sends))


def reset() -> None:
    """Test-only. Never called from application code."""
    global _spent, _sends
    _spent = Decimal("0")
    _sends = []
