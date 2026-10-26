"""NexlyticX server.

    uvicorn main:app --reload

Serves the REST API (/api/*) and the static frontend from one process.
IMPORTANT: run a single worker (guest datasets live in this process's memory).
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app import config, db, storage
from app.core import security
from app.core.ratelimit import limiter
from app.routers import auth, copilot, datasets

log = logging.getLogger("nexlyticx")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self'; "
       "img-src 'self' data: blob:; connect-src 'self'; frame-ancestors 'self'; base-uri 'self'; form-action 'self'")
REPORT_CSP = ("default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; font-src 'self'; "
              "img-src data:; frame-ancestors 'self'; base-uri 'none'")
STATIC_PREFIXES = ("/css/", "/js/", "/assets/")
OPEN_API_PATHS = ("/api/health", "/api/config")


async def _janitor():
    while True:
        await asyncio.sleep(300)
        removed = storage.purge_expired()
        db.purge_expired_sessions()
        if removed:
            log.info("Released %d dataset(s) from memory; %d active", removed, storage.count())


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init()
    task = asyncio.create_task(_janitor())
    yield
    task.cancel()


app = FastAPI(title=config.APP_NAME, version=config.APP_VERSION, lifespan=lifespan,
              docs_url="/docs" if config.ENABLE_DOCS else None, redoc_url=None,
              openapi_url="/openapi.json" if config.ENABLE_DOCS else None,
              description="Upload a CSV, get a real statistical profile, and ask it questions.")

app.add_middleware(GZipMiddleware, minimum_size=1024)
if config.ALLOWED_ORIGINS:
    app.add_middleware(CORSMiddleware, allow_origins=config.ALLOWED_ORIGINS, allow_credentials=True,
                       allow_methods=["*"], allow_headers=["*"])


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@app.middleware("http")
async def gate(request: Request, call_next):
    path = request.url.path
    if path.startswith(STATIC_PREFIXES):
        response = await call_next(request)
        if path.startswith("/assets/fonts/"):
            response.headers["Cache-Control"] = "public, max-age=2592000, immutable"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    # --- identity: guest session id + (optional) signed-in user
    sid = request.cookies.get(config.SESSION_COOKIE)
    new_session = not sid or not (16 <= len(sid) <= 64)
    if new_session:
        sid = storage.new_session_id()
    request.state.sid = sid
    request.state.user = None
    token = request.cookies.get(config.AUTH_COOKIE)
    if token:
        request.state.user = db.user_for_token(security.token_hash(token))
    user = request.state.user
    request.state.owner = f"u:{user['id']}" if user else f"g:{sid}"

    is_api = path.startswith("/api/")
    if is_api:
        # CSRF: browsers can't add custom headers cross-site without a CORS preflight we never grant.
        if request.method not in ("GET", "HEAD", "OPTIONS") and not request.headers.get("x-nx"):
            return JSONResponse({"detail": "Missing security header."}, status_code=403)
        ip = _client_ip(request)
        limited = not limiter.allow(f"api:{ip}", config.RATE_LIMIT_PER_MINUTE, 60)
        if not limited and request.method == "POST" and path in ("/api/datasets", "/api/datasets/sample"):
            limited = not limiter.allow(f"up:{ip}", config.UPLOAD_LIMIT_PER_10MIN, 600)
        if limited:
            return JSONResponse({"detail": "Too many requests. Please slow down and try again shortly."},
                                status_code=429, headers={"Retry-After": "30"})
        if (config.REQUIRE_LOGIN and user is None and not path.startswith("/api/auth/")
                and path not in OPEN_API_PATHS):
            return JSONResponse({"detail": "Please sign in to continue.", "login_required": True}, status_code=401)

    response = await call_next(request)

    if new_session:
        secure = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
        response.set_cookie(config.SESSION_COOKIE, sid, max_age=86400, httponly=True, samesite="lax",
                            secure=secure, path="/")

    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    if not (path.startswith("/docs") or path.startswith("/openapi")):
        response.headers["Content-Security-Policy"] = REPORT_CSP if path.endswith("/report") else CSP
    if is_api or path in ("/login", "/signup", "/app", "/dashboard.html"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(Exception)
async def unhandled(_: Request, exc: Exception):
    log.exception("Unhandled error: %s", exc)
    return JSONResponse({"detail": "Something went wrong on our side. Please try again."}, status_code=500)


@app.get("/api/health")
def health():
    return {"status": "ok", "version": config.APP_VERSION, "active_datasets": storage.count()}


app.include_router(auth.router)
app.include_router(datasets.router)
app.include_router(copilot.router)

FRONTEND = config.FRONTEND_DIR
if FRONTEND.exists():
    for sub in ("css", "js", "assets"):
        if (FRONTEND / sub).exists():
            app.mount(f"/{sub}", StaticFiles(directory=FRONTEND / sub), name=sub)

    @app.get("/", include_in_schema=False)
    def landing():
        return FileResponse(FRONTEND / "index.html")

    @app.get("/app", include_in_schema=False)
    @app.get("/dashboard.html", include_in_schema=False)
    def workspace(request: Request):
        if config.REQUIRE_LOGIN and request.state.user is None:
            return RedirectResponse("/login?next=/app", status_code=302)
        return FileResponse(FRONTEND / "dashboard.html")

    @app.get("/login", include_in_schema=False)
    @app.get("/signup", include_in_schema=False)
    def auth_page(request: Request):
        if request.state.user is not None:
            return RedirectResponse("/app", status_code=302)
        return FileResponse(FRONTEND / "login.html")

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon():
        return FileResponse(FRONTEND / "assets" / "favicon.svg", media_type="image/svg+xml")
