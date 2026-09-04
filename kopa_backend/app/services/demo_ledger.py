"""In-memory running ledger for demo-mode sends.

Deliberately separate from `demo_data.py`, which stays pure and side-effect
free so the safety-engine tests it feeds stay deterministic. This module is
the opposite on purpose: it is process-level mutable state, and exists for
exactly one reason — a live demo should show the balance actually drop after
a send, rather than resetting to the same fixed figure on every page view.

This build has exactly one simulated demo user, so a single counter is
enough; there is no per-user keying to get wrong. It resets whenever the
server process restarts, which is a feature for a repeatable demo, not a
limitation — every fresh deploy starts from the same clean ₦47,500.
"""

from __future__ import annotations

from decimal import Decimal

_spent: Decimal = Decimal("0")


def demo_spent() -> Decimal:
    return _spent


def record_demo_send(amount: Decimal) -> None:
    global _spent
    _spent += amount


def reset() -> None:
    """Test-only. Never called from application code."""
    global _spent
    _spent = Decimal("0")
