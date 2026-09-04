"""Seed the demo user, wallet, history and obligations into PostgreSQL.

Demo mode serves the same figures from memory without a database, so this
script is for demonstrating the full persisted path — the audit log, the
history query, and the obligation lookups all reading from Postgres.

The data is SYNTHETIC and describes a fictional person. It is never presented
as a real user's financial record.

Idempotent: re-running replaces the demo user's rows rather than duplicating
them.

Usage:
    cd kopa_backend
    ../.venv/Scripts/python.exe ../scripts/seed_demo.py
"""

from __future__ import annotations

import sys
import uuid
from datetime import datetime, time, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "kopa_backend"))

from sqlalchemy import delete, select  # noqa: E402

from app.db.base import Base, SessionLocal, engine  # noqa: E402
from app.models import (  # noqa: E402
    KycStatus,
    Obligation,
    Transaction,
    TransactionDirection,
    TransactionStatus,
    User,
    Wallet,
    WalletStatus,
)
from app.services.demo_data import (  # noqa: E402
    DEMO_CURRENCY,
    DEMO_USER_NAME,
    demo_history,
    demo_obligations,
)

# Fixed so the app, the docs and the seed all agree on one id.
DEMO_USER_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")

# The wallet actually provisioned during the M0a sandbox spike.
DEMO_BMONI_USER_REF = "2633ed62-0938-4666-8604-8565c712ddf5"
DEMO_WALLET_REF = "0cdd116e-ab84-4227-a290-ab79b9634657"
DEMO_WALLET_ADDRESS = "0xbDD35d2daA61866c1cAa085A93e2B46eAE669768"


def main() -> int:
    print("Creating tables if absent...")
    Base.metadata.create_all(engine)

    today = datetime.now(timezone.utc).date()

    with SessionLocal() as db:
        existing = db.get(User, DEMO_USER_ID)
        if existing is not None:
            print("Demo user exists — clearing previous seed data")
            db.execute(delete(Obligation).where(Obligation.user_id == DEMO_USER_ID))
            wallet_ids = db.scalars(
                select(Wallet.id).where(Wallet.user_id == DEMO_USER_ID)
            ).all()
            if wallet_ids:
                db.execute(
                    delete(Transaction).where(Transaction.wallet_id.in_(wallet_ids))
                )
            db.execute(delete(Wallet).where(Wallet.user_id == DEMO_USER_ID))
            db.delete(existing)
            db.commit()

        user = User(
            id=DEMO_USER_ID,
            bmoni_user_ref=DEMO_BMONI_USER_REF,
            display_name=DEMO_USER_NAME,
            phone_number="+2348088485390",
            kyc_status=KycStatus.ACTIVE,
        )
        db.add(user)

        wallet = Wallet(
            user_id=user.id,
            bmoni_wallet_ref=DEMO_WALLET_REF,
            wallet_address=DEMO_WALLET_ADDRESS,
            owner_address=None,  # the owner key lives on a device, not here
            currency=DEMO_CURRENCY,
            status=WalletStatus.ACTIVE,
        )
        db.add(wallet)
        db.flush()

        history = demo_history(today)
        for tx in history:
            db.add(
                Transaction(
                    wallet_id=wallet.id,
                    bmoni_txn_ref=None,  # seeded, so never a real BMONI reference
                    amount=tx.amount,
                    currency=DEMO_CURRENCY,
                    direction=TransactionDirection.OUTBOUND,
                    counterpart=tx.counterpart,
                    status=TransactionStatus.DEMO,
                    description="Seeded demo transaction",
                    occurred_at=datetime.combine(
                        tx.occurred_on, time(12, 0), tzinfo=timezone.utc
                    ),
                )
            )

        obligations = demo_obligations(today)
        for ob in obligations:
            db.add(
                Obligation(
                    user_id=user.id,
                    description=ob.description,
                    amount=ob.amount,
                    currency=DEMO_CURRENCY,
                    due_date=ob.due_date,
                )
            )

        db.commit()

    print()
    print("=" * 62)
    print("Seed complete")
    print(f"  user id      : {DEMO_USER_ID}")
    print(f"  wallet       : {DEMO_WALLET_ADDRESS}")
    print(f"  transactions : {len(history)}")
    print(f"  obligations  : {len(obligations)}")
    for ob in obligations:
        print(f"      {ob.description}: {ob.amount} due {ob.due_date}")
    print("=" * 62)
    print()
    print("Try it:")
    print("  curl -X POST localhost:8000/decisions/evaluate \\")
    print("    -H 'Content-Type: application/json' \\")
    print(f"    -d '{{\"user_id\":\"{DEMO_USER_ID}\",")
    print('         "proposed_amount":30000,"counterpart":"QuickLoan NG"}\'')
    return 0


if __name__ == "__main__":
    sys.exit(main())
