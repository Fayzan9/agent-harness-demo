"""All configuration in one place: read from the environment, checked once, at startup.

Locally the values come from backend/.env. On a server they come from real environment variables
(on AWS, injected from Secrets Manager). The code never knows which.
"""
from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # hide_input_in_errors: a validation error must never echo the values it was given (they may be secrets).
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    # Where this copy of the app runs. Later steps turn protections on when this is not "local".
    environment: Literal["local", "staging", "production"] = "local"

    # Azure OpenAI. Required: the app refuses to start without them.
    openai_api_base: str
    openai_api_key: SecretStr  # SecretStr prints as ********, so a stray log line cannot leak it
    model: str  # Azure deployment name
    openai_api_version: str = "2025-04-01-preview"

    # Browser origins allowed to call the API. A JSON list in the env var: CORS_ORIGINS='["https://app.example.com"]'
    cors_origins: list[str] = ["http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    """Built once, then reused. The first call is at startup, so a bad config stops the app right there."""
    return Settings()
