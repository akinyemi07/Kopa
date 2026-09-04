# KOPA — single-container deployment.
#
# One service serves both the Flutter web bundle and the API, from the same
# origin. That removes CORS from the deployment entirely and gives reviewers
# one URL instead of two.
#
# Stage 1 builds the Flutter bundle; stage 2 is a slim Python runtime that
# never sees the Flutter SDK, keeping the shipped image small.

# ---------------------------------------------------------------------------
# Stage 1 — build the Flutter web bundle
# ---------------------------------------------------------------------------
FROM ghcr.io/cirruslabs/flutter:3.47.2 AS web

WORKDIR /build
COPY kopa_app/pubspec.yaml kopa_app/pubspec.lock ./
RUN flutter pub get

COPY kopa_app/ ./
# No --dart-define for the API base URL: on web the app defaults to the origin
# serving the page, which is this same container.
RUN flutter build web --release

# ---------------------------------------------------------------------------
# Stage 2 — runtime
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS runtime

# Do not run as root.
RUN useradd --create-home --uid 10001 kopa

WORKDIR /app

COPY kopa_backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY kopa_backend/app ./app
COPY --from=web /build/build/web ./web

RUN chown -R kopa:kopa /app
USER kopa

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    KOPA_ENV=production \
    KOPA_DEMO_MODE=true

# Render and most PaaS providers inject $PORT. Default to 8000 locally.
ENV PORT=8000
EXPOSE 8000

# Shell form so $PORT expands.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
