import hmac
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt


TOKEN_ISSUER = "support-copilot-local"
TOKEN_AUDIENCE = "support-copilot-api"
TOKEN_TTL_SECONDS = 3600
MIN_SECRET_LENGTH = 32
MIN_PASSWORD_LENGTH = 12


class AuthenticationError(Exception):
    pass


class AuthenticationConfigurationError(Exception):
    pass


@dataclass(frozen=True)
class AuthenticationSettings:
    secret: str
    username: str
    password: str


def _settings() -> AuthenticationSettings | None:
    secret = os.environ.get("SUPPORT_COPILOT_AUTH_SECRET", "")
    username = os.environ.get("SUPPORT_COPILOT_OPERATOR_USERNAME", "").strip()
    password = os.environ.get("SUPPORT_COPILOT_OPERATOR_PASSWORD", "")
    if (
        len(secret) < MIN_SECRET_LENGTH
        or not username
        or len(password) < MIN_PASSWORD_LENGTH
    ):
        return None
    return AuthenticationSettings(secret, username, password)


def issue_access_token(username: str, password: str) -> str:
    settings = _settings()
    if settings is None:
        raise AuthenticationConfigurationError

    username_matches = hmac.compare_digest(
        username.strip().encode("utf-8"), settings.username.encode("utf-8")
    )
    password_matches = hmac.compare_digest(
        password.encode("utf-8"), settings.password.encode("utf-8")
    )
    if not (username_matches and password_matches):
        raise AuthenticationError

    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": settings.username,
            "iss": TOKEN_ISSUER,
            "aud": TOKEN_AUDIENCE,
            "iat": now,
            "exp": now + timedelta(seconds=TOKEN_TTL_SECONDS),
        },
        settings.secret,
        algorithm="HS256",
    )


def verify_access_token(token: str) -> str:
    settings = _settings()
    if settings is None:
        raise AuthenticationError
    try:
        claims = jwt.decode(
            token,
            settings.secret,
            algorithms=["HS256"],
            issuer=TOKEN_ISSUER,
            audience=TOKEN_AUDIENCE,
            options={"require": ["sub", "iss", "aud", "iat", "exp"]},
        )
    except jwt.PyJWTError as exc:
        raise AuthenticationError from exc

    subject = claims.get("sub")
    if not isinstance(subject, str) or not hmac.compare_digest(
        subject.encode("utf-8"), settings.username.encode("utf-8")
    ):
        raise AuthenticationError
    return subject