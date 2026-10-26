"""SQLite persistence for accounts, authentication sessions and saved datasets."""
from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator

from . import config


@contextmanager
def _connection() -> Iterator[sqlite3.Connection]:
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(config.DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 10000")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init() -> None:
    with _connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                name TEXT NOT NULL,
                pw_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_login REAL
            );
            CREATE TABLE IF NOT EXISTS auth_sessions (
                token_hash TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                expires_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS auth_sessions_expiry ON auth_sessions(expires_at);
            CREATE TABLE IF NOT EXISTS datasets (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                source TEXT NOT NULL,
                parent_id TEXT,
                rows INTEGER NOT NULL,
                cols INTEGER NOT NULL,
                created_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS datasets_by_owner ON datasets(user_id, created_at);
            """
        )


def create_user(email: str, name: str, pw_hash: str) -> int:
    created_at = datetime.now(timezone.utc).isoformat()
    with _connection() as connection:
        cursor = connection.execute(
            "INSERT INTO users(email, name, pw_hash, created_at) VALUES (?, ?, ?, ?)",
            (email, name, pw_hash, created_at),
        )
        return int(cursor.lastrowid)


def get_user(user_id: int) -> sqlite3.Row | None:
    with _connection() as connection:
        return connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def get_user_by_email(email: str) -> sqlite3.Row | None:
    with _connection() as connection:
        return connection.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()


def create_auth_session(user_id: int, token_hash: str, ttl_seconds: int) -> None:
    with _connection() as connection:
        connection.execute(
            "INSERT INTO auth_sessions(token_hash, user_id, expires_at) VALUES (?, ?, ?)",
            (token_hash, user_id, time.time() + ttl_seconds),
        )


def user_for_token(token_hash: str) -> sqlite3.Row | None:
    with _connection() as connection:
        return connection.execute(
            """
            SELECT users.* FROM users
            JOIN auth_sessions ON auth_sessions.user_id = users.id
            WHERE auth_sessions.token_hash = ? AND auth_sessions.expires_at > ?
            """,
            (token_hash, time.time()),
        ).fetchone()


def delete_auth_session(token_hash: str) -> None:
    with _connection() as connection:
        connection.execute("DELETE FROM auth_sessions WHERE token_hash = ?", (token_hash,))


def delete_other_sessions(user_id: int, keep_token_hash: str | None) -> None:
    with _connection() as connection:
        if keep_token_hash:
            connection.execute(
                "DELETE FROM auth_sessions WHERE user_id = ? AND token_hash != ?",
                (user_id, keep_token_hash),
            )
        else:
            connection.execute("DELETE FROM auth_sessions WHERE user_id = ?", (user_id,))


def purge_expired_sessions() -> None:
    with _connection() as connection:
        connection.execute("DELETE FROM auth_sessions WHERE expires_at <= ?", (time.time(),))


def touch_login(user_id: int) -> None:
    with _connection() as connection:
        connection.execute("UPDATE users SET last_login = ? WHERE id = ?", (time.time(), user_id))


def update_password(user_id: int, pw_hash: str) -> None:
    with _connection() as connection:
        connection.execute("UPDATE users SET pw_hash = ? WHERE id = ?", (pw_hash, user_id))


def delete_user(user_id: int) -> None:
    with _connection() as connection:
        connection.execute("DELETE FROM users WHERE id = ?", (user_id,))


def add_dataset(dataset_id: str, user_id: int, name: str, source: str, parent_id: str | None,
                rows: int, cols: int, created_at: float) -> None:
    with _connection() as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO datasets(id, user_id, name, source, parent_id, rows, cols, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (dataset_id, user_id, name, source, parent_id, rows, cols, created_at),
        )


def list_datasets(user_id: int) -> list[sqlite3.Row]:
    with _connection() as connection:
        return connection.execute(
            "SELECT * FROM datasets WHERE user_id = ? ORDER BY created_at ASC",
            (user_id,),
        ).fetchall()


def get_dataset_row(user_id: int, dataset_id: str) -> sqlite3.Row | None:
    with _connection() as connection:
        return connection.execute(
            "SELECT * FROM datasets WHERE user_id = ? AND id = ?",
            (user_id, dataset_id),
        ).fetchone()


def delete_dataset_row(user_id: int, dataset_id: str) -> None:
    with _connection() as connection:
        connection.execute("DELETE FROM datasets WHERE user_id = ? AND id = ?", (user_id, dataset_id))
