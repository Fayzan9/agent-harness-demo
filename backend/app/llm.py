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
    """The model name from settings: an Azure deployment name, or a model name for the other providers."""
    return get_settings().model


def request_args(model: str) -> dict:
    """The provider-specific part of a model call. Kept apart from complete() so it can be tested without a network."""
    s = get_settings()
    # A name that already says its provider, such as "gemini/gemini-2.0-flash", is passed through untouched.
    args: dict = {"model": model if "/" in model else f"{s.llm_provider}/{model}"}
    args["api_key"] = s.openai_api_key.get_secret_value()  # the one place the secret is unwrapped
    if s.openai_api_base:
        args["api_base"] = s.openai_api_base
    if s.llm_provider == "azure":
        args["api_version"] = s.openai_api_version
    return args


async def complete(model: str, messages: list[dict], tools: list[dict] | None):
    """One model call through LiteLLM. Which provider it goes to comes from settings."""
    return await litellm.acompletion(**request_args(model), messages=messages, tools=tools, timeout=REQUEST_TIMEOUT)


def usage_of(resp) -> dict:
    """Token counts the provider reports for one call. Cached is how many came from its prompt cache."""
    u = getattr(resp, "usage", None)
    details = getattr(u, "prompt_tokens_details", None)
    return {
        "prompt": getattr(u, "prompt_tokens", 0) or 0,
        "completion": getattr(u, "completion_tokens", 0) or 0,
        "cached": getattr(details, "cached_tokens", 0) or 0,
    }
