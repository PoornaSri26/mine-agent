"""Account and conversation-history API.

The committed React app gates every screen behind `/auth/*` and manages chats
through `/sessions`, but the repository's FastAPI service never implemented
them. These routes close that gap and are what keep the deployed demo usable.
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

import db
import security

router = APIRouter(tags=["auth"])

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")


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
def list_sessions(user: dict = Depends(current_user)) -> dict:  # type: ignore[assignment]
    return {"sessions": db.list_sessions(user["id"])}


@router.post("/sessions")
def create_session(payload: SessionCreate, user: dict = Depends(current_user)) -> dict:  # type: ignore[assignment]
    return db.create_session(user["id"], payload.title)


@router.get("/sessions/{session_id}")
def get_session(session_id: str, user: dict = Depends(current_user)) -> dict:  # type: ignore[assignment]
    session = db.get_session(user["id"], session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return session


@router.patch("/sessions/{session_id}")
def rename_session(session_id: str, payload: SessionRename, user: dict = Depends(current_user)) -> dict:  # type: ignore[assignment]
    if not db.rename_session(user["id"], session_id, payload.title):
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return {"ok": True}


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str, user: dict = Depends(current_user)) -> dict:  # type: ignore[assignment]
    if not db.delete_session(user["id"], session_id):
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return {"ok": True}
