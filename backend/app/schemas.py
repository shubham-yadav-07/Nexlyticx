"""Validated API request models."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ChartSpec(BaseModel):
    type: Literal["histogram", "bar", "scatter", "line"]
    x: str | None = Field(default=None, max_length=200)
    y: str | None = Field(default=None, max_length=200)
    agg: Literal["mean", "sum", "median", "min", "max", "count"] = "mean"
    bins: int = Field(default=20, ge=5, le=60)


class CleanOperation(BaseModel):
    type: Literal[
        "fill_missing", "zeros_to_nan", "cap_outliers", "drop_duplicates",
        "drop_missing_rows", "drop_columns",
    ]
    columns: list[str] = Field(default_factory=list, max_length=150)
    strategy: Literal["mean", "median", "mode", "zero", "constant"] = "median"
    value: str | None = Field(default=None, max_length=200)


class CleanRequest(BaseModel):
    ops: list[CleanOperation] = Field(default_factory=list, max_length=20)


class AskRequest(BaseModel):
    dataset_id: str = Field(min_length=4, max_length=32)
    question: str = Field(min_length=1, max_length=1000)
    target: str | None = Field(default=None, max_length=200)
