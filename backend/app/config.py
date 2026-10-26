"""Application settings loaded from environment variables."""
from __future__ import annotations

import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent
FRONTEND_DIR = PROJECT_DIR / "frontend"
SAMPLE_DATA_PATH = PROJECT_DIR / "sample_data" / "sample_retail_sales.csv"


def _int_setting(name: str, default: int, minimum: int = 1) -> int:
    raw = os.getenv(name)
    try:
        value = default if raw is None else int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer.") from exc
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}.")
    return value


def _bool_setting(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be true or false.")


APP_NAME = "NexlyticX"
APP_VERSION = "1.0.0"
REQUIRE_LOGIN = _bool_setting("NX_REQUIRE_LOGIN")
DB_PATH = Path(os.getenv("NX_DB_PATH", "data/nexlyticx.db"))
if not DB_PATH.is_absolute():
    DB_PATH = BACKEND_DIR / DB_PATH
DB_PATH = DB_PATH.resolve()
USER_DATA_DIR = DB_PATH.parent / "user_data"
SESSION_TTL_MINUTES = _int_setting("NX_SESSION_TTL_MINUTES", 120)
MAX_UPLOAD_MB = _int_setting("NX_MAX_UPLOAD_MB", 20)
MAX_ROWS = _int_setting("NX_MAX_ROWS", 200_000)
MAX_COLS = _int_setting("NX_MAX_COLS", 150)
MAX_SAVED_DATASETS = _int_setting("NX_MAX_SAVED_DATASETS", 10)
MAX_DATASETS_PER_SESSION = 10
MAX_TOTAL_DATASETS = 100
AUTH_TTL_DAYS = _int_setting("NX_AUTH_TTL_DAYS", 14)
RATE_LIMIT_PER_MINUTE = _int_setting("NX_RATE_LIMIT_PER_MINUTE", 240)
UPLOAD_LIMIT_PER_10MIN = _int_setting("NX_UPLOAD_LIMIT_PER_10MIN", 30)
LOGIN_LIMIT_PER_IP = _int_setting("NX_LOGIN_LIMIT_PER_IP", 30)
LOGIN_LIMIT_PER_EMAIL = _int_setting("NX_LOGIN_LIMIT_PER_EMAIL", 10)
REGISTER_LIMIT_PER_IP = _int_setting("NX_REGISTER_LIMIT_PER_IP", 10)
ENABLE_DOCS = _bool_setting("NX_ENABLE_DOCS")
ALLOWED_ORIGINS = [origin.strip() for origin in os.getenv("NX_ALLOWED_ORIGINS", "").split(",") if origin.strip()]
SESSION_COOKIE = "nx_session"
AUTH_COOKIE = "nx_auth"
