"""Discover the real PATCH /kyc body shape.

The published quickstart uses `addressDetails`, which the live API rejects with
`property addressDetails should not exist`. That is NestJS whitelist validation,
so it names any property we send that is not allowed — we can use it to map the
accepted surface by probing candidate names.
"""

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

state = json.loads((Path(__file__).resolve().parent.parent / ".spike_state.json").read_text())
UID = state["bmoniUserId"]

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
    print(s[:3000])
    return r.status_code, body


print("=" * 70)
print("Current KYC record")
print("=" * 70)
call("GET", f"/v1/users/{UID}/kyc")

print("\n" + "=" * 70)
print("KYC options (documented field option lists)")
print("=" * 70)
call("GET", f"/v1/users/{UID}/kyc/options")

print("\n" + "=" * 70)
print("Readiness — usually names what is still missing")
print("=" * 70)
call("GET", f"/v1/users/{UID}/kyc/readiness")

print("\n" + "=" * 70)
print("Whitelist probe — every candidate name at once")
print("=" * 70)
candidates = {
    "personalInfo": {},
    "addressDetails": {},
    "address": {},
    "addressInfo": {},
    "residentialAddress": {},
    "employment": {},
    "employmentInfo": {},
    "compliance": {},
    "financialInfo": {},
    "identificationNumbers": {},
    "identityNumbers": {},
    "sourceOfFunds": "salary",
}
call("PATCH", f"/v1/users/{UID}/kyc", json=candidates)

print("\n" + "=" * 70)
print("Empty body — does it accept a no-op?")
print("=" * 70)
call("PATCH", f"/v1/users/{UID}/kyc", json={})

print("\n" + "=" * 70)
print("personalInfo only, with a junk inner key to map the nested shape")
print("=" * 70)
call("PATCH", f"/v1/users/{UID}/kyc", json={
    "personalInfo": {"firstName": "Bunch", "lastName": "Dillon", "zzzJunk": 1}
})
