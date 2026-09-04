"""KOPA backend.

Financial safety analysis before you sign.

This service is the only component that holds credentials. The Flutter client
talks to this API; this API talks to BMONI and Anthropic. No key ever reaches
the device, and no wallet key ever reaches this server.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.api import decisions, transactions, wallets
from app.core.config import get_settings
from app.db.base import engine
from app.schemas import HealthResponse

settings = get_settings()

logging.basicConfig(
    level=settings.kopa_log_level,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger("kopa")

app = FastAPI(
    title="KOPA API",
    version="0.1.0",
    description=(
        "KOPA helps people understand the financial consequence of a transaction "
        "before they sign it.\n\n"
        "A deterministic safety engine computes every figure and reaches the "
        "verdict. An LLM explains that result in plain language and can never "
        "alter it. If the LLM is unavailable the verdict is still produced."
    ),
)

# The production client is a mobile app, not a browser, so CORS exists only for
# the docs UI and for running the Flutter web build during development.
# Deliberately an explicit allow-list, never a wildcard, and never with
# credentials enabled.
_DEV_ORIGINS = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    # Flutter web dev server — local development only.
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_DEV_ORIGINS if settings.kopa_env == "development" else [],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

app.include_router(decisions.router)
app.include_router(wallets.router)
app.include_router(transactions.router)


@app.get("/health", response_model=HealthResponse, tags=["meta"])
def health() -> HealthResponse:
    """Liveness plus a secret-free view of how the service is configured."""
    db_status = "unavailable"
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception as exc:  # noqa: BLE001
        logger.warning("database health check failed: %s", exc)

    return HealthResponse(
        status="ok",
        database=db_status,
        config=settings.safe_summary(),
    )


# ---------------------------------------------------------------------------
# Flutter web bundle
#
# When a build is present, the same process that serves the API also serves the
# app. Same-origin means there is no CORS configuration to get wrong in
# production, and judges get one URL rather than two.
#
# This is mounted AFTER every router, so it can never shadow an API route.
# ---------------------------------------------------------------------------

_WEB_DIR = Path(__file__).resolve().parent.parent / "web"

if _WEB_DIR.is_dir():
    app.mount(
        "/assets", StaticFiles(directory=_WEB_DIR / "assets"), name="assets"
    )
    if (_WEB_DIR / "canvaskit").is_dir():
        app.mount(
            "/canvaskit",
            StaticFiles(directory=_WEB_DIR / "canvaskit"),
            name="canvaskit",
        )

    @app.get("/{path:path}", include_in_schema=False)
    def serve_app(path: str) -> FileResponse:
        """Serve the Flutter bundle, falling back to index.html for routes.

        A single-page app owns its own routing, so any path that is not a real
        file must return index.html rather than a 404 — otherwise a refresh on
        a deep link breaks.
        """
        candidate = (_WEB_DIR / path).resolve()
        # Contain the lookup to the bundle: a crafted path must not be able to
        # read files elsewhere on disk.
        if (
            path
            and _WEB_DIR in candidate.parents
            and candidate.is_file()
        ):
            return FileResponse(candidate)
        return FileResponse(_WEB_DIR / "index.html")


@app.on_event("startup")
def on_startup() -> None:
    logger.info("KOPA starting: %s", settings.safe_summary())
    if settings.kopa_demo_mode:
        logger.warning(
            "DEMO MODE is ON — balance and history come from seeded data. "
            "The safety engine and AI narration still run for real."
        )
    if not settings.ai_enabled:
        logger.warning(
            "ANTHROPIC_API_KEY not set — explanations will use the deterministic "
            "fallback. Safety verdicts are unaffected."
        )
