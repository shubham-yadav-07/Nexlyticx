"""Password hashing and opaque authentication-token helpers."""
from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets

_ITERATIONS = 600_000
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_email(email: str) -> str | None:
    normalized = email.strip().casefold()
    return normalized if len(normalized) <= 254 and _EMAIL_RE.fullmatch(normalized) else None


def check_password(password: str, email: str) -> str | None:
    if len(password) < 8:
        return "Use at least 8 characters for your password."
    if email and email.split("@", 1)[0].casefold() in password.casefold():
        return "Your password cannot contain your e-mail name."
    return None


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)
    return "pbkdf2_sha256${}${}${}".format(
        _ITERATIONS,
        base64.urlsafe_b64encode(salt).decode("ascii"),
        base64.urlsafe_b64encode(digest).decode("ascii"),
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt_text, digest_text = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        expected = base64.urlsafe_b64decode(digest_text.encode("ascii"))
        salt = base64.urlsafe_b64decode(salt_text.encode("ascii"))
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
    except (ValueError, TypeError, UnicodeError):
        return False
    return hmac.compare_digest(actual, expected)


_DUMMY_HASH = hash_password("dummy-password-not-used-for-login")


def dummy_hash() -> str:
    return _DUMMY_HASH


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
