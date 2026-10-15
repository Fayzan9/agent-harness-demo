"""Settings checks: the app must refuse a bad config, and a secret must never leak.

Run from backend/:  PYTHONPATH=. uv run python tests/test_settings.py
"""
import os

from pydantic import ValidationError

from app.settings import Settings

SECRET = "super-secret-value-123"
GOOD = {"OPENAI_API_BASE": "https://x.example.test", "OPENAI_API_KEY": SECRET, "MODEL": "m"}


def build(env: dict) -> Settings:
    for name in ("OPENAI_API_BASE", "OPENAI_API_KEY", "MODEL", "OPENAI_API_VERSION", "ENVIRONMENT", "CORS_ORIGINS"):
        os.environ.pop(name, None)
    os.environ.update(env)
    return Settings(_env_file=None)  # ignore any real .env so the test is the same on every machine


def test_good_config_and_defaults():
    s = build(GOOD)
    assert s.environment == "local" and s.openai_api_version and s.cors_origins == ["http://localhost:3000"]
    assert s.openai_api_key.get_secret_value() == SECRET


def test_secret_is_hidden():
    s = build(GOOD)
    assert SECRET not in repr(s) and SECRET not in str(s)


def test_missing_setting_stops_startup_without_leaking():
    try:
        build({k: v for k, v in GOOD.items() if k != "MODEL"})  # the key is present, the model is missing
    except ValidationError as e:
        text = str(e)
        assert "model" in text.lower() and SECRET not in text, text
        return
    raise AssertionError("a missing MODEL should have stopped the app")


def test_bad_environment_name_is_rejected():
    try:
        build({**GOOD, "ENVIRONMENT": "prod"})  # a typo, not one of local/staging/production
    except ValidationError:
        return
    raise AssertionError("an unknown environment name should be rejected")


def test_cors_origins_from_env():
    s = build({**GOOD, "CORS_ORIGINS": '["https://app.example.test"]'})
    assert s.cors_origins == ["https://app.example.test"]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
