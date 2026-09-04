"""Transaction endpoints — the proposal / approve / sign chain.

This is where KOPA's security boundary is easiest to see. A transfer takes four
BMONI calls; three of them happen here, on the server, with the partner key. The
fourth — producing the signature over `hashToSign` — happens on the device,
because that is the only place the owner private key exists.

    POST /transactions          -> proposal + approve + fetch hashToSign
    (device signs hashToSign with BmoniEmbeddedSdk.signTransactionHash)
    POST /transactions/sign     -> submit the signature, record the result

The server can propose a transfer. It cannot complete one without the user's
device and their PIN.
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.base import get_db
from app.models import (
    Transaction,
    TransactionDirection,
    TransactionStatus,
    User,
    Wallet,
)
from app.schemas import (
    CreateTransactionRequest,
    ProposalResponse,
    SubmitSignatureRequest,
    TransactionResponse,
)
from app.services import demo_ledger
from app.services.bmoni_client import BmoniClient, BmoniError
from app.services.decision_service import DecisionService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/transactions", tags=["transactions"])

#: BMONI only exposes the signing payload once the proposal reaches
#: PENDING_SIGNATURES, so a 404 immediately after approval is expected.
SIGN_PAYLOAD_ATTEMPTS = 5
SIGN_PAYLOAD_DELAY_SECONDS = 1.5


def _client() -> BmoniClient:
    try:
        return BmoniClient()
    except BmoniError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, exc.message) from exc


def _require_wallet(db: Session, user_id: str) -> tuple[User, Wallet]:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    wallet = next((w for w in user.wallets), None)
    if wallet is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "This user has no wallet yet")
    return user, wallet


@router.post("", response_model=ProposalResponse, status_code=201)
def create_transaction(
    user_id: str, payload: CreateTransactionRequest, db: Session = Depends(get_db)
) -> ProposalResponse:
    """Create and approve a transfer proposal, and return the digest to sign.

    Nothing moves as a result of this call. It records intent and produces the
    hash the device must sign for the transfer to execute.
    """
    settings = get_settings()

    # Hard solvency check, independent of the risk-based safety verdict.
    # KOPA advises on risk (obligations, spending pattern, an unfamiliar
    # recipient) and deliberately never blocks those — "Send anyway" always
    # stays available. Sending money that is not there is not a judgement
    # call, though; it is impossible, the same way a bank refuses an
    # overdraft it never agreed to. This runs before ANY branch below, live
    # or demo, so it can never be bypassed by either path.
    user_for_balance = None if settings.kopa_demo_mode else db.get(User, user_id)
    current_balance, _ = DecisionService(db=db, settings=settings).get_balance(
        user_for_balance
    )
    if payload.amount > current_balance:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"You only have NGN {current_balance:.2f} available. "
            "Enter an amount within your balance.",
        )

    if settings.kopa_demo_mode:
        # Demo mode must not touch BMONI or the database at all — the same
        # reason /wallets/{id}/balance short-circuits before it. A deployment
        # with no DATABASE_URL configured (the public demo link) would 500 on
        # _require_wallet()'s db.get(User, ...) otherwise, which is exactly
        # what happened here before this existed: the demo-mode branch used to
        # run AFTER _require_wallet, so it never protected anything.
        #
        # Nothing is persisted to the database. bmoni_txn_ref stays absent and
        # status is DEMO everywhere a real transaction would carry a BMONI
        # reference, so a demo transfer can never be mistaken for a real one.
        # The in-memory ledger is the one exception -- it exists purely so the
        # demo balance visibly drops on the next fetch, the way a real send
        # would.
        demo_ledger.record_demo_send(payload.amount)
        return ProposalResponse(
            proposal_id=f"demo-{uuid.uuid4()}",
            status="DEMO",
            hash_to_sign=None,
            is_demo=True,
        )

    user, wallet = _require_wallet(db, user_id)

    if not payload.to_address:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "A recipient wallet address is required for a live transfer.",
        )

    client = _client()
    try:
        created = client.create_transfer_proposal(
            user.bmoni_user_ref,
            wallet.bmoni_wallet_ref,
            amount=f"{payload.amount:.2f}",
            to_address=payload.to_address,
            description=payload.description,
        )
        proposal = (created.get("data") or created).get("proposal") or created
        proposal_id = proposal["id"]

        client.approve_proposal(user.bmoni_user_ref, proposal_id)

        hash_to_sign = None
        for attempt in range(SIGN_PAYLOAD_ATTEMPTS):
            try:
                sign_payload = client.get_sign_payload(user.bmoni_user_ref, proposal_id)
                hash_to_sign = sign_payload.get("hashToSign")
                if hash_to_sign:
                    break
            except BmoniError as exc:
                if exc.status != 404 or attempt == SIGN_PAYLOAD_ATTEMPTS - 1:
                    raise
            time.sleep(SIGN_PAYLOAD_DELAY_SECONDS)

    except BmoniError as exc:
        logger.warning("proposal failed: %s (%s)", exc.message, exc.detail)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, exc.message) from exc

    row = Transaction(
        wallet_id=wallet.id,
        bmoni_txn_ref=proposal_id,
        amount=payload.amount,
        direction=TransactionDirection.OUTBOUND,
        counterpart=payload.counterpart,
        status=TransactionStatus.PENDING_SIGNATURES
        if hash_to_sign
        else TransactionStatus.PENDING_APPROVALS,
        description=payload.description,
    )
    db.add(row)
    db.commit()

    return ProposalResponse(
        proposal_id=proposal_id,
        status="PENDING_SIGNATURES" if hash_to_sign else "PENDING_APPROVALS",
        hash_to_sign=hash_to_sign,
        is_demo=False,
    )


@router.post("/sign", response_model=TransactionResponse)
def submit_signature(
    user_id: str, payload: SubmitSignatureRequest, db: Session = Depends(get_db)
) -> TransactionResponse:
    """Relay the device's signature to BMONI and reconcile the outcome.

    The signature must have been produced by `signTransactionHash` — a raw
    digest signature with NO EIP-191 prefix. A `signMessage` signature recovers
    to a different address and BMONI rejects it without saying why.
    """
    user, _ = _require_wallet(db, user_id)

    client = _client()
    try:
        client.submit_signature(user.bmoni_user_ref, payload.proposal_id, payload.signature)
        final = client.get_proposal(user.bmoni_user_ref, payload.proposal_id)
    except BmoniError as exc:
        logger.warning("signature submission failed: %s", exc.message)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, exc.message) from exc

    row = db.scalar(
        select(Transaction).where(Transaction.bmoni_txn_ref == payload.proposal_id)
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Transaction not found")

    remote = ((final.get("data") or final).get("proposal") or final).get("status", "")
    row.status = {
        "COMPLETED": TransactionStatus.COMPLETED,
        "FAILED": TransactionStatus.FAILED,
        "PENDING_SIGNATURES": TransactionStatus.PENDING_SIGNATURES,
        "PENDING_APPROVALS": TransactionStatus.PENDING_APPROVALS,
    }.get(str(remote).upper(), row.status)
    db.commit()
    db.refresh(row)

    return TransactionResponse.model_validate(row)


@router.get("", response_model=list[TransactionResponse])
def list_transactions(
    user_id: str, limit: int = 50, db: Session = Depends(get_db)
) -> list[TransactionResponse]:
    """Transaction history from KOPA's own records."""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    rows = db.scalars(
        select(Transaction)
        .join(Wallet, Transaction.wallet_id == Wallet.id)
        .where(Wallet.user_id == user.id)
        .order_by(Transaction.occurred_at.desc())
        .limit(min(limit, 200))
    ).all()
    return [TransactionResponse.model_validate(r) for r in rows]
