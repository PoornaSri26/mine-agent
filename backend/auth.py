"""Account API and request ownership.

Sign-in is switched off for this review build. `/query`, `/sessions/*` and
`/audit_report_pdf` resolve ownership with `request_owner`, which still accepts a
bearer token when one is sent and otherwise falls back to an anonymous guest
identified by the browser's `X-Guest-Id` header. Conversations stay separated per
guest, so two reviewers on the same deployment do not share a history.

Everything under `/auth/*` is kept intact: when authentication is added back,
switch the handlers in `main.py` and the session routes below from
`request_owner` to `current_user` and the guest path becomes unreachable.
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

import db
import security

router = APIRouter(tags=["auth"])

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
GUEST_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
# Requests that send no usable guest id (curl, probes) share one bucket.
ANONYMOUS_GUEST = "anonymous"


class RegisterRequest(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    email: str = Field(max_length=200)
    password: str = Field(min_length=8, max_length=200)


class LoginRequest(BaseModel):
    email: str = Field(max_length=200)
    password: str = Field(min_length=1, max_length=200)


class SessionCreate(BaseModel):
    title: str = Field(default="New chat", max_length=120)


class SessionRename(BaseModel):
    title: str = Field(min_length=1, max_length=120)


def _public_user(user: dict) -> dict:
    return {"id": user["id"], "name": user["name"], "email": user["email"]}


def _issue(user: dict) -> dict:
    return {"token": db.issue_token(user["id"]), "user": _public_user(user)}


def current_user(authorization: str | None = Header(default=None)) -> dict:
    """Strict variant: a valid bearer token is required."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Sign in to continue.")
    token = authorization.split(" ", 1)[1].strip()
    user_id = db.user_id_for_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Your session expired. Please sign in again.")
    user = db.get_user(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Account not found.")
    return user


def request_owner(
    authorization: str | None = Header(default=None),
    guest_id: str | None = Header(default=None, alias="X-Guest-Id"),
) -> dict:
    """Resolve the owner of a request without requiring a sign-in.

    A valid bearer token still wins, so the account path keeps working; anything
    else is scoped to the guest id the browser keeps in localStorage.
    """
    if authorization and authorization.lower().startswith("bearer "):
        user_id = db.user_id_for_token(authorization.split(" ", 1)[1].strip())
        if user_id:
            user = db.get_user(user_id)
            if user:
                return user

    value = (guest_id or "").strip()
    return db.ensure_guest(value if GUEST_ID_RE.match(value) else ANONYMOUS_GUEST)


@router.post("/auth/register")
def register(payload: RegisterRequest) -> dict:
    email = payload.email.strip().lower()
    if not EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="Enter a valid email address.")
    if db.get_user_by_email(email):
        raise HTTPException(status_code=409, detail="An account with this email already exists.")
    user = db.create_user(payload.name, email, payload.password)
    return _issue(user)


@router.post("/auth/login")
def login(payload: LoginRequest) -> dict:
    record = db.get_user_by_email(payload.email)
    if not record or not security.verify_password(payload.password, record["password_hash"]):
        raise HTTPException(status_code=401, detail="Incorrect email or password.")
    return _issue(record)


@router.get("/auth/me")
def me(user: dict = Depends(current_user)) -> dict:  # type: ignore[assignment]
    return {"user": _public_user(user)}


@router.post("/auth/logout")
def logout(authorization: str | None = Header(default=None)) -> dict:
    if authorization and authorization.lower().startswith("bearer "):
        db.revoke_token(authorization.split(" ", 1)[1].strip())
    return {"ok": True}


# ------------------------------------------------------------------ chat sessions


@router.get("/sessions")
def list_sessions(user: dict = Depends(request_owner)) -> dict:  # type: ignore[assignment]
    return {"sessions": db.list_sessions(user["id"])}


@router.post("/sessions")
def create_session(payload: SessionCreate, user: dict = Depends(request_owner)) -> dict:  # type: ignore[assignment]
    return db.create_session(user["id"], payload.title)


@router.get("/sessions/{session_id}")
def get_session(session_id: str, user: dict = Depends(request_owner)) -> dict:  # type: ignore[assignment]
    session = db.get_session(user["id"], session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return session


@router.patch("/sessions/{session_id}")
def rename_session(session_id: str, payload: SessionRename, user: dict = Depends(request_owner)) -> dict:  # type: ignore[assignment]
    if not db.rename_session(user["id"], session_id, payload.title):
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return {"ok": True}


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str, user: dict = Depends(request_owner)) -> dict:  # type: ignore[assignment]
    if not db.delete_session(user["id"], session_id):
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return {"ok": True}
