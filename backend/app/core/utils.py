"""Shared serialization and numeric helpers."""
from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any

import numpy as np


def rnd(value: Any, digits: int = 2) -> float | None:
    if value is None:
        return None
    number = float(value)
    return round(number, digits) if math.isfinite(number) else None


def sanitize(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, np.generic):
        return sanitize(value.item())
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(key): sanitize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize(item) for item in value]
    return value
