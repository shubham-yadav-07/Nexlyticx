from __future__ import annotations

import re
import sqlite3

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .. import config, db, storage
from ..core import security
from ..core.ratelimit import limiter
from ..core.utils import sanitize

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterBody(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class LoginBody(BaseModel):
    email: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class ChangePasswordBody(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


class DeleteBody(BaseModel):
    password: str = Field(min_length=1, max_length=256)


def public_user(row) -> dict | None:
    if row is None:
        return None
    return {"id": row["id"], "name": row["name"], "email": row["email"], "created_at": row["created_at"]}


def _ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "unknown")


def _too_many() -> HTTPException:
    return HTTPException(429, "Too many attempts. Please wait a few minutes and try again.")


def _secure(request: Request) -> bool:
    return request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"


def _login_response(request: Request, user_row, status: int = 200) -> JSONResponse:
    uid = int(user_row["id"])
    token = security.new_token()
    ttl = config.AUTH_TTL_DAYS * 86400
    db.create_auth_session(uid, security.token_hash(token), ttl)
    db.touch_login(uid)
    guest_owner = f"g:{request.state.sid}"
    adopted = storage.adopt(guest_owner, uid)
    resp = JSONResponse(sanitize({"user": public_user(user_row), "adopted_datasets": adopted}), status_code=status)
    resp.set_cookie(config.AUTH_COOKIE, token, max_age=ttl, httponly=True, samesite="lax", secure=_secure(request), path="/")
    return resp


def current_user(request: Request):
    user = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(401, "Please sign in to continue.")
    return user


@router.get("/me")
def me(request: Request):
    user = getattr(request.state, "user", None)
    return JSONResponse(sanitize({"user": public_user(user), "require_login": config.REQUIRE_LOGIN}))


@router.post("/register", status_code=201)
async def register(body: RegisterBody, request: Request):
    if not limiter.allow(f"reg:{_ip(request)}", config.REGISTER_LIMIT_PER_IP, 3600):
        raise _too_many()
    email = security.normalize_email(body.email)
    if not email:
        raise HTTPException(400, "Enter a valid e-mail address.")
    name = re.sub(r"\s+", " ", body.name).strip()[:80]
    if not name:
        raise HTTPException(400, "Please enter your name.")
    problem = security.check_password(body.password, email)
    if problem:
        raise HTTPException(400, problem)
    pw_hash = await run_in_threadpool(security.hash_password, body.password)
    try:
        uid = db.create_user(email, name, pw_hash)
    except sqlite3.IntegrityError:
        raise HTTPException(409, "An account with this e-mail already exists. Try signing in.") from None
    return _login_response(request, db.get_user(uid), 201)


@router.post("/login")
async def login(body: LoginBody, request: Request):
    email = security.normalize_email(body.email) or body.email.strip().lower()[:254]
    if not (limiter.allow(f"login-ip:{_ip(request)}", config.LOGIN_LIMIT_PER_IP, 900)
            and limiter.allow(f"login-em:{email}", config.LOGIN_LIMIT_PER_EMAIL, 900)):
        raise _too_many()
    user = db.get_user_by_email(email)
    stored = user["pw_hash"] if user else security.dummy_hash()
    ok = await run_in_threadpool(security.verify_password, body.password, stored)
    if not user or not ok:
        raise HTTPException(401, "Incorrect e-mail or password.")
    return _login_response(request, user)


@router.post("/logout")
def logout(request: Request):
    token = request.cookies.get(config.AUTH_COOKIE)
    if token:
        db.delete_auth_session(security.token_hash(token))
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(config.AUTH_COOKIE, path="/")
    return resp


@router.post("/password")
async def change_password(body: ChangePasswordBody, request: Request):
    user = current_user(request)
    if not await run_in_threadpool(security.verify_password, body.current_password, user["pw_hash"]):
        raise HTTPException(400, "Your current password is incorrect.")
    problem = security.check_password(body.new_password, user["email"])
    if problem:
        raise HTTPException(400, problem)
    db.update_password(user["id"], await run_in_threadpool(security.hash_password, body.new_password))
    token = request.cookies.get(config.AUTH_COOKIE)
    db.delete_other_sessions(user["id"], security.token_hash(token) if token else None)
    return {"ok": True}


@router.post("/delete-account")
async def delete_account(body: DeleteBody, request: Request):
    user = current_user(request)
    if not await run_in_threadpool(security.verify_password, body.password, user["pw_hash"]):
        raise HTTPException(400, "Password is incorrect.")
    storage.delete_user_data(user["id"])
    db.delete_user(user["id"])
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(config.AUTH_COOKIE, path="/")
    return resp
