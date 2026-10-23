"""Provider settings: the right model name and arguments reach LiteLLM, and no network or key is needed.

Run from backend/:  PYTHONPATH=. uv run python tests/test_llm.py
"""
import os

from pydantic import ValidationError

from app import llm
from app.settings import Settings

SECRET = "super-secret-value-123"
NAMES = ("LLM_PROVIDER", "LLM_API_KEY", "LLM_API_BASE", "OPENAI_API_BASE", "OPENAI_API_KEY", "MODEL", "OPENAI_API_VERSION")


def use(env: dict) -> Settings:
    """Make llm.py see these settings, ignoring any real .env on this machine."""
    for name in NAMES:
        os.environ.pop(name, None)
    os.environ.update(env)
    s = Settings(_env_file=None)
    llm.get_settings = lambda: s
    return s


def test_openai_needs_no_base_and_no_azure_arguments():
    use({"LLM_PROVIDER": "openai", "LLM_API_KEY": SECRET, "MODEL": "gpt-4o-mini"})
    args = llm.request_args("gpt-4o-mini")
    assert args["model"] == "openai/gpt-4o-mini" and args["api_key"] == SECRET
    assert "api_base" not in args and "api_version" not in args, args


def test_azure_sends_base_and_version():
    use({"LLM_PROVIDER": "azure", "LLM_API_BASE": "https://r.example.test", "LLM_API_KEY": SECRET, "MODEL": "dep"})
    args = llm.request_args("dep")
    assert args["model"] == "azure/dep" and args["api_base"] == "https://r.example.test" and args["api_version"], args


def test_gemini_and_anthropic_prefix():
    use({"LLM_PROVIDER": "gemini", "LLM_API_KEY": SECRET, "MODEL": "gemini-2.0-flash"})
    assert llm.request_args("gemini-2.0-flash")["model"] == "gemini/gemini-2.0-flash"
    use({"LLM_PROVIDER": "anthropic", "LLM_API_KEY": SECRET, "MODEL": "m"})
    assert llm.request_args("m")["model"] == "anthropic/m"


def test_full_litellm_id_is_passed_through():
    use({"LLM_PROVIDER": "openai", "LLM_API_KEY": SECRET, "MODEL": "ollama/llama3", "LLM_API_BASE": "http://localhost:11434"})
    args = llm.request_args("ollama/llama3")
    assert args["model"] == "ollama/llama3" and args["api_base"] == "http://localhost:11434", args


def test_old_azure_env_still_works():
    s = use({"OPENAI_API_BASE": "https://r.example.test", "OPENAI_API_KEY": SECRET, "MODEL": "dep"})
    assert s.llm_provider == "azure"
    assert llm.request_args("dep")["model"] == "azure/dep"


def test_provider_defaults_to_openai_without_a_base():
    s = use({"LLM_API_KEY": SECRET, "MODEL": "gpt-4o-mini"})
    assert s.llm_provider == "openai"


def test_azure_without_a_base_stops_startup():
    try:
        use({"LLM_PROVIDER": "azure", "LLM_API_KEY": SECRET, "MODEL": "dep"})
    except ValidationError as e:
        assert "LLM_API_BASE" in str(e) and SECRET not in str(e)
        return
    raise AssertionError("azure without an endpoint should have stopped the app")


def test_missing_key_stops_startup_without_leaking():
    try:
        use({"LLM_PROVIDER": "openai", "MODEL": "gpt-4o-mini"})
    except ValidationError:
        return
    raise AssertionError("a missing key should have stopped the app")


def test_key_is_hidden_in_repr():
    s = use({"LLM_PROVIDER": "openai", "LLM_API_KEY": SECRET, "MODEL": "m"})
    assert SECRET not in repr(s) and SECRET not in str(s)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
