import os

import litellm


def default_model() -> str:
    """Azure deployment name from the MODEL env var."""
    return os.environ.get("MODEL", "")


async def complete(deployment: str, messages: list[dict], tools: list[dict] | None):
    """One model call through LiteLLM, pointed at an Azure OpenAI deployment."""
    return await litellm.acompletion(
        model=f"azure/{deployment}",
        api_base=os.environ["OPENAI_API_BASE"],
        api_key=os.environ["OPENAI_API_KEY"],
        api_version=os.environ.get("OPENAI_API_VERSION", "2025-04-01-preview"),
        messages=messages,
        tools=tools,
    )
