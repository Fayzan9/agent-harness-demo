"""Who is calling? Check the signed token the identity provider (Google) gave the browser.

We never see a password. We only verify a JWT: was it signed by the provider, is it for us, has it expired?
"""
import jwt
from fastapi import Depends, HTTPException, Request
from jwt import PyJWKClient
from pydantic import BaseModel

from .sessions import LOCAL_USER
from .settings import get_settings

_jwks: PyJWKClient | None = None


class User(BaseModel):
    id: str  # stable id from the provider (the "sub" claim). Chats are owned by this.
    email: str


def _signing_key(token: str):
    """The provider's public key that matches this token. Fetched from its JWKS url and cached by PyJWKClient."""
    global _jwks
    if _jwks is None:
        _jwks = PyJWKClient(get_settings().auth_jwks_url, cache_keys=True)
    return _jwks.get_signing_key_from_jwt(token).key


def _allowed(email: str, allowlist: list[str]) -> bool:
    email = email.lower()
    for entry in (e.strip().lower() for e in allowlist):
        if entry.startswith("@") and email.endswith(entry):  # "@company.com": the "@" stops "x@evil-company.com"
            return True
        if email == entry:
            return True
    return False


def verify(token: str) -> User:
    """Return the user for a good token, or raise 401 (who are you?) / 403 (you are not allowed)."""
    s = get_settings()
    try:
        claims = jwt.decode(
            token,
            _signing_key(token),
            algorithms=["RS256"],  # only the algorithm we expect, so a forged "alg: none" or HS256 token is refused
            audience=s.auth_audience,  # a token Google issued for some OTHER app is refused
            issuer=s.auth_issuers,
            options={"require": ["exp", "iss", "aud", "sub"]},
        )
    except jwt.PyJWTError:  # bad signature, expired, wrong audience or issuer, malformed: one answer, no detail
        raise HTTPException(401, "Sign in again.", headers={"WWW-Authenticate": "Bearer"})
    email = claims.get("email", "")
    if not (email and claims.get("email_verified") is True and _allowed(email, s.allowed_emails)):
        raise HTTPException(403, "This account is not allowed to use the app.")
    return User(id=claims["sub"], email=email)


def current_user(request: Request) -> User:
    """FastAPI dependency: put it on a route and the route only runs for a signed-in, allowed user."""
    if get_settings().auth_mode == "off":
        return User(id=LOCAL_USER, email="local@localhost")
    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(401, "Sign in first.", headers={"WWW-Authenticate": "Bearer"})
    return verify(token)


CurrentUser = Depends(current_user)
