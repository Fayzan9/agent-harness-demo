"""Login checks with tokens we sign ourselves, no Google and no API key needed.

Run from backend/:  PYTHONPATH=. uv run python tests/test_auth.py
"""
import tempfile
import time
from pathlib import Path

import fakeenv  # noqa: F401
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app import auth, runs, sessions
import app.main as main_module
from app.main import app
from app.settings import Settings


AUD, ISS = "my-client-id", "https://accounts.google.com"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)  # plays the part of Google's signing key
OTHER = rsa.generate_private_key(public_exponent=65537, key_size=2048)  # a forger's key

jwt_settings = Settings(_env_file=None, auth_mode="jwt", auth_audience=AUD, allowed_emails=["alice@corp.test", "@team.test"])
auth.get_settings = lambda: jwt_settings
main_module.settings = jwt_settings  # /auth/config reads this one
auth._signing_key = lambda token: KEY.public_key()  # no network: pretend Google's key is ours

client = TestClient(app)
failed = []


def check(name, ok, extra=""):
    print("PASS" if ok else "FAIL", name, extra)
    if not ok:
        failed.append(name)


def token(sub="u1", email="alice@corp.test", key=KEY, **over):
    claims = {"sub": sub, "email": email, "email_verified": True, "aud": AUD, "iss": ISS, "exp": time.time() + 600, **over}
    return jwt.encode({k: v for k, v in claims.items() if v is not None}, key, algorithm="RS256")


def h(t):
    return {"Authorization": f"Bearer {t}"}


def code(t, path="/auth/me"):
    return client.get(path, headers=h(t) if t else {}).status_code


# -- authentication: who are you? ------------------------------------------------------------
check("public routes need no login", client.get("/health").status_code == 200 and client.get("/auth/config").json() == {"mode": "jwt", "client_id": AUD})
check("no token -> 401", code(None) == 401)
check("garbage token -> 401", code("not-a-jwt") == 401)
check("good token -> 200", code(token()) == 200)
check("expired -> 401", code(token(exp=time.time() - 10)) == 401)
check("token for another app (audience) -> 401", code(token(aud="someone-else")) == 401)
check("wrong issuer -> 401", code(token(iss="https://evil.test")) == 401)
check("signed with a forger's key -> 401", code(token(key=OTHER)) == 401)
check("missing expiry -> 401", code(token(exp=None)) == 401)
forged_hs = jwt.encode({"sub": "u1", "email": "alice@corp.test", "email_verified": True, "aud": AUD, "iss": ISS, "exp": time.time() + 600}, "x" * 40, algorithm="HS256")
check("HS256 token (algorithm swap attack) -> 401", code(forged_hs) == 401)
check("alg none -> 401", code(jwt.encode({"sub": "u1", "aud": AUD, "iss": ISS, "exp": time.time() + 600}, None, algorithm="none")) == 401)
check("Basic scheme instead of Bearer -> 401", client.get("/auth/me", headers={"Authorization": f"Basic {token()}"}).status_code == 401)

# -- the allowlist: are you allowed? ---------------------------------------------------------
check("unverified email -> 403", code(token(email_verified=False)) == 403)
check("email not on the list -> 403", code(token(email="mallory@corp.test")) == 403)
check("domain entry lets a teammate in", code(token(email="bob@team.test")) == 200)
check("domain entry is not fooled by x@evil-team.test", code(token(email="x@evil-team.test")) == 403)
check("allowlist ignores letter case", code(token(email="ALICE@Corp.Test")) == 200)
check("every data route is closed without a token", all(
    client.request(m, p, json={}).status_code == 401
    for m, p in [("GET", "/options"), ("GET", "/sessions"), ("GET", "/sessions/x"), ("POST", "/run"), ("POST", "/approve"), ("POST", "/compact"),
                 ("POST", "/branch"), ("GET", "/workspace"), ("POST", "/workspace/reset"), ("GET", "/evals/options"), ("POST", "/evals/run")]))

# -- authorization: only your own chats ------------------------------------------------------
alice, bob = h(token(sub="alice", email="alice@corp.test")), h(token(sub="bob", email="bob@team.test"))
mine = sessions.create("", "alice's chat", "alice")
mine.turns.append({"run_id": "run-a", "task": "x"})
mine.save()
runs.register("run-a", mine.id, "alice")
check("owner sees their chat in the list", [s["id"] for s in client.get("/sessions", headers=alice).json()] == [mine.id])
check("another user's list is empty", client.get("/sessions", headers=bob).json() == [])
check("owner can open it", client.get(f"/sessions/{mine.id}", headers=alice).status_code == 200)
check("another user gets 404, not 403 (it does not even look like it exists)", client.get(f"/sessions/{mine.id}", headers=bob).status_code == 404)
check("another user cannot continue it", client.post("/run", json={"session_id": mine.id, "task": "hi"}, headers=bob).status_code == 404)
check("another user cannot resume it", client.post(f"/sessions/{mine.id}/resume", json={}, headers=bob).status_code == 404)
check("another user cannot branch from its run", client.post("/branch", json={"run_id": "run-a", "event_index": 0}, headers=bob).status_code == 404)

# -- approvals and compaction belong to the run's owner --------------------------------------
import asyncio  # noqa: E402

from app.main import approvals  # noqa: E402


async def approvals_scenario():
    waiting = asyncio.create_task(approvals.wait("call-1", "alice"))
    await asyncio.sleep(0)
    check("bob cannot approve alice's call", approvals.resolve("call-1", True, owner="bob") is False)
    check("alice can", approvals.resolve("call-1", True, owner="alice") is True)
    check("the call got alice's answer", await waiting is True)


asyncio.run(approvals_scenario())
from app.main import run_owner  # noqa: E402

run_owner["live-run"] = "alice"
check("bob cannot request compaction on alice's run", client.post("/compact", json={"run_id": "live-run"}, headers=bob).status_code == 404)
check("alice can", client.post("/compact", json={"run_id": "live-run"}, headers=alice).status_code == 200)

# -- the settings refuse unsafe combinations --------------------------------------------------
def refused(**kw):
    try:
        Settings(_env_file=None, **kw)
    except ValidationError:
        return True
    return False


check("production with login off is refused", refused(environment="production"))
check("jwt without an audience is refused", refused(auth_mode="jwt", allowed_emails=["a@b.test"]))
check("jwt with an empty allowlist is refused", refused(auth_mode="jwt", auth_audience=AUD))
check("local with login off is fine", not refused())

# -- login off: one local user, nothing changes for the demo ----------------------------------
auth.get_settings = lambda: Settings(_env_file=None)
check("login off: no token needed", client.get("/auth/me").json()["id"] == "local-user")

print("\nALL PASSED" if not failed else f"\nFAILED: {failed}")
raise SystemExit(1 if failed else 0)
