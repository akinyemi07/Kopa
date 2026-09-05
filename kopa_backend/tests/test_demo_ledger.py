"""The demo balance must actually drop after a send, and never go negative.

These exercise the real API layer via TestClient rather than the ledger
module in isolation, because the behaviour under test spans two endpoints
(balance and transactions) sharing one piece of process state — exactly what
a unit test on either endpoint alone would miss.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app
from app.services import demo_ledger

DEMO_USER_ID = "11111111-1111-1111-1111-111111111111"


@pytest.fixture(autouse=True)
def _reset_ledger():
    """The ledger is process-global. Tests must not leak spend into each other."""
    demo_ledger.reset()
    yield
    demo_ledger.reset()


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("KOPA_DEMO_MODE", "true")
    get_settings.cache_clear()
    with TestClient(app) as c:
        yield c
    get_settings.cache_clear()


def _balance(client: TestClient) -> float:
    return float(client.get(f"/wallets/{DEMO_USER_ID}/balance").json()["balance"])


def _send(client: TestClient, amount: float, counterpart: str = "Mama Nkechi Stores"):
    return client.post(
        f"/transactions?user_id={DEMO_USER_ID}",
        json={"amount": amount, "counterpart": counterpart},
    )


def test_balance_drops_by_the_sent_amount(client):
    before = _balance(client)
    r = _send(client, 3000)
    assert r.status_code == 201
    assert _balance(client) == pytest.approx(before - 3000)


def test_balance_keeps_dropping_across_repeated_sends(client):
    start = _balance(client)
    _send(client, 1000, "A")
    _send(client, 2000, "B")
    assert _balance(client) == pytest.approx(start - 3000)


def test_cannot_send_more_than_the_current_balance(client):
    balance = _balance(client)
    r = _send(client, balance + 1, "QuickLoan NG")
    assert r.status_code == 400
    assert "available" in r.json()["detail"].lower()
    # And the rejected attempt must not have moved anything.
    assert _balance(client) == pytest.approx(balance)


def test_sending_exactly_the_full_balance_is_allowed(client):
    balance = _balance(client)
    r = _send(client, balance, "Landlord")
    assert r.status_code == 201
    assert _balance(client) == pytest.approx(0)


def test_the_hard_block_uses_the_already_reduced_balance(client):
    """The second send must be checked against what is left, not the original.

    Sending 40,000 against a ~47,500 balance succeeds. A second attempt at
    10,000 would total 50,000 against the original balance but only ~7,500 is
    actually left, and must be rejected.
    """
    start = _balance(client)
    first = _send(client, 40000, "QuickLoan NG")
    assert first.status_code == 201

    remaining = _balance(client)
    assert remaining == pytest.approx(start - 40000)

    second = _send(client, 10000, "QuickLoan NG")
    assert second.status_code == 400
    assert _balance(client) == pytest.approx(remaining)


def test_zero_or_negative_amount_is_rejected_before_it_reaches_the_ledger(client):
    r = _send(client, 0, "Someone")
    assert r.status_code == 422  # schema validation: amount must be > 0
    assert demo_ledger.demo_spent() == 0


# --------------------------------------------------------------------------
# transaction history
# --------------------------------------------------------------------------

def test_history_is_empty_before_any_send(client):
    r = client.get(f"/transactions?user_id={DEMO_USER_ID}")
    assert r.status_code == 200
    assert r.json() == []


def test_a_send_appears_in_history_immediately(client):
    _send(client, 3000, "Mama Nkechi Stores")

    rows = client.get(f"/transactions?user_id={DEMO_USER_ID}").json()
    assert len(rows) == 1
    row = rows[0]
    assert row["amount"] == "3000"
    assert row["counterpart"] == "Mama Nkechi Stores"
    assert row["direction"] == "outbound"
    assert row["status"] == "demo"
    # Never mistaken for a real BMONI transaction.
    assert row["bmoni_txn_ref"] is None


def test_history_is_most_recent_first(client):
    _send(client, 1000, "First")
    _send(client, 2000, "Second")

    rows = client.get(f"/transactions?user_id={DEMO_USER_ID}").json()
    assert [r["counterpart"] for r in rows] == ["Second", "First"]


def test_a_rejected_overspend_does_not_appear_in_history(client):
    balance = _balance(client)
    _send(client, balance + 1, "QuickLoan NG")  # rejected, see test above

    rows = client.get(f"/transactions?user_id={DEMO_USER_ID}").json()
    assert rows == []
