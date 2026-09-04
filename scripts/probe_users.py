"""Read-only probe: what can we see / recover on the shared sandbox key?

Two questions:
  1. Does GET /v1/users list the partner's existing users? If the persona users
     already exist, we may be able to reuse one rather than create it.
  2. Is the persona match name+number only, or does it include the phone? If
     phone is not matched, we can register a fresh phone with the persona's
     name and BVN and still pass verification.
"""

from __future__ import annotations

import json
import os

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
print("PROBE 1 — can we list existing users on this key?")
print("=" * 70)
call("GET", "/v1/users")
call("GET", "/v1/users", params={"limit": 20})
call("GET", "/v1/users", params={"phoneNumber": "+2348000000000"})
call("GET", "/v1/users", params={"search": "Dillon"})

print()
print("=" * 70)
print("PROBE 2 — supported currencies (confirms key reaches the service)")
print("=" * 70)
call("GET", "/v1/smart-wallets/supported-currencies")
