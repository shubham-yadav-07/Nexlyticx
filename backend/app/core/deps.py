"""Request dependencies shared by API routers."""
from __future__ import annotations

from typing import Any, Callable

from fastapi import HTTPException, Request

from .. import storage


def cached(entry: storage.DatasetEntry, key: Any, builder: Callable[[], Any]) -> Any:
    if key not in entry.cache:
        entry.cache[key] = builder()
    return entry.cache[key]


def require_dataset(dataset_id: str, request: Request) -> storage.DatasetEntry:
    entry = storage.get(request.state.owner, dataset_id)
    if entry is None:
        raise HTTPException(404, "Dataset not found.")
    return entry
