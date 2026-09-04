"""Orchestrates a safety decision.

The order here is the whole architecture, and it is deliberately rigid:

    1. gather facts      (BMONI balance, KOPA obligations, KOPA history)
    2. run the engine    (deterministic, auditable, LLM-free)
    3. narrate           (the LLM sees the engine's output, nothing more)
    4. record            (verdict + figures + prose, for audit)

Step 2 decides. Step 3 explains. If step 3 fails, the user still gets step 2.
Nothing in step 3 can alter the outcome of step 2.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models import (
    AiDecisionLog,
    Obligation as ObligationRow,
    Transaction,
    TransactionDirection,
    User,
    Verdict as VerdictEnum,
    Wallet,
)
from app.services import ai_copilot, demo_data
from app.services.bmoni_client import BmoniClient, BmoniError
from app.services.safety_engine import (
    HistoricalTransaction,
    Obligation,
    SafetyAssessment,
    evaluate_transaction,
)

logger = logging.getLogger(__name__)


class DecisionService:
    def __init__(
        self,
        db: Session | None = None,
        settings: Settings | None = None,
        bmoni: BmoniClient | None = None,
    ):
        self.db = db
        self.settings = settings or get_settings()
        self._bmoni = bmoni

    @property
    def demo_mode(self) -> bool:
        return self.settings.kopa_demo_mode

    # ------------------------------------------------------------ fact gathering

    def _bmoni_client(self) -> BmoniClient:
        if self._bmoni is None:
            self._bmoni = BmoniClient(self.settings)
        return self._bmoni

    def get_balance(self, user: User | None) -> tuple[Decimal, bool]:
        """Current spendable balance. Returns `(amount, is_demo)`.

        In demo mode this is seeded. Live, it is BMONI's figure — and if BMONI
        is unreachable we fall back to seeded data rather than failing the whole
        decision, because a safety check the user cannot run is worse than one
        computed against a clearly-labelled demo balance.
        """
        if self.demo_mode or user is None:
            return demo_data.demo_balance(), True

        try:
            balances = self._bmoni_client().get_balances(user.bmoni_user_ref)
        except BmoniError as exc:
            logger.warning("balance unavailable, using demo figure: %s", exc.message)
            return demo_data.demo_balance(), True

        for b in balances:
            if b.currency.upper() in {"NGN", "CNGN"} and not b.error:
                return Decimal(b.balance), False

        return Decimal("0"), False

    def get_obligations(self, user: User | None, as_of: date) -> list[Obligation]:
        if self.demo_mode or user is None or self.db is None:
            return demo_data.demo_obligations(as_of)

        rows = self.db.scalars(
            select(ObligationRow).where(ObligationRow.user_id == user.id)
        ).all()
        if not rows:
            return demo_data.demo_obligations(as_of)

        return [
            Obligation(description=r.description, amount=r.amount, due_date=r.due_date)
            for r in rows
        ]

    def get_history(self, user: User | None, as_of: date) -> list[HistoricalTransaction]:
        """Past outflows. KOPA's own records — BMONI is not the ledger here."""
        if self.demo_mode or user is None or self.db is None:
            return demo_data.demo_history(as_of)

        rows = self.db.scalars(
            select(Transaction)
            .join(Wallet, Transaction.wallet_id == Wallet.id)
            .where(
                Wallet.user_id == user.id,
                Transaction.direction == TransactionDirection.OUTBOUND,
            )
            .order_by(Transaction.occurred_at.desc())
            .limit(200)
        ).all()
        if not rows:
            return demo_data.demo_history(as_of)

        return [
            HistoricalTransaction(
                amount=r.amount,
                occurred_on=r.occurred_at.date(),
                counterpart=r.counterpart,
            )
            for r in rows
        ]

    # ------------------------------------------------------------ the decision

    def evaluate(
        self,
        *,
        user: User | None,
        proposed_amount: Decimal,
        counterpart: str | None = None,
        as_of: date | None = None,
        persist: bool = True,
    ) -> tuple[SafetyAssessment, ai_copilot.Explanation, uuid.UUID | None, bool]:
        """Run the full pipeline. Returns (assessment, explanation, log_id, is_demo)."""
        as_of = as_of or datetime.now(timezone.utc).date()

        balance, is_demo = self.get_balance(user)
        obligations = self.get_obligations(user, as_of)
        history = self.get_history(user, as_of)

        # 2. Deterministic verdict. No model involved, no network, no clock read.
        assessment = evaluate_transaction(
            current_balance=balance,
            proposed_amount=proposed_amount,
            obligations=obligations,
            history=history,
            counterpart=counterpart,
            daily_spend_estimate=(
                user.daily_spend_estimate if user and user.daily_spend_estimate else None
            ),
            as_of=as_of,
        )

        justification = assessment.to_numeric_justification()

        # 3. Narration. Cannot fail the request — explain() never raises.
        explanation = ai_copilot.explain(justification, self.settings)

        # 4. Audit record.
        log_id: uuid.UUID | None = None
        if persist and self.db is not None and user is not None:
            try:
                row = AiDecisionLog(
                    user_id=user.id,
                    verdict=VerdictEnum(assessment.verdict.value),
                    numeric_justification=justification,
                    ai_explanation_text=explanation.text,
                    ai_is_fallback=explanation.is_fallback,
                    ai_model=explanation.model,
                )
                self.db.add(row)
                self.db.commit()
                log_id = row.id
            except Exception:  # noqa: BLE001
                # An audit-write failure must not deny the user their verdict.
                logger.exception("could not persist decision log")
                self.db.rollback()

        return assessment, explanation, log_id, is_demo

    # ------------------------------------------------------------ follow-ups

    def followup(
        self,
        *,
        user: User | None,
        original_amount: Decimal,
        question: str,
        counterpart: str | None = None,
        as_of: date | None = None,
    ) -> tuple[SafetyAssessment | None, ai_copilot.Explanation | None, str, bool]:
        """Re-run the engine with an amount extracted from a "what if" question.

        The question is only ever used to derive a new INPUT. The engine still
        decides the outcome — the user's phrasing cannot influence the verdict,
        only the amount being tested.
        """
        new_amount, how = ai_copilot.extract_followup_amount(question, str(original_amount))

        if new_amount is None:
            return None, None, how, False

        assessment, explanation, _, is_demo = self.evaluate(
            user=user,
            proposed_amount=Decimal(new_amount),
            counterpart=counterpart,
            as_of=as_of,
            persist=False,
        )
        return assessment, explanation, how, is_demo
