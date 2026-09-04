"""Server-side BMONI Embedded API client.

This module is the ONLY place in KOPA that holds the BMONI partner key. The
Flutter app never sees it, never sends it, and cannot: every BMONI call the app
needs is proxied through kopa_backend.

The split of responsibilities:

    device  (bmoni_embedded_sdk)  -> keygen, PIN, signMessage, signTransactionHash
    backend (this module)         -> everything else, authenticated with x-api-key

The device produces an address and two signatures. The private key never leaves
the device's secure element and never exists on a server.

Every method here corresponds to a call verified against the live sandbox during
the M0a spike. Where the published documentation and the live API disagree, the
live behaviour wins and the divergence is noted inline.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

# Keys whose values must never reach a log line.
_REDACT = {"x-api-key", "signature", "ownerProofSignature", "photo", "bvn", "nin"}


class BmoniError(RuntimeError):
    """A BMONI call failed.

    `message` is safe to surface to a user after mapping; `detail` is for logs.
    """

    def __init__(self, message: str, *, status: int | None = None, detail: Any = None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.detail = detail


@dataclass(frozen=True)
class SmartWallet:
    smart_wallet_id: str
    address: str
    currency: str
    is_active: bool
    raw: dict[str, Any]


@dataclass(frozen=True)
class OwnerProofChallenge:
    challenge_id: str
    message: str
    expires_at: str | None


@dataclass(frozen=True)
class WalletBalance:
    smart_wallet_id: str | None
    currency: str
    balance: str
    error: str | None = None


def _redact(payload: Any) -> Any:
    """Strip secrets and bulky blobs before anything is logged."""
    if isinstance(payload, dict):
        return {
            k: ("<redacted>" if k in _REDACT else _redact(v))
            for k, v in payload.items()
        }
    if isinstance(payload, list):
        return [_redact(v) for v in payload]
    if isinstance(payload, str) and len(payload) > 300:
        return f"<{len(payload)} chars>"
    return payload


class BmoniClient:
    """Thin, typed wrapper over the BMONI Embedded REST API."""

    def __init__(self, settings: Settings | None = None, client: httpx.Client | None = None):
        self.settings = settings or get_settings()
        if not self.settings.bmoni_configured:
            raise BmoniError("BMONI_API_KEY is not configured")

        self._client = client or httpx.Client(
            # Origin only. A trailing /v1 here yields /v1/v1/... 404s.
            base_url=self.settings.bmoni_base_url.rstrip("/"),
            headers={
                "x-api-key": self.settings.bmoni_api_key,
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(60.0, connect=15.0),
        )

    def close(self) -> None:
        self._client.close()

    # ----------------------------------------------------------------- http

    def _request(self, method: str, path: str, **kw: Any) -> Any:
        try:
            response = self._client.request(method, path, **kw)
        except httpx.HTTPError as exc:
            logger.warning("bmoni transport error: %s %s (%s)", method, path, exc)
            raise BmoniError(
                "Could not reach BMONI. Check your connection and try again.",
                detail=str(exc),
            ) from exc

        try:
            body: Any = response.json()
        except ValueError:
            body = response.text

        logger.info(
            "bmoni %s %s -> %s %s",
            method,
            path,
            response.status_code,
            _redact(body) if response.status_code >= 400 else "",
        )

        if response.status_code >= 400:
            raise BmoniError(
                _friendly_message(response.status_code, body),
                status=response.status_code,
                detail=_redact(body),
            )
        return body

    # ----------------------------------------------------------- lifecycle 1

    def create_user(
        self,
        *,
        first_name: str,
        last_name: str,
        email: str,
        phone_number: str,
    ) -> dict[str, Any]:
        """Stage 1 — register the person and get a bmoniUserId.

        A 409 means the email or phone is already registered. That is the
        correct answer to a retry of a create that already succeeded; the caller
        should recover the existing user rather than retry with new details.
        """
        body = self._request(
            "POST",
            "/v1/users",
            json={
                "firstName": first_name,
                "lastName": last_name,
                "email": email,
                "phoneNumber": phone_number,
            },
        )
        # Live API wraps this as {"user": {...}} rather than the documented {"data": ...}.
        user = body.get("user") if isinstance(body, dict) else None
        if not user or not user.get("bmoniUserId"):
            raise BmoniError("BMONI did not return a user id", detail=_redact(body))
        return user

    # ----------------------------------------------------------- lifecycle 2

    def create_owner_proof_challenge(
        self, user_id: str, owner_address: str, currency: str | None = None
    ) -> OwnerProofChallenge:
        """Ask BMONI for the message the device must sign to prove key ownership.

        The challenge expires after 10 minutes and is consumed on successful
        wallet creation — request a fresh one on any retry.
        """
        body = self._request(
            "POST",
            f"/v1/users/{user_id}/smart-wallets/owner-proof-challenges",
            json={
                "currency": currency or self.settings.bmoni_currency,
                "userOwnerAddress": owner_address,
            },
        )
        return OwnerProofChallenge(
            challenge_id=body["challengeId"],
            message=body["message"],
            expires_at=body.get("expiresAt"),
        )

    def create_smart_wallet(
        self,
        user_id: str,
        *,
        owner_address: str,
        challenge_id: str,
        owner_proof_signature: str,
        currency: str | None = None,
    ) -> SmartWallet:
        """Deploy the smart wallet against the device-held owner key.

        `owner_proof_signature` must be an EIP-191 (prefixed) signature over the
        challenge message — `BmoniEmbeddedSdk.signMessage` on device. This is
        NOT the same method used to sign a proposal later.
        """
        body = self._request(
            "POST",
            f"/v1/users/{user_id}/smart-wallets/create-managed",
            json={
                "currency": currency or self.settings.bmoni_currency,
                "userOwnerAddress": owner_address,
                "ownerProofChallengeId": challenge_id,
                "ownerProofSignature": owner_proof_signature,
            },
        )
        return SmartWallet(
            smart_wallet_id=body["id"],
            address=body["walletAddress"],
            currency=body.get("currency", "NGN"),
            is_active=bool(body.get("isActive")),
            raw=body,
        )

    # ----------------------------------------------------------- lifecycle 3

    def bvn_lookup(self, user_id: str, bvn: str) -> dict[str, Any]:
        """Fetch-only identity preview. Writes nothing to the KYC profile.

        Useful as the cheapest confirmation that the key reaches the identity
        service at all: if this returns a record but activation later fails, the
        plumbing is fine and the profile details do not match the persona.
        """
        return self._request("GET", f"/v1/users/{user_id}/kyc/bvn-lookup/{bvn}")

    def get_kyc(self, user_id: str) -> dict[str, Any]:
        return self._request("GET", f"/v1/users/{user_id}/kyc")

    def get_kyc_readiness(self, user_id: str) -> dict[str, Any]:
        return self._request("GET", f"/v1/users/{user_id}/kyc/readiness")

    def patch_kyc(self, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Submit KYC profile data.

        NOTE — the published quickstart shows `addressDetails`, which the live
        API rejects with `property addressDetails should not exist`. The accepted
        top-level properties, mapped against the live validator, are:

            personalInfo, address, employment, sourceOfFunds, identificationNumbers

        and `identificationNumbers` must be an ARRAY, not an object. Verified
        against the sandbox on 2026-09-04. See docs/bmoni-integration.md.
        """
        return self._request("PATCH", f"/v1/users/{user_id}/kyc", json=payload)

    # ----------------------------------------------------------- lifecycle 4

    def start_nigeria(
        self, user_id: str, *, bvn: str, wallet_address: str, wallet_index: int = 0
    ) -> dict[str, Any]:
        """Activate the NGN rail. Requires the wallet to exist first."""
        return self._request(
            "POST",
            f"/v1/users/{user_id}/onboarding/start-nigeria",
            json={
                "bvn": bvn,
                "ngnWalletAddress": wallet_address,
                "ngnWalletIndex": wallet_index,
            },
        )

    def get_onboarding_status(self, user_id: str) -> dict[str, Any]:
        return self._request("GET", f"/v1/users/{user_id}/onboarding/status")

    # ----------------------------------------------------------- lifecycle 5

    def list_wallets(self, user_id: str) -> list[dict[str, Any]]:
        body = self._request("GET", f"/v1/users/{user_id}/smart-wallets/account/wallets")
        return body if isinstance(body, list) else body.get("wallets", [])

    def get_balances(self, user_id: str) -> list[WalletBalance]:
        """Live balances. This is the figure the safety engine evaluates against."""
        body = self._request("GET", f"/v1/users/{user_id}/smart-wallets/account/balances")
        return [
            WalletBalance(
                smart_wallet_id=b.get("smartWalletId"),
                currency=b.get("currency", "NGN"),
                balance=str(b.get("balance", "0")),
                error=b.get("error"),
            )
            for b in (body.get("balances") or [])
        ]

    # ----------------------------------------------------------- lifecycle 6

    def create_transfer_proposal(
        self,
        user_id: str,
        smart_wallet_id: str,
        *,
        amount: str,
        to_address: str | None = None,
        to_user_id: str | None = None,
        description: str | None = None,
        currency: str | None = None,
    ) -> dict[str, Any]:
        """Record the intent to transfer. Nothing moves on this call.

        Exactly one of `to_address` / `to_user_id` is required. `to_user_id`
        requires the recipient to already hold an active wallet in this
        currency, which a fresh sandbox user usually does not — `to_address` is
        the reliable choice.
        """
        if not (to_address or to_user_id):
            raise BmoniError("A transfer needs either a recipient address or user id")

        proposal: dict[str, Any] = {
            "type": "TRANSFER",
            "amount": amount,
            "currency": currency or self.settings.bmoni_currency,
        }
        if to_address:
            proposal["toAddress"] = to_address
        else:
            proposal["toUserId"] = to_user_id
        if description:
            proposal["description"] = description[:500]

        return self._request(
            "POST",
            f"/v1/users/{user_id}/smart-wallets/{smart_wallet_id}/proposals",
            json={"proposal": proposal},
        )

    def approve_proposal(self, user_id: str, proposal_id: str) -> dict[str, Any]:
        """Record the approval vote. Moves status to PENDING_SIGNATURES."""
        return self._request(
            "POST",
            f"/v1/users/{user_id}/smart-wallets/proposals/{proposal_id}/approve",
        )

    def get_sign_payload(self, user_id: str, proposal_id: str) -> dict[str, Any]:
        """Fetch `hashToSign` — the raw 32-byte digest the device must sign.

        Only available once the proposal reaches PENDING_SIGNATURES, so a 404
        here usually means the approval threshold has not been met yet rather
        than that the proposal is missing.
        """
        return self._request(
            "GET",
            f"/v1/users/{user_id}/smart-wallets/proposals/{proposal_id}/sign-payload",
        )

    def submit_signature(
        self, user_id: str, proposal_id: str, signature: str
    ) -> dict[str, Any]:
        """Submit the device signature over `hashToSign`.

        This signature comes from `BmoniEmbeddedSdk.signTransactionHash` — a RAW
        digest signature with NO EIP-191 prefix. Using the message-signing method
        here produces a signature that recovers to a different address and is
        rejected, with an error that does not say why.
        """
        return self._request(
            "POST",
            f"/v1/users/{user_id}/smart-wallets/proposals/{proposal_id}/sign",
            json={"signature": signature},
        )

    def get_proposal(self, user_id: str, proposal_id: str) -> dict[str, Any]:
        """Poll for the terminal status: PENDING_APPROVALS -> PENDING_SIGNATURES -> COMPLETED."""
        return self._request(
            "GET", f"/v1/users/{user_id}/smart-wallets/proposals/{proposal_id}"
        )


def _friendly_message(status: int, body: Any) -> str:
    """Translate a BMONI failure into something a user can act on.

    The technical detail stays in the logs; the user gets a sentence.
    """
    raw = ""
    if isinstance(body, dict):
        message = body.get("message")
        raw = " ".join(message) if isinstance(message, list) else str(message or "")

    if status == 401 or status == 403:
        return "KOPA could not authenticate with BMONI. Please contact support."
    if status == 404:
        return "That record could not be found on BMONI."
    if status == 409:
        return "An account already exists with those details."
    if status == 400 and "recipient does not have an active" in raw.lower():
        return "That recipient cannot receive this currency yet."
    if status == 400:
        return f"BMONI rejected the request: {raw}" if raw else "BMONI rejected the request."
    if status >= 500:
        return "BMONI is temporarily unavailable. Please try again shortly."
    return "Something went wrong talking to BMONI."
