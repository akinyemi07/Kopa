"""Map the `address` sub-shape, then attempt the Nigeria rail."""

from __future__ import annotations

import json
import os
from pathlib import Path

import httpx

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

STATE = Path(__file__).resolve().parent.parent / ".spike_state.json"
state = json.loads(STATE.read_text())
UID = state["bmoniUserId"]
persona = state["persona"]

client = httpx.Client(
    base_url=BASE_URL,
    headers={"x-api-key": API_KEY, "Content-Type": "application/json"},
    timeout=60.0,
)


def call(method: str, path: str, **kw):
    r = client.request(method, path, **kw)
    try:
        body = r.json()
    except Exception:
        body = r.text
    print(f"\n>>> {method} {path} -> {r.status_code}")
    s = json.dumps(body, indent=2) if not isinstance(body, str) else body
    print(s[:2500])
    return r.status_code, body


print("=" * 70)
print("Map the address sub-shape with candidate keys")
print("=" * 70)
call("PATCH", f"/v1/users/{UID}/kyc", json={
    "address": {
        "street": "15 Admiralty Way",
        "streetLine1": "15 Admiralty Way",
        "line1": "15 Admiralty Way",
        "address": "15 Admiralty Way",
        "city": "Lagos",
        "state": "Lagos",
        "subdivisionName": "Lagos",
        "postalCode": "101233",
        "countryCode": "NGA",
        "country": "NGA",
    }
})

print("\n" + "=" * 70)
print("BVN lookup (fetch-only, cheapest confirmation the key reaches identity)")
print("=" * 70)
call("GET", f"/v1/users/{UID}/kyc/bvn-lookup/{persona['bvn']}")

print("\n" + "=" * 70)
print("identificationNumbers with the persona BVN")
print("=" * 70)
call("PATCH", f"/v1/users/{UID}/kyc", json={
    "identificationNumbers": {
        "type": "bvn",
        "number": persona["bvn"],
        "issuingCountryCode": "NGA",
    }
})

print("\n" + "=" * 70)
print("Readiness after profile writes")
print("=" * 70)
call("GET", f"/v1/users/{UID}/kyc/readiness")

print("\n" + "=" * 70)
print("Onboarding status before the rail")
print("=" * 70)
call("GET", f"/v1/users/{UID}/onboarding/status")

print("\n" + "=" * 70)
print("Start the Nigeria rail")
print("=" * 70)
call("POST", f"/v1/users/{UID}/onboarding/start-nigeria", json={
    "bvn": persona["bvn"],
    "ngnWalletAddress": state["ownerAddress"],
    "ngnWalletIndex": 0,
})

print("\n" + "=" * 70)
print("Onboarding status after the rail")
print("=" * 70)
call("GET", f"/v1/users/{UID}/onboarding/status")

print("\n" + "=" * 70)
print("Wallets and balances")
print("=" * 70)
call("GET", f"/v1/users/{UID}/smart-wallets/account/wallets")
call("GET", f"/v1/users/{UID}/smart-wallets/account/balances")
