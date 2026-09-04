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
#
# The Flutter SDK is cloned directly from the stable channel rather than
# pulled from a third-party prebuilt image. ghcr.io/cirruslabs/flutter — a
# plausible-looking choice — turned out to be four months stale (latest tag
# 3.44.0) with no 3.47.x published at all, so pinning to it here would have
# silently downgraded every deploy. Cloning stable tracks the same channel
# `flutter upgrade` does, which is what a locally verified build already
# depends on.
# ---------------------------------------------------------------------------
FROM debian:bookworm-slim AS web

RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl ca-certificates unzip xz-utils \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --depth 1 -b stable https://github.com/flutter/flutter.git /flutter
ENV PATH="/flutter/bin:${PATH}"

# Pre-cache the tool and pull the web artifacts once, so pub get and the
# build below don't pay for it again.
RUN flutter precache --web

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
