# Deployment

KOPA deploys as **one container**. The same FastAPI process serves the Flutter
web bundle and the API from the same origin, which removes CORS from the
deployment entirely and gives reviewers a single URL.

```
https://<your-app>/              → Flutter app
https://<your-app>/decisions/…   → API
https://<your-app>/docs          → OpenAPI docs
https://<your-app>/health        → liveness + config (no secrets)
```

## What a web deployment can and cannot do

**Can:** the full decision journey — balance, amount entry, safety verdict,
numeric justification, AI explanation, counterpart context, and the PIN gate.

**Cannot: sign.** `bmoni_embedded_sdk` holds the key in the Android Keystore /
iOS Secure Enclave, and a browser has neither. The deployed app states this on
the home screen rather than letting a visitor infer they are looking at a live
wallet. **The Android build is the artefact that demonstrates signing.**

## Deploy to Render

Free tier, no card required. The service sleeps after ~15 minutes idle and
takes ~30s to wake — **open the link once before judging** so a reviewer does
not hit a cold start.

1. Push to GitHub.
2. Render → **New** → **Web Service** → connect the repository.
3. Runtime: **Docker**. Render finds the `Dockerfile` at the repository root;
   leave the build and start commands empty.
4. Instance type: **Free**.
5. Environment variables:

   | Key | Value | Notes |
   |---|---|---|
   | `KOPA_DEMO_MODE` | `true` | No database required |
   | `KOPA_ENV` | `production` | Disables dev CORS origins |
   | `KOPA_AI_PROVIDER` | `groq` | Recommended — free tier, no billing risk |
   | `GROQ_API_KEY` | *(secret)* | From console.groq.com. See below |
   | `ANTHROPIC_API_KEY` | *(secret)* | Alternative to Groq; paid, no free tier |
   | `BMONI_API_KEY` | *(secret)* | Optional in demo mode |

   Without any AI key, KOPA serves its deterministic explanation template —
   the verdict and every figure are identical either way. See
   [responsible-ai.md](responsible-ai.md#choice-of-provider).

   Do not set `PORT`; Render injects it and the container reads it.

6. Deploy. First build takes ~8–12 minutes (it compiles the Flutter bundle).

### Verify

```bash
curl -s https://<your-app>/health
```

Expect `"status":"ok"` and `"demo_mode":true`. The response deliberately
reports whether keys are configured, never the keys themselves.

Then load the root URL and run the demo from
[demo-script.md](demo-script.md).

## Why demo mode for the public deployment

`KOPA_DEMO_MODE=true` means:

- **No database to provision.** Balance, history and obligations come from
  seeded synthetic data.
- **No dependency on BMONI uptime.** A sandbox outage cannot break the link a
  judge clicks.
- The **safety engine and the AI layer still run for real** — only the BMONI
  reads are substituted.

Everything seeded is labelled `DEMO DATA` in the UI, and a demo transfer
carries no BMONI reference and a distinct `DEMO` status.

## Running the deployment locally

Exactly what the container does, without Docker:

```bash
cd kopa_app
flutter build web --release
rm -rf ../kopa_backend/web && cp -r build/web ../kopa_backend/web

cd ../kopa_backend
KOPA_DEMO_MODE=true KOPA_ENV=production \
  ../.venv/Scripts/python.exe -m uvicorn app.main:app --port 8080
```

Open `http://localhost:8080`.

With Docker:

```bash
docker build -t kopa .
docker run --rm -p 8000:8000 -e KOPA_DEMO_MODE=true kopa
```

## Security notes for the deployed build

- The container runs as a **non-root** user (uid 10001).
- `.dockerignore` excludes `.env`, `.git`, the venv and build artefacts, so no
  secret can enter the build context.
- Secrets are environment variables only, never baked into the image. The
  Flutter bundle contains no credentials — it holds only a URL, and on web not
  even that, since it uses the origin serving the page.
- The static handler is **contained to the bundle directory**. Verified against
  raw-socket traversal attempts (`/../.env`, `/%2e%2e/.env`, `/..%2f..%2f.env`,
  `/app/core/config.py`), all of which return `index.html` rather than a file
  from outside the bundle.
- In `KOPA_ENV=production` the dev CORS origins are dropped. Same-origin
  serving means no cross-origin access is needed at all.

### Before this holds anything real

Documented in [security.md](docs/security.md), and restated here because a
public URL invites the question:

- **There is no user authentication.** Demo mode serves seeded data to any user
  id. Correct for a sandbox demonstration; unacceptable for real user data.
- **No rate limiting.**
- The **shared BMONI sandbox key is public** and exposes other participants'
  contact details via `GET /v1/users`. A private key is required before
  production.

Keep this deployment in demo mode. It is a demonstration, not a product
launch.

## Alternatives

| Host | Notes |
|---|---|
| **Fly.io** | `fly launch` reads the Dockerfile. No sleep on the free allowance. |
| **Railway** | Same Dockerfile; requires a card. |
| **Cloud Run** | `gcloud run deploy --source .`; scales to zero. |

Static-only hosts (Netlify, Vercel, GitHub Pages) can serve the Flutter bundle
but not the API, which would mean a second deployment and a CORS
configuration. Avoid — the single-container path exists to prevent that.
