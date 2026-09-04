"""KOPA persistence models.

KOPA stores what it needs to make a safety decision and to keep an audit trail
of the decisions it made. It deliberately does NOT store:

  * wallet private keys (they exist only in the device secure element)
  * PINs (the SDK holds only a PBKDF2 digest, on device)
  * BMONI API credentials (environment only)
  * KYC document images (they go straight to BMONI and are not retained here)

Money is stored as NUMERIC, never as a float.
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class KycStatus(str, enum.Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    SUBMITTED = "submitted"
    ACTIVE = "active"
    FAILED = "failed"


class WalletStatus(str, enum.Enum):
    PENDING = "pending"
    ACTIVE = "active"
    INACTIVE = "inactive"


class TransactionDirection(str, enum.Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class TransactionStatus(str, enum.Enum):
    PENDING_APPROVALS = "pending_approvals"
    PENDING_SIGNATURES = "pending_signatures"
    COMPLETED = "completed"
    FAILED = "failed"
    #: A transaction produced in demo mode. Never presented as a real BMONI
    #: transaction — the UI labels it and it carries no bmoni_txn_ref.
    DEMO = "demo"


class Verdict(str, enum.Enum):
    SAFE = "safe"
    CAUTION = "caution"
    UNSAFE = "unsafe"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    bmoni_user_ref: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    phone_number: Mapped[str | None] = mapped_column(String(20))
    kyc_status: Mapped[KycStatus] = mapped_column(
        Enum(KycStatus, name="kyc_status"), default=KycStatus.NOT_STARTED
    )
    #: Manual fallback used by the safety engine when there is no history yet.
    daily_spend_estimate: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    wallets: Mapped[list["Wallet"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    obligations: Mapped[list["Obligation"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    decisions: Mapped[list["AiDecisionLog"]] = relationship(back_populates="user", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint(
            "daily_spend_estimate IS NULL OR daily_spend_estimate > 0",
            name="ck_users_daily_spend_positive",
        ),
    )


class Wallet(Base):
    __tablename__ = "wallets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    bmoni_wallet_ref: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    #: The on-chain smart account address. Public data — not a secret.
    wallet_address: Mapped[str | None] = mapped_column(String(64))
    #: The device-held owner address. Its PRIVATE key never reaches this server.
    owner_address: Mapped[str | None] = mapped_column(String(64))
    currency: Mapped[str] = mapped_column(String(8), default="NGN")
    status: Mapped[WalletStatus] = mapped_column(
        Enum(WalletStatus, name="wallet_status"), default=WalletStatus.PENDING
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship(back_populates="wallets")
    transactions: Mapped[list["Transaction"]] = relationship(
        back_populates="wallet", cascade="all, delete-orphan"
    )


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    wallet_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("wallets.id", ondelete="CASCADE"), index=True
    )
    #: BMONI's proposal id. NULL for demo-mode records, which is how a demo
    #: transaction is distinguished from a real one at the data layer.
    bmoni_txn_ref: Mapped[str | None] = mapped_column(String(64), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(String(8), default="NGN")
    direction: Mapped[TransactionDirection] = mapped_column(
        Enum(TransactionDirection, name="txn_direction")
    )
    counterpart: Mapped[str | None] = mapped_column(String(200), index=True)
    status: Mapped[TransactionStatus] = mapped_column(
        Enum(TransactionStatus, name="txn_status"), default=TransactionStatus.PENDING_APPROVALS
    )
    description: Mapped[str | None] = mapped_column(String(500))
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    wallet: Mapped[Wallet] = relationship(back_populates="transactions")

    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_transactions_amount_positive"),
        Index("ix_transactions_wallet_occurred", "wallet_id", "occurred_at"),
    )


class Obligation(Base):
    __tablename__ = "obligations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    description: Mapped[str] = mapped_column(String(200))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(String(8), default="NGN")
    due_date: Mapped[date] = mapped_column(Date, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship(back_populates="obligations")

    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_obligations_amount_positive"),
    )


class AiDecisionLog(Base):
    """An audit record of every safety decision KOPA reached.

    `numeric_justification` is the engine's output, stored verbatim. Because the
    engine is deterministic, any decision can be recomputed and checked against
    this row — which is what makes KOPA's AI claims auditable rather than
    asserted.
    """

    __tablename__ = "ai_decision_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("transactions.id", ondelete="SET NULL"), nullable=True
    )
    verdict: Mapped[Verdict] = mapped_column(Enum(Verdict, name="verdict"), index=True)
    numeric_justification: Mapped[dict] = mapped_column(JSONB)
    ai_explanation_text: Mapped[str | None] = mapped_column(Text)
    #: True when the explanation came from the deterministic template because the
    #: model was unavailable or its output failed validation.
    ai_is_fallback: Mapped[bool] = mapped_column(default=False)
    ai_model: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    user: Mapped[User] = relationship(back_populates="decisions")


__all__ = [
    "AiDecisionLog",
    "KycStatus",
    "Obligation",
    "Transaction",
    "TransactionDirection",
    "TransactionStatus",
    "User",
    "Verdict",
    "Wallet",
    "WalletStatus",
]
