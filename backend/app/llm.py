import litellm

from .settings import get_settings

# Failures worth retrying: the request may well succeed a moment later.
TRANSIENT = (
    litellm.RateLimitError,
    litellm.APIConnectionError,
    litellm.Timeout,
    litellm.InternalServerError,
    litellm.ServiceUnavailableError,
)

REQUEST_TIMEOUT = 60  # seconds to wait for one model call


def default_model() -> str:
    """Azure deployment name from settings."""
    return get_settings().model


async def complete(deployment: str, messages: list[dict], tools: list[dict] | None):
    """One model call through LiteLLM, pointed at an Azure OpenAI deployment."""
    s = get_settings()
    return await litellm.acompletion(
        model=f"azure/{deployment}",
        api_base=s.openai_api_base,
        api_key=s.openai_api_key.get_secret_value(),  # the one place the secret is unwrapped
        api_version=s.openai_api_version,
        messages=messages,
        tools=tools,
        timeout=REQUEST_TIMEOUT,
    )


def usage_of(resp) -> dict:
    """Token counts the provider reports for one call. Cached is how many came from its prompt cache."""
    u = getattr(resp, "usage", None)
    details = getattr(u, "prompt_tokens_details", None)
    return {
        "prompt": getattr(u, "prompt_tokens", 0) or 0,
        "completion": getattr(u, "completion_tokens", 0) or 0,
        "cached": getattr(details, "cached_tokens", 0) or 0,
    }
