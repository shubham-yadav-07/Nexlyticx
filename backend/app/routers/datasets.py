from __future__ import annotations

import datetime as dt
import json
import re

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, JSONResponse, Response

from .. import config, storage
from ..core.deps import cached, require_dataset
from ..core.utils import sanitize
from ..schemas import ChartSpec, CleanRequest
from ..services import analysis as an
from ..services import ingest, report

router = APIRouter(prefix="/api", tags=["datasets"])


def ok(data, status: int = 200) -> JSONResponse:
    return JSONResponse(sanitize(data), status_code=status)


def _quality(entry):
    return cached(entry, "quality", lambda: an.quality(entry.df))


def _meta(entry) -> dict:
    return {"id": entry.id, "name": entry.name, "rows": int(len(entry.df)), "columns": int(entry.df.shape[1]),
            "source": entry.source, "parent_id": entry.parent_id, "saved": entry.persisted,
            "created_at": dt.datetime.fromtimestamp(entry.created_at, dt.timezone.utc).isoformat()}


def _with_quality(entry) -> dict:
    q = _quality(entry)
    return {"dataset": _meta(entry), "quality": {"score": q["score"], "grade": q["grade"]}}


def _safe_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._") or "dataset"


@router.get("/config")
def get_config():
    return ok({"max_upload_mb": config.MAX_UPLOAD_MB, "max_rows": config.MAX_ROWS, "max_datasets": config.MAX_DATASETS_PER_SESSION,
               "session_ttl_minutes": config.SESSION_TTL_MINUTES, "max_saved_datasets": config.MAX_SAVED_DATASETS,
               "require_login": config.REQUIRE_LOGIN, "version": config.APP_VERSION})


@router.get("/datasets")
def list_datasets(request: Request):
    return ok({"datasets": storage.list_meta(request.state.owner)})


@router.post("/datasets", status_code=201)
async def upload_dataset(request: Request, file: UploadFile = File(...)):
    fname = (file.filename or "dataset.csv")
    if not fname.lower().endswith((".csv", ".tsv", ".txt")):
        raise HTTPException(400, "Please upload a .csv file.")
    limit = config.MAX_UPLOAD_MB * 1024 * 1024
    raw = await file.read(limit + 1)
    if len(raw) > limit:
        raise HTTPException(413, f"File is larger than the {config.MAX_UPLOAD_MB} MB limit.")
    try:
        df = await run_in_threadpool(ingest.read_csv_bytes, raw)
    except ingest.IngestError as exc:
        raise HTTPException(400, str(exc)) from exc
    entry = storage.save(request.state.owner, fname[:120], df, "upload")
    return ok(await run_in_threadpool(_with_quality, entry), 201)


@router.post("/datasets/sample", status_code=201)
def load_sample(request: Request):
    if not config.SAMPLE_DATA_PATH.exists():
        raise HTTPException(404, "Sample dataset is not available on this server.")
    df = ingest.read_csv_bytes(config.SAMPLE_DATA_PATH.read_bytes())
    entry = storage.save(request.state.owner, "sample_retail_sales.csv", df, "sample")
    return ok(_with_quality(entry), 201)


@router.delete("/datasets/{dataset_id}")
def delete_dataset(dataset_id: str, request: Request):
    if not storage.delete(request.state.owner, dataset_id):
        raise HTTPException(404, "Dataset not found.")
    return ok({"deleted": dataset_id})


@router.get("/datasets/{dataset_id}/overview")
def overview(dataset_id: str, request: Request, target: str | None = Query(default=None, max_length=200)):
    entry = require_dataset(dataset_id, request)
    q = _quality(entry)
    data = cached(entry, ("overview", target), lambda: an.overview(entry.df, target, q))
    return ok({"dataset": _meta(entry), **data})


@router.get("/datasets/{dataset_id}/quality")
def quality(dataset_id: str, request: Request):
    entry = require_dataset(dataset_id, request)
    return ok({"dataset": _meta(entry), **_quality(entry)})


@router.get("/datasets/{dataset_id}/eda")
def eda(dataset_id: str, request: Request):
    entry = require_dataset(dataset_id, request)

    def build():
        return {"columns": an.profile(entry.df)["column_profiles"], "numeric_summary": an.describe_numeric(entry.df),
                "correlation": an.correlation_matrix(entry.df)}
    return ok({"dataset": _meta(entry), **cached(entry, "eda", build)})


@router.get("/datasets/{dataset_id}/column")
def column(dataset_id: str, request: Request, name: str = Query(max_length=200)):
    entry = require_dataset(dataset_id, request)
    if name not in entry.df.columns:
        raise HTTPException(404, "Column not found.")
    return ok(an.column_detail(entry.df, name))


@router.get("/datasets/{dataset_id}/preview")
def preview(dataset_id: str, request: Request, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200)):
    entry = require_dataset(dataset_id, request)
    page = entry.df.iloc[offset: offset + limit]
    rows = [[None if (v is None or (isinstance(v, float) and v != v)) else v for v in r]
            for r in page.astype(object).where(page.notna(), None).values.tolist()]
    return ok({"columns": list(entry.df.columns), "rows": rows, "total": int(len(entry.df)), "offset": offset})


@router.post("/datasets/{dataset_id}/chart")
def chart(dataset_id: str, spec: ChartSpec, request: Request):
    entry = require_dataset(dataset_id, request)
    try:
        return ok(an.chart_data(entry.df, spec.model_dump()))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/datasets/{dataset_id}/clean", status_code=201)
def clean(dataset_id: str, body: CleanRequest, request: Request):
    entry = require_dataset(dataset_id, request)
    before = _quality(entry)
    try:
        new_df, log = an.apply_cleaning(entry.df, [op.model_dump() for op in body.ops])
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if new_df.empty or new_df.shape[1] == 0:
        raise HTTPException(400, "These steps would remove all data. Nothing was changed.")
    base = re.sub(r" \(cleaned( \d+)?\)$", "", entry.name)
    new_entry = storage.save(request.state.owner, f"{base} (cleaned)", new_df, "cleaned", parent_id=entry.id)
    after = _quality(new_entry)
    return ok({"dataset": _meta(new_entry), "log": log,
               "before": {"score": before["score"], "grade": before["grade"], "rows": int(len(entry.df))},
               "after": {"score": after["score"], "grade": after["grade"], "rows": int(len(new_df))}}, 201)


@router.get("/datasets/{dataset_id}/download.csv")
def download_csv(dataset_id: str, request: Request):
    entry = require_dataset(dataset_id, request)
    body = entry.df.to_csv(index=False)
    fname = _safe_name(entry.name.rsplit(".", 1)[0]) + ".csv"
    return Response(body, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@router.get("/datasets/{dataset_id}/summary.json")
def download_summary(dataset_id: str, request: Request, target: str | None = Query(default=None, max_length=200)):
    entry = require_dataset(dataset_id, request)
    data = cached(entry, ("overview", target), lambda: an.overview(entry.df, target, _quality(entry)))
    payload = json.dumps(sanitize({"dataset": _meta(entry), **data}), indent=2)
    fname = _safe_name(entry.name.rsplit(".", 1)[0]) + "_summary.json"
    return Response(payload, media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@router.get("/datasets/{dataset_id}/report", response_class=HTMLResponse)
def html_report(dataset_id: str, request: Request, target: str | None = Query(default=None, max_length=200)):
    entry = require_dataset(dataset_id, request)
    html = report.build_report(entry.name, entry.df, _quality(entry), target)
    return HTMLResponse(html)
