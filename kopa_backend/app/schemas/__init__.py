"""Request and response schemas.

These are the contract with the Flutter app. They deliberately expose only what
the client needs — no database identifiers beyond the ones it must round-trip,
no BMONI internals, and never anything secret.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --------------------------------------------------------------------------
# users / wallets
# --------------------------------------------------------------------------

class CreateUserRequest(BaseModel):
    first_name: str = Field(min_length=1, max_length=60)
    last_name: str = Field(min_length=1, max_length=60)
    email: str = Field(min_length=3, max_length=200)
    phone_number: str = Field(min_length=10, max_length=20)


class UserResponse(ORMModel):
    id: uuid.UUID
    bmoni_user_ref: str
    display_name: str
    kyc_status: str
    daily_spend_estimate: Decimal | None = None
    created_at: datetime


class WalletResponse(ORMModel):
    id: uuid.UUID
    bmoni_wallet_ref: str
    wallet_address: str | None
    currency: str
    status: str


class CreateWalletRequest(BaseModel):
    """The device has generated a key and needs a challenge to sign."""

    owner_address: str = Field(min_length=42, max_length=42, pattern=r"^0x[0-9a-fA-F]{40}$")


class OwnerProofChallengeResponse(BaseModel):
    challenge_id: str
    message: str
    expires_at: str | None = None


class CompleteWalletRequest(BaseModel):
    """The device has signed the challenge with signMessage (EIP-191)."""

    owner_address: str = Field(pattern=r"^0x[0-9a-fA-F]{40}$")
    challenge_id: str
    owner_proof_signature: str = Field(pattern=r"^0x[0-9a-fA-F]{130}$")


class KycRequest(BaseModel):
    bvn: str = Field(min_length=11, max_length=11, pattern=r"^\d{11}$")
    date_of_birth: date
    street: str = Field(max_length=200)
    city: str = Field(max_length=100)
    state: str = Field(max_length=100)
    postal_code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class BalanceResponse(BaseModel):
    currency: str
    balance: Decimal
    #: True when this figure came from seeded demo data rather than BMONI.
    is_demo: bool = False
    as_of: datetime


# --------------------------------------------------------------------------
# obligations
# --------------------------------------------------------------------------

class CreateObligationRequest(BaseModel):
    description: str = Field(min_length=1, max_length=200)
    amount: Decimal = Field(gt=0)
    due_date: date


class ObligationResponse(ORMModel):
    id: uuid.UUID
    description: str
    amount: Decimal
    currency: str
    due_date: date


# --------------------------------------------------------------------------
# transactions
# --------------------------------------------------------------------------

class TransactionResponse(ORMModel):
    id: uuid.UUID
    bmoni_txn_ref: str | None
    amount: Decimal
    currency: str
    direction: str
    counterpart: str | None
    status: str
    description: str | None
    occurred_at: datetime


class CreateTransactionRequest(BaseModel):
    """Start a transfer. Returns a proposal for the device to sign."""

    amount: Decimal = Field(gt=0)
    to_address: str | None = Field(default=None, pattern=r"^0x[0-9a-fA-F]{40}$")
    counterpart: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=500)


class ProposalResponse(BaseModel):
    proposal_id: str
    status: str
    #: The raw 32-byte digest the device signs with signTransactionHash.
    #: Absent until the proposal reaches PENDING_SIGNATURES.
    hash_to_sign: str | None = None
    is_demo: bool = False


class SubmitSignatureRequest(BaseModel):
    proposal_id: str
    signature: str = Field(pattern=r"^0x[0-9a-fA-F]{130}$")


# --------------------------------------------------------------------------
# decisions — the core of KOPA
# --------------------------------------------------------------------------

class EvaluateRequest(BaseModel):
    user_id: uuid.UUID
    proposed_amount: Decimal = Field(gt=0, description="Amount the user wants to send")
    counterpart: str | None = Field(default=None, max_length=200)
    type: Literal["personal", "merchant"] = "personal"


class ObligationFact(BaseModel):
    description: str
    amount: str
    due_date: str


class CounterpartFacts(BaseModel):
    counterpart: str | None
    is_first_time_counterpart: bool
    previous_payment_count: int
    historical_average_amount: str | None
    last_paid_on: str | None
    payment_frequency_days: float | None


class NumericJustification(BaseModel):
    """Every figure behind the verdict, exactly as the engine computed it.

    Money is carried as decimal STRINGS, not floats, so the value the user sees
    is bit-for-bit the value the engine produced.
    """

    currency: str
    verdict: str
    current_balance: str
    proposed_amount: str
    resulting_balance: str
    pct_of_balance_used: float
    runway_days: int | None
    daily_spend_estimate: str | None
    daily_spend_source: str
    obligations_total: str
    at_risk_obligations: list[ObligationFact]
    upcoming_obligations: list[ObligationFact]
    counterpart_context: CounterpartFacts | None
    reasons: list[str]


class DecisionResponse(BaseModel):
    decision_id: uuid.UUID | None
    verdict: Literal["safe", "caution", "unsafe"]
    numeric_justification: NumericJustification
    ai_explanation: str
    #: True when the explanation is the deterministic template because the model
    #: was unavailable. The UI tells the user rather than hiding it.
    ai_is_fallback: bool
    ai_model: str | None = None
    is_demo: bool = False


class FollowupRequest(BaseModel):
    user_id: uuid.UUID
    original_amount: Decimal = Field(gt=0)
    question: str = Field(min_length=1, max_length=300)
    counterpart: str | None = Field(default=None, max_length=200)
    type: Literal["personal", "merchant"] = "personal"


class FollowupResponse(DecisionResponse):
    #: How KOPA read the question, shown to the user so an incorrect reading is
    #: visible rather than silently acted upon.
    interpreted_as: str
    understood: bool


# --------------------------------------------------------------------------
# health
# --------------------------------------------------------------------------

class HealthResponse(BaseModel):
    status: str
    database: str
    config: dict[str, Any]
