"""Dataset store.

Owners are strings:
  "g:<session id>"  guest  - kept in memory only, deleted after
                             NX_SESSION_TTL_MINUTES of inactivity, never written to disk.
  "u:<user id>"     member - also saved to private per-user storage (CSV on disk +
                             a row in SQLite) so datasets survive restarts and logins.
                             Memory is just a cache; saved data is reloaded on demand.

Owners can only ever read their own datasets.
"""
from __future__ import annotations

import datetime as dt
import re
import secrets
import shutil
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from . import config, db
from .services import ingest

_LOCK = threading.RLock()
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{4,32}$")


@dataclass
class DatasetEntry:
    id: str
    owner: str
    name: str
    df: pd.DataFrame
    source: str = "upload"          # upload | sample | cleaned
    parent_id: str | None = None
    created_at: float = field(default_factory=time.time)
    last_access: float = field(default_factory=time.time)
    cache: dict = field(default_factory=dict)
    persisted: bool = False


_DATASETS: dict[str, DatasetEntry] = {}


def new_session_id() -> str:
    return secrets.token_urlsafe(18)


def user_id_of(owner: str) -> int | None:
    if owner.startswith("u:"):
        try:
            return int(owner[2:])
        except ValueError:
            return None
    return None


def _path(uid: int, ds_id: str) -> Path:
    return config.USER_DATA_DIR / str(uid) / f"{ds_id}.csv"


def _expired(e: DatasetEntry) -> bool:
    return e.last_access < time.time() - config.SESSION_TTL_MINUTES * 60


def _persist(e: DatasetEntry) -> None:
    uid = user_id_of(e.owner)
    if uid is None:
        return
    path = _path(uid, e.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    e.df.to_csv(path, index=False)
    db.add_dataset(e.id, uid, e.name, e.source, e.parent_id, int(len(e.df)), int(e.df.shape[1]), e.created_at)
    e.persisted = True


def _enforce_user_cap(uid: int) -> None:
    rows = db.list_datasets(uid)
    for row in rows[: max(0, len(rows) - config.MAX_SAVED_DATASETS)]:
        _delete_saved(uid, row["id"])


def _delete_saved(uid: int, ds_id: str) -> None:
    db.delete_dataset_row(uid, ds_id)
    try:
        _path(uid, ds_id).unlink(missing_ok=True)
    except OSError:
        pass
    _DATASETS.pop(ds_id, None)


def _evict_memory_locked() -> None:
    cutoff = time.time() - config.SESSION_TTL_MINUTES * 60
    for k in [k for k, v in _DATASETS.items() if v.last_access < cutoff]:
        del _DATASETS[k]
    while len(_DATASETS) >= config.MAX_TOTAL_DATASETS:
        oldest = min(_DATASETS.values(), key=lambda e: e.last_access)
        del _DATASETS[oldest.id]


def purge_expired() -> int:
    with _LOCK:
        before = len(_DATASETS)
        _evict_memory_locked()
        return before - len(_DATASETS)


def save(owner: str, name: str, df: pd.DataFrame, source: str = "upload", parent_id: str | None = None) -> DatasetEntry:
    with _LOCK:
        _evict_memory_locked()
        uid = user_id_of(owner)
        if uid is None:   # guests: cap how many they can hold
            mine = sorted((e for e in _DATASETS.values() if e.owner == owner), key=lambda e: e.last_access)
            while len(mine) >= config.MAX_DATASETS_PER_SESSION:
                del _DATASETS[mine.pop(0).id]
        entry = DatasetEntry(id=secrets.token_urlsafe(8), owner=owner, name=name, df=df, source=source, parent_id=parent_id)
        _DATASETS[entry.id] = entry
        if uid is not None:
            _persist(entry)
            _enforce_user_cap(uid)
        return entry


def get(owner: str, dataset_id: str) -> DatasetEntry | None:
    if not _ID_RE.match(dataset_id or ""):
        return None
    with _LOCK:
        e = _DATASETS.get(dataset_id)
        uid = user_id_of(owner)
        if e is not None:
            if e.owner != owner:
                return None
            if not _expired(e):
                e.last_access = time.time()
                return e
            del _DATASETS[dataset_id]
            if uid is None:
                return None
        if uid is None:
            return None
        row = db.get_dataset_row(uid, dataset_id)
        if row is None:
            return None
        path = _path(uid, dataset_id)
        if not path.exists():
            db.delete_dataset_row(uid, dataset_id)
            return None
        _evict_memory_locked()
        df = ingest.read_csv_bytes(path.read_bytes(), enforce_limits=False)
        e = DatasetEntry(id=row["id"], owner=owner, name=row["name"], df=df, source=row["source"],
                         parent_id=row["parent_id"], created_at=row["created_at"], persisted=True)
        _DATASETS[e.id] = e
        return e


def _iso(ts: float) -> str:
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).isoformat()


def list_meta(owner: str) -> list[dict]:
    with _LOCK:
        uid = user_id_of(owner)
        if uid is not None:
            return [{"id": r["id"], "name": r["name"], "rows": r["rows"], "columns": r["cols"], "source": r["source"],
                     "parent_id": r["parent_id"], "created_at": _iso(r["created_at"]), "saved": True}
                    for r in db.list_datasets(uid)]
        _evict_memory_locked()
        mine = sorted((e for e in _DATASETS.values() if e.owner == owner), key=lambda e: e.created_at)
        return [{"id": e.id, "name": e.name, "rows": int(len(e.df)), "columns": int(e.df.shape[1]), "source": e.source,
                 "parent_id": e.parent_id, "created_at": _iso(e.created_at), "saved": False} for e in mine]


def delete(owner: str, dataset_id: str) -> bool:
    with _LOCK:
        uid = user_id_of(owner)
        if uid is not None:
            if db.get_dataset_row(uid, dataset_id) is None:
                return False
            _delete_saved(uid, dataset_id)
            return True
        e = _DATASETS.get(dataset_id)
        if e is None or e.owner != owner:
            return False
        del _DATASETS[dataset_id]
        return True


def adopt(guest_owner: str, user_id: int) -> int:
    """Move a guest's in-memory datasets into a member's account (called on sign-in / sign-up)."""
    with _LOCK:
        moved = 0
        new_owner = f"u:{user_id}"
        for e in [e for e in _DATASETS.values() if e.owner == guest_owner and not _expired(e)]:
            e.owner = new_owner
            _persist(e)
            moved += 1
        if moved:
            _enforce_user_cap(user_id)
        return moved


def delete_user_data(user_id: int) -> None:
    with _LOCK:
        owner = f"u:{user_id}"
        for k in [k for k, v in _DATASETS.items() if v.owner == owner]:
            del _DATASETS[k]
        shutil.rmtree(config.USER_DATA_DIR / str(user_id), ignore_errors=True)


def count() -> int:
    with _LOCK:
        return len(_DATASETS)
