"""All configuration in one place: read from the environment, checked once, at startup.

Locally the values come from backend/.env. On a server they come from real environment variables
(on AWS, injected from Secrets Manager). The code never knows which.
"""
from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # hide_input_in_errors: a validation error must never echo the values it was given (they may be secrets).
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True, populate_by_name=True)

    # Where this copy of the app runs. Later steps turn protections on when this is not "local".
    environment: Literal["local", "staging", "production"] = "local"

    # The model provider, through LiteLLM. The app refuses to start without a key and a model.
    # LLM_PROVIDER: azure | openai | gemini | anthropic. Left empty, it is "azure" when an API base is set and "openai" otherwise,
    # so an older .env that only has the three Azure values keeps working.
    # The OPENAI_* names are the older spelling of LLM_API_KEY and LLM_API_BASE and are still accepted.
    llm_provider: Literal["", "azure", "openai", "gemini", "anthropic"] = ""
    openai_api_key: SecretStr = Field(validation_alias=AliasChoices("LLM_API_KEY", "OPENAI_API_KEY"))  # SecretStr prints as ********, so a stray log line cannot leak it
    openai_api_base: str = Field("", validation_alias=AliasChoices("LLM_API_BASE", "OPENAI_API_BASE"))  # Azure: required. Others: only for a proxy or a local server
    model: str  # Azure: the deployment name. Others: the model name, e.g. gpt-4o-mini. A full LiteLLM id such as gemini/gemini-2.0-flash also works
    openai_api_version: str = "2025-04-01-preview"  # Azure only

    # Browser origins allowed to call the API. A JSON list in the env var: CORS_ORIGINS='["https://app.example.com"]'
    cors_origins: list[str] = ["http://localhost:3000"]

    # Where chats and runs are kept. The default is a local SQLite file so the demo needs nothing installed.
    # Staging and production must use Postgres. The url holds a password, so it is a SecretStr.
    # Example: postgresql+psycopg://user:password@host:5432/dbname
    database_url: SecretStr = SecretStr("sqlite:///data/harness.db")

    # Login. "off" = everyone is one local user (demo on a laptop). "jwt" = callers must send a signed token.
    # Defaults describe Google sign-in; Cognito, Okta etc. only need different values here.
    auth_mode: Literal["off", "jwt"] = "off"
    auth_audience: str = ""  # who the token is for: the Google OAuth client id (not a secret)
    auth_issuers: list[str] = ["https://accounts.google.com", "accounts.google.com"]
    auth_jwks_url: str = "https://www.googleapis.com/oauth2/v3/certs"  # where the provider publishes its public keys
    # Who may use the app, as exact emails or "@domain". Signing in with Google proves WHO you are, not that you are allowed.
    allowed_emails: list[str] = []

    @model_validator(mode="after")
    def _pick_provider(self):
        if not self.llm_provider:
            self.llm_provider = "azure" if self.openai_api_base else "openai"
        if self.llm_provider == "azure" and not self.openai_api_base:
            raise ValueError("LLM_PROVIDER=azure needs LLM_API_BASE (your Azure endpoint)")
        return self

    @model_validator(mode="after")
    def _safe_for_where_it_runs(self):
        if self.environment != "local" and self.auth_mode == "off":
            raise ValueError("AUTH_MODE=off is only allowed when ENVIRONMENT=local")
        if self.environment != "local" and not self.database_url.get_secret_value().startswith("postgresql"):
            raise ValueError("DATABASE_URL must be a Postgres url unless ENVIRONMENT=local")
        if self.auth_mode == "jwt" and not (self.auth_audience and self.allowed_emails):
            raise ValueError("AUTH_MODE=jwt needs AUTH_AUDIENCE and a non-empty ALLOWED_EMAILS (an empty list would let nobody in)")
        return self


@lru_cache
def get_settings() -> Settings:
    """Built once, then reused. The first call is at startup, so a bad config stops the app right there."""
    return Settings()
