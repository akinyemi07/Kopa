"""
M0a — BMONI sandbox chain spike.

Proves the documented lifecycle end to end, server-side, before any Flutter
code exists:

    user -> owner-proof challenge -> smart wallet -> KYC -> Nigeria rail -> balances

The on-device signature is stood in for here with a local eth-account keypair.
That keypair is a THROWAWAY spike artefact. In the real app this exact role is
played by bmoni_embedded_sdk inside Android Keystore, and the private key never
exists on a server. Nothing in kopa_backend/ will ever hold a wallet key.

Resumable: every completed step is checkpointed to .spike_state.json so a
failure (or a 409 on a shared sandbox persona) does not cost earlier progress.

Usage:
    ./.venv/Scripts/python.exe scripts/bmoni_spike.py [--persona bunch|samson]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx
from eth_account import Account
from eth_account.messages import encode_defunct

# Base URL is origin-only. A trailing /v1 produces /v1/v1/... 404s.
BASE_URL = os.environ.get("BMONI_BASE_URL", "https://embedded-dev.bmoni.com")

# Never hardcoded. Export BMONI_API_KEY before running; BMONI publishes a
# shared sandbox key in their public quickstart if you need one.
API_KEY = os.environ.get("BMONI_API_KEY", "")
if not API_KEY:
    raise SystemExit(
        "BMONI_API_KEY is not set. Export it first: "
        "export BMONI_API_KEY=<your sandbox key>. "
        "BMONI publishes a shared sandbox key at "
        "https://bkey.mintlify.app/api-quickstart"
    )

# Smart-wallet calls take the stablecoin code, not the fiat one.
CURRENCY = "CNGN"

STATE_PATH = Path(__file__).resolve().parent.parent / ".spike_state.json"

# Only these personas resolve in the sandbox. Submitting any other NAME or BVN
# simulates a failed identity match — which is correct behaviour, not a bug.
# See /api-reference/sandbox-test-data.
#
# The persona's own phone number is already registered on this shared key, and
# POST /v1/users rejects a duplicate phone with a 409. Verification matches on
# name + identity number, not phone, so we register a unique phone against the
# persona's name and BVN. Confirmed against the partner's existing users, which
# show the same persona name registered under several different numbers.
PERSONAS = {
    "bunch": {
        "firstName": "Bunch",
        "lastName": "Dillon",
        "bvn": "95888168924",
        "nin": "63184876213",
        "dateOfBirth": "1990-01-15",
        "gender": "male",
    },
    "samson": {
        "firstName": "Samson",
        "lastName": "Jabo",
        "bvn": "22222222222",
        "dateOfBirth": "1990-01-15",
        "gender": "male",
    },
}


def with_unique_contact(persona: dict) -> dict:
    """Give the persona a fresh phone/email so POST /v1/users does not 409.

    Nigerian mobile numbers are +234 followed by 10 digits. We derive both from
    a timestamp so reruns never collide, and persist them in the checkpoint —
    the phone is what BMONI needs in order to credit test tokens.
    """
    suffix = str(int(time.time()))[-8:]
    p = dict(persona)
    p["phoneNumber"] = f"+23480{suffix}"
    p["email"] = f"kopa.{persona['firstName'].lower()}.{suffix}@example.com"
    return p


# --------------------------------------------------------------------------
# state
# --------------------------------------------------------------------------

def load_state() -> dict[str, Any]:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    return {}


def save_state(state: dict[str, Any]) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2))


# --------------------------------------------------------------------------
# http
# --------------------------------------------------------------------------

client = httpx.Client(
    base_url=BASE_URL,
    headers={"x-api-key": API_KEY, "Content-Type": "application/json"},
    timeout=60.0,
)


def call(method: str, path: str, **kw) -> tuple[int, Any]:
    """One request, fully logged. Returns (status, parsed-body-or-text)."""
    print(f"\n>>> {method} {path}")
    if "json" in kw:
        print(f"    body: {json.dumps(kw['json'])[:600]}")
    r = client.request(method, path, **kw)
    try:
        body: Any = r.json()
    except Exception:
        body = r.text
    print(f"<<< {r.status_code}")
    print(f"    {json.dumps(body, indent=2)[:1800] if not isinstance(body, str) else body[:1800]}")
    return r.status_code, body


def unwrap(body: Any) -> Any:
    """BMONI wraps most successful payloads in {"data": ...}."""
    if isinstance(body, dict) and "data" in body:
        return body["data"]
    return body


def dig(obj: Any, *keys: str) -> Any:
    """First non-null value for any of `keys`, searched shallowly then one level down."""
    if not isinstance(obj, dict):
        return None
    for k in keys:
        if obj.get(k) is not None:
            return obj[k]
    for v in obj.values():
        if isinstance(v, dict):
            for k in keys:
                if v.get(k) is not None:
                    return v[k]
    return None


# --------------------------------------------------------------------------
# steps
# --------------------------------------------------------------------------

def step_owner_key(state: dict) -> None:
    """Stand-in for bmoni_embedded_sdk.initWallet(). Throwaway spike key."""
    if state.get("ownerAddress"):
        print(f"\n[skip] owner key exists: {state['ownerAddress']}")
        return
    acct = Account.create()
    state["ownerAddress"] = acct.address
    state["ownerPrivateKey"] = acct.key.hex()
    save_state(state)
    print(f"\n[ok] spike owner key generated: {acct.address}")


def step_create_user(state: dict, persona: dict) -> bool:
    if state.get("bmoniUserId"):
        print(f"\n[skip] user exists: {state['bmoniUserId']}")
        return True

    status, body = call("POST", "/v1/users", json={
        "firstName": persona["firstName"],
        "lastName": persona["lastName"],
        "email": persona["email"],
        "phoneNumber": persona["phoneNumber"],
    })

    if status == 409:
        print("\n[BLOCKED] 409 — this persona's email or phone is already registered.")
        print("          The sandbox key is public, so another integrator likely holds it.")
        print("          Try: --persona samson, or ask developers@bkey.me for a private key.")
        return False

    if status not in (200, 201):
        print(f"\n[FAIL] user creation returned {status}")
        return False

    data = unwrap(body)
    user_id = dig(data, "bmoniUserId", "id", "userId")
    if not user_id:
        print("\n[FAIL] no user id in response — inspect the body above.")
        return False

    state["bmoniUserId"] = user_id
    save_state(state)
    print(f"\n[ok] bmoniUserId = {user_id}")
    return True


def step_smart_wallet(state: dict) -> bool:
    if state.get("smartWalletId"):
        print(f"\n[skip] smart wallet exists: {state['smartWalletId']}")
        return True

    uid = state["bmoniUserId"]
    owner = state["ownerAddress"]

    status, body = call(
        "POST", f"/v1/users/{uid}/smart-wallets/owner-proof-challenges",
        json={"currency": CURRENCY, "userOwnerAddress": owner},
    )
    if status not in (200, 201):
        print(f"\n[FAIL] owner-proof challenge returned {status}")
        return False

    data = unwrap(body)
    challenge_id = dig(data, "challengeId", "id")
    message = dig(data, "message", "eip191Message")
    if not challenge_id or not message:
        print("\n[FAIL] challenge response missing challengeId/message.")
        return False

    # Owner proof signs the challenge TEXT with the EIP-191 prefix.
    # This is bmoni_embedded_sdk.signMessage() on-device.
    signed = Account.sign_message(
        encode_defunct(text=message),
        state["ownerPrivateKey"],
    )
    signature = "0x" + signed.signature.hex().removeprefix("0x")
    print(f"\n[ok] EIP-191 owner-proof signature: {signature[:24]}... ({len(signature)} chars)")

    status, body = call(
        "POST", f"/v1/users/{uid}/smart-wallets/create-managed",
        json={
            "currency": CURRENCY,
            "userOwnerAddress": owner,
            "ownerProofChallengeId": challenge_id,
            "ownerProofSignature": signature,
        },
    )
    if status not in (200, 201):
        print(f"\n[FAIL] create-managed returned {status}")
        return False

    data = unwrap(body)
    wallet_id = dig(data, "smartWalletId", "id")
    wallet_addr = dig(data, "address", "smartWalletAddress", "walletAddress")
    if not wallet_id:
        print("\n[FAIL] no smartWalletId in response.")
        return False

    state["smartWalletId"] = wallet_id
    state["smartWalletAddress"] = wallet_addr
    save_state(state)
    print(f"\n[ok] smartWalletId = {wallet_id}  address = {wallet_addr}")
    return True


def step_kyc_profile(state: dict, persona: dict) -> bool:
    if state.get("kycPatched"):
        print("\n[skip] KYC profile already submitted")
        return True

    uid = state["bmoniUserId"]
    status, _ = call("PATCH", f"/v1/users/{uid}/kyc", json={
        "personalInfo": {
            "firstName": persona["firstName"],
            "lastName": persona["lastName"],
            "dateOfBirth": persona["dateOfBirth"],
            "gender": persona["gender"],
            "phoneNumber": persona["phoneNumber"],
        },
        "addressDetails": {
            "streetLine1": "15 Admiralty Way",
            "street": "15 Admiralty Way",
            "city": "Lagos",
            "state": "Lagos",
            "postalCode": "101233",
            "countryCode": "NGA",
        },
    })
    if status not in (200, 201, 204):
        print(f"\n[FAIL] PATCH /kyc returned {status}")
        return False

    state["kycPatched"] = True
    save_state(state)
    print("\n[ok] KYC profile submitted")
    return True


def step_start_nigeria(state: dict, persona: dict) -> bool:
    if state.get("nigeriaStarted"):
        print("\n[skip] Nigeria rail already started")
        return True

    uid = state["bmoniUserId"]
    status, body = call(
        "POST", f"/v1/users/{uid}/onboarding/start-nigeria",
        json={
            "bvn": persona["bvn"],
            "ngnWalletAddress": state["ownerAddress"],
            "ngnWalletIndex": 0,
        },
    )
    if status not in (200, 201, 202):
        print(f"\n[FAIL] start-nigeria returned {status}")
        return False

    state["nigeriaStarted"] = True
    save_state(state)
    print("\n[ok] Nigeria rail onboarding started")
    return True


def step_status_and_balances(state: dict) -> None:
    uid = state["bmoniUserId"]

    for attempt in range(3):
        status, body = call("GET", f"/v1/users/{uid}/onboarding/status")
        text = json.dumps(body) if not isinstance(body, str) else body
        if '"active"' in text.lower() or "active" in text.lower():
            break
        if attempt < 2:
            print("    ...not active yet, waiting 5s")
            time.sleep(5)

    call("GET", f"/v1/users/{uid}/smart-wallets/account/wallets")
    call("GET", f"/v1/users/{uid}/smart-wallets/account/balances")


# --------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--persona", choices=["bunch", "samson"], default="bunch")
    ap.add_argument("--reset", action="store_true", help="discard checkpoint and start over")
    args = ap.parse_args()

    if args.reset and STATE_PATH.exists():
        STATE_PATH.unlink()
        print("[reset] checkpoint discarded")

    state = load_state()

    # Reuse the contact details from a previous run so a resumed spike stays
    # on the same BMONI user — a fresh phone would fork the wallet history.
    if state.get("persona"):
        persona = state["persona"]
    else:
        persona = with_unique_contact(PERSONAS[args.persona])
        state["persona"] = persona
        save_state(state)

    print("=" * 70)
    print(f"KOPA — BMONI sandbox spike")
    print(f"base    : {BASE_URL}")
    print(f"key     : {API_KEY[:16]}... (sandbox)")
    print(f"persona : {persona['firstName']} {persona['lastName']}  {persona['phoneNumber']}")
    print(f"currency: {CURRENCY}")
    print("=" * 70)

    step_owner_key(state)

    if not step_create_user(state, persona):
        return 1
    if not step_smart_wallet(state):
        return 1
    if not step_kyc_profile(state, persona):
        return 1
    if not step_start_nigeria(state, persona):
        return 1

    step_status_and_balances(state)

    print("\n" + "=" * 70)
    print("SPIKE SUMMARY")
    print(f"  bmoniUserId        : {state.get('bmoniUserId')}")
    print(f"  owner address      : {state.get('ownerAddress')}")
    print(f"  smartWalletId      : {state.get('smartWalletId')}")
    print(f"  smart wallet addr  : {state.get('smartWalletAddress')}")
    print(f"  funding phone      : {persona['phoneNumber']}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
