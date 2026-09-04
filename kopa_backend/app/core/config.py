"""Application configuration.

Every secret enters the process here, from the environment, and nowhere else.
No secret is ever returned by an API response, written to a log, or sent to the
Flutter client.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- BMONI ------------------------------------------------------------
    bmoni_base_url: str = Field(
        default="https://embedded-dev.bmoni.com",
        description="Origin only — a trailing /v1 produces /v1/v1/... 404s.",
    )
    bmoni_api_key: str = Field(default="", description="Sent as the x-api-key header.")
    bmoni_currency: str = Field(
        default="CNGN",
        description="Stablecoin code for smart-wallet calls, not the fiat code.",
    )

    # --- AI ---------------------------------------------------------------
    # The explanation layer is provider-pluggable on purpose. It only narrates
    # figures the deterministic engine already computed, so swapping the model
    # cannot change a verdict — which makes the provider a cost/availability
    # decision rather than a correctness one.
    #
    # "auto" picks whichever key is present, preferring Anthropic.
    kopa_ai_provider: Literal["auto", "anthropic", "groq", "none"] = Field(
        default="auto"
    )

    anthropic_api_key: str = Field(default="")
    kopa_ai_model: str = Field(default="claude-sonnet-5")

    #: Groq's free tier. OpenAI-compatible API at api.groq.com/openai/v1.
    groq_api_key: str = Field(default="")
    groq_model: str = Field(default="openai/gpt-oss-120b")
    groq_base_url: str = Field(default="https://api.groq.com/openai/v1")

    # --- database ---------------------------------------------------------
    database_url: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/kopa"
    )

    # --- application ------------------------------------------------------
    kopa_demo_mode: bool = Field(default=False)
    kopa_env: str = Field(default="development")
    kopa_log_level: str = Field(default="INFO")

    @property
    def active_ai_provider(self) -> str:
        """Which provider will actually be used: 'anthropic', 'groq' or 'none'.

        Resolved rather than assumed, so `/health` reports what is really in
        play instead of what was configured in principle.
        """
        if self.kopa_ai_provider == "none":
            return "none"
        if self.kopa_ai_provider == "anthropic":
            return "anthropic" if self.anthropic_api_key.strip() else "none"
        if self.kopa_ai_provider == "groq":
            return "groq" if self.groq_api_key.strip() else "none"
        # auto
        if self.anthropic_api_key.strip():
            return "anthropic"
        if self.groq_api_key.strip():
            return "groq"
        return "none"

    @property
    def active_ai_model(self) -> str | None:
        return {
            "anthropic": self.kopa_ai_model,
            "groq": self.groq_model,
        }.get(self.active_ai_provider)

    @property
    def ai_enabled(self) -> bool:
        """AI is optional by design. Its absence must never disable the verdict."""
        return self.active_ai_provider != "none"

    @property
    def bmoni_configured(self) -> bool:
        return bool(self.bmoni_api_key.strip())

    def safe_summary(self) -> dict[str, object]:
        """A log/health-safe view. Deliberately contains no key material."""
        return {
            "env": self.kopa_env,
            "demo_mode": self.kopa_demo_mode,
            "bmoni_base_url": self.bmoni_base_url,
            "bmoni_currency": self.bmoni_currency,
            "bmoni_configured": self.bmoni_configured,
            "ai_enabled": self.ai_enabled,
            "ai_provider": self.active_ai_provider,
            "ai_model": self.active_ai_model,
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
