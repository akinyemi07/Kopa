"""Wallet and onboarding endpoints.

Every call here is a proxy: the Flutter app asks KOPA, KOPA asks BMONI with the
partner key. The app never holds that key.

The one thing that does NOT pass through here is signing. The device generates
its own key and produces signatures locally; KOPA only ever sees the resulting
address and the signature hex.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.base import get_db
from app.models import KycStatus, User, Wallet, WalletStatus
from app.schemas import (
    BalanceResponse,
    CompleteWalletRequest,
    CreateUserRequest,
    CreateWalletRequest,
    KycRequest,
    OwnerProofChallengeResponse,
    UserResponse,
    WalletResponse,
)
from app.services.bmoni_client import BmoniClient, BmoniError
from app.services import demo_ledger
from app.services.demo_data import demo_balance

logger = logging.getLogger(__name__)

router = APIRouter(tags=["wallets"])


def _client() -> BmoniClient:
    try:
        return BmoniClient()
    except BmoniError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, exc.message) from exc


def _bmoni_error(exc: BmoniError) -> HTTPException:
    """Surface a user-safe message; the technical detail stays in the logs."""
    logger.warning("bmoni failure: %s (%s)", exc.message, exc.detail)
    code = {
        400: status.HTTP_400_BAD_REQUEST,
        403: status.HTTP_403_FORBIDDEN,
        404: status.HTTP_404_NOT_FOUND,
        409: status.HTTP_409_CONFLICT,
    }.get(exc.status or 0, status.HTTP_502_BAD_GATEWAY)
    return HTTPException(code, exc.message)


@router.post("/users", response_model=UserResponse, status_code=201)
def create_user(payload: CreateUserRequest, db: Session = Depends(get_db)) -> UserResponse:
    """Stage 1 — register with BMONI and mirror the user locally."""
    try:
        bmoni_user = _client().create_user(
            first_name=payload.first_name,
            last_name=payload.last_name,
            email=payload.email,
            phone_number=payload.phone_number,
        )
    except BmoniError as exc:
        raise _bmoni_error(exc) from exc

    user = User(
        bmoni_user_ref=bmoni_user["bmoniUserId"],
        display_name=f"{payload.first_name} {payload.last_name}".strip(),
        phone_number=payload.phone_number,
        kyc_status=KycStatus.NOT_STARTED,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return UserResponse.model_validate(user)


@router.post(
    "/users/{user_id}/wallet/challenge", response_model=OwnerProofChallengeResponse
)
def wallet_challenge(
    user_id: str, payload: CreateWalletRequest, db: Session = Depends(get_db)
) -> OwnerProofChallengeResponse:
    """Stage 2a — get the message the device must sign to prove key ownership.

    The device has already generated its keypair via `BmoniEmbeddedSdk.initWallet()`
    and sends only the resulting public address.
    """
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    try:
        challenge = _client().create_owner_proof_challenge(
            user.bmoni_user_ref, payload.owner_address
        )
    except BmoniError as exc:
        raise _bmoni_error(exc) from exc

    return OwnerProofChallengeResponse(
        challenge_id=challenge.challenge_id,
        message=challenge.message,
        expires_at=challenge.expires_at,
    )


@router.post("/users/{user_id}/wallet", response_model=WalletResponse, status_code=201)
def create_wallet(
    user_id: str, payload: CompleteWalletRequest, db: Session = Depends(get_db)
) -> WalletResponse:
    """Stage 2b — deploy the smart wallet using the device's EIP-191 signature."""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    try:
        wallet = _client().create_smart_wallet(
            user.bmoni_user_ref,
            owner_address=payload.owner_address,
            challenge_id=payload.challenge_id,
            owner_proof_signature=payload.owner_proof_signature,
        )
    except BmoniError as exc:
        raise _bmoni_error(exc) from exc

    row = Wallet(
        user_id=user.id,
        bmoni_wallet_ref=wallet.smart_wallet_id,
        wallet_address=wallet.address,
        owner_address=payload.owner_address,
        currency=wallet.currency,
        status=WalletStatus.ACTIVE if wallet.is_active else WalletStatus.PENDING,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return WalletResponse.model_validate(row)


@router.post("/wallets/kyc", status_code=202)
def submit_kyc(
    user_id: str, payload: KycRequest, db: Session = Depends(get_db)
) -> dict[str, object]:
    """Stage 3 + 4 — submit the KYC profile, then activate the NGN rail.

    NOTE on the request shape: BMONI's published quickstart shows an
    `addressDetails` property, which the live API rejects. The accepted
    top-level keys are personalInfo / address / employment / sourceOfFunds /
    identificationNumbers, and identificationNumbers must be an ARRAY. Verified
    against the sandbox 2026-09-04.
    """
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    wallet = next((w for w in user.wallets), None)
    if wallet is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "A wallet must exist before onboarding — BMONI needs its address.",
        )

    client = _client()
    first, _, last = user.display_name.partition(" ")

    try:
        client.patch_kyc(
            user.bmoni_user_ref,
            {
                "personalInfo": {
                    "firstName": first,
                    "lastName": last or first,
                    "dateOfBirth": payload.date_of_birth.isoformat(),
                    "phoneNumber": user.phone_number,
                },
                "address": {
                    "street": payload.street,
                    "city": payload.city,
                    "state": payload.state,
                    "postalCode": payload.postal_code,
                    "countryCode": "NGA",
                },
                "identificationNumbers": [
                    {
                        "type": "bvn",
                        "number": payload.bvn,
                        "issuingCountryCode": "NGA",
                    }
                ],
            },
        )
        user.kyc_status = KycStatus.SUBMITTED
        db.commit()

        result = client.start_nigeria(
            user.bmoni_user_ref,
            bvn=payload.bvn,
            wallet_address=wallet.owner_address or wallet.wallet_address or "",
        )
    except BmoniError as exc:
        raise _bmoni_error(exc) from exc

    status_block = result.get("status", {})
    if status_block.get("hasBvn") and status_block.get("hasLocalWallet"):
        user.kyc_status = KycStatus.ACTIVE
        db.commit()

    return {"kyc_status": user.kyc_status.value, "onboarding": result}


@router.get("/wallets/{user_id}/balance", response_model=BalanceResponse)
def get_balance(user_id: str, db: Session = Depends(get_db)) -> BalanceResponse:
    """Live balance from BMONI, or the seeded figure in demo mode.

    `is_demo` is always reported honestly so the UI can label it.
    """
    settings = get_settings()
    now = datetime.now(timezone.utc)

    if settings.kopa_demo_mode:
        return BalanceResponse(
            currency="NGN",
            balance=demo_balance() - demo_ledger.demo_spent(),
            is_demo=True,
            as_of=now,
        )

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    try:
        balances = _client().get_balances(user.bmoni_user_ref)
    except BmoniError as exc:
        raise _bmoni_error(exc) from exc

    for b in balances:
        if b.currency.upper() in {"NGN", "CNGN"} and not b.error:
            from decimal import Decimal

            return BalanceResponse(
                currency="NGN", balance=Decimal(b.balance), is_demo=False, as_of=now
            )

    raise HTTPException(status.HTTP_404_NOT_FOUND, "No NGN wallet balance found")
