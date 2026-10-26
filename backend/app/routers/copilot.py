from __future__ import annotations

from fastapi import APIRouter, Request

from ..core.deps import cached, require_dataset
from ..core.utils import sanitize
from ..schemas import AskRequest
from ..services import analysis as an
from ..services import copilot_engine
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api", tags=["copilot"])


@router.post("/copilot/ask")
def ask(body: AskRequest, request: Request):
    entry = require_dataset(body.dataset_id, request)
    result = copilot_engine.answer(entry.df, body.question, body.target,
                                   quality_fn=lambda: cached(entry, "quality", lambda: an.quality(entry.df)))
    return JSONResponse(sanitize(result))
