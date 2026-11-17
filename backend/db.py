"""SQLite persistence for users, bearer tokens, chat sessions and messages.

The original backend only cached RAG answers in SQLite, while the committed
frontend expects accounts and conversation history. Both live here behind one
locked connection; every read/write is scoped by user id.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import config
import security

_LOCK = threading.RLock()
_CONNECTION: sqlite3.Connection | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _connect() -> sqlite3.Connection:
    global _CONNECTION
    if _CONNECTION is None:
        config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(config.DB_PATH), check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        _CONNECTION = connection
    return _CONNECTION


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS auth_tokens (
    token_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    expires_at REAL NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS chat_sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    trace TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES chat_sessions (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON chat_sessions (user_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_messages_session ON chat_messages (session_id, id);
"""


def init_db() -> None:
    with _LOCK:
        connection = _connect()
        connection.executescript(SCHEMA)
        connection.commit()
        if config.SEED_DEMO:
            _seed_demo_user(connection)


def _seed_demo_user(connection: sqlite3.Connection) -> None:
    existing = connection.execute(
        "SELECT id FROM users WHERE email = ?", (config.DEMO_EMAIL.lower(),)
    ).fetchone()
    if existing:
        return
    connection.execute(
        "INSERT INTO users (id, name, email, password_hash, created_at) VALUES (?, ?, ?, ?, ?)",
        (
            str(uuid.uuid4()),
            config.DEMO_NAME,
            config.DEMO_EMAIL.lower(),
            security.hash_password(config.DEMO_PASSWORD),
            _now(),
        ),
    )
    connection.commit()


# --------------------------------------------------------------------------- users


def create_user(name: str, email: str, password: str) -> dict[str, Any]:
    with _LOCK:
        connection = _connect()
        user = {
            "id": str(uuid.uuid4()),
            "name": name.strip(),
            "email": email.strip().lower(),
            "password_hash": security.hash_password(password),
            "created_at": _now(),
        }
        connection.execute(
            "INSERT INTO users (id, name, email, password_hash, created_at) VALUES (?, ?, ?, ?, ?)",
            (user["id"], user["name"], user["email"], user["password_hash"], user["created_at"]),
        )
        connection.commit()
        return {"id": user["id"], "name": user["name"], "email": user["email"]}


def get_user_by_email(email: str) -> dict[str, Any] | None:
    with _LOCK:
        row = _connect().execute(
            "SELECT * FROM users WHERE email = ?", (email.strip().lower(),)
        ).fetchone()
        return dict(row) if row else None


def get_user(user_id: str) -> dict[str, Any] | None:
    with _LOCK:
        row = _connect().execute("SELECT id, name, email FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None


def ensure_guest(guest_id: str) -> dict[str, Any]:
    """Return the local owner row for a browser's guest id, creating it once.

    Guests are ordinary rows in `users` with an id prefixed `guest:` so a guest id
    can never collide with an account id. They have no usable password and exist
    only to own conversations until sign-in is added back.
    """
    owner_id = f"guest:{guest_id}"
    with _LOCK:
        connection = _connect()
        row = connection.execute(
            "SELECT id, name, email FROM users WHERE id = ?", (owner_id,)
        ).fetchone()
        if row:
            return dict(row)
        email = f"guest-{guest_id}@guest.local"
        connection.execute(
            "INSERT INTO users (id, name, email, password_hash, created_at) VALUES (?, ?, ?, ?, ?)",
            (owner_id, "Guest reviewer", email, "!", _now()),
        )
        connection.commit()
        return {"id": owner_id, "name": "Guest reviewer", "email": email}


# --------------------------------------------------------------------------- tokens


def issue_token(user_id: str) -> str:
    token = security.new_token()
    with _LOCK:
        connection = _connect()
        connection.execute(
            "INSERT INTO auth_tokens (token_hash, user_id, expires_at, created_at) VALUES (?, ?, ?, ?)",
            (
                security.token_digest(token),
                user_id,
                time.time() + config.TOKEN_TTL_DAYS * 86400,
                _now(),
            ),
        )
        connection.commit()
    return token


def user_id_for_token(token: str) -> str | None:
    with _LOCK:
        row = _connect().execute(
            "SELECT user_id, expires_at FROM auth_tokens WHERE token_hash = ?",
            (security.token_digest(token),),
        ).fetchone()
        if not row:
            return None
        if row["expires_at"] < time.time():
            _connect().execute(
                "DELETE FROM auth_tokens WHERE token_hash = ?", (security.token_digest(token),)
            )
            _connect().commit()
            return None
        return str(row["user_id"])


def revoke_token(token: str) -> None:
    with _LOCK:
        connection = _connect()
        connection.execute("DELETE FROM auth_tokens WHERE token_hash = ?", (security.token_digest(token),))
        connection.commit()


# --------------------------------------------------------------------------- sessions


def create_session(user_id: str, title: str = "New chat") -> dict[str, Any]:
    session = {"id": str(uuid.uuid4()), "title": (title or "New chat")[:120], "created_at": _now()}
    with _LOCK:
        connection = _connect()
        connection.execute(
            "INSERT INTO chat_sessions (id, user_id, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (session["id"], user_id, session["title"], session["created_at"], session["created_at"]),
        )
        connection.commit()
    return {"session_id": session["id"], "title": session["title"]}


def list_sessions(user_id: str) -> list[dict[str, Any]]:
    with _LOCK:
        rows = _connect().execute(
            """
            SELECT s.id, s.title, s.created_at, s.updated_at,
                   (SELECT COUNT(*) FROM chat_messages m WHERE m.session_id = s.id) AS message_count
            FROM chat_sessions s
            WHERE s.user_id = ?
            ORDER BY s.updated_at DESC
            """,
            (user_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def get_session(user_id: str, session_id: str) -> dict[str, Any] | None:
    with _LOCK:
        connection = _connect()
        session = connection.execute(
            "SELECT id, title, updated_at FROM chat_sessions WHERE id = ? AND user_id = ?",
            (session_id, user_id),
        ).fetchone()
        if not session:
            return None
        rows = connection.execute(
            "SELECT role, content, trace, created_at FROM chat_messages WHERE session_id = ? ORDER BY id",
            (session_id,),
        ).fetchall()
        messages = []
        for row in rows:
            trace = None
            if row["trace"]:
                try:
                    trace = json.loads(row["trace"])
                except json.JSONDecodeError:
                    trace = None
            messages.append(
                {
                    "role": row["role"],
                    "content": row["content"],
                    "created_at": row["created_at"],
                    "trace": trace,
                }
            )
        return {
            "id": session["id"],
            "title": session["title"],
            "updated_at": session["updated_at"],
            "messages": messages,
        }


def rename_session(user_id: str, session_id: str, title: str) -> bool:
    with _LOCK:
        connection = _connect()
        cursor = connection.execute(
            "UPDATE chat_sessions SET title = ?, updated_at = ? WHERE id = ? AND user_id = ?",
            (title.strip()[:120], _now(), session_id, user_id),
        )
        connection.commit()
        return cursor.rowcount > 0


def delete_session(user_id: str, session_id: str) -> bool:
    with _LOCK:
        connection = _connect()
        cursor = connection.execute(
            "DELETE FROM chat_sessions WHERE id = ? AND user_id = ?", (session_id, user_id)
        )
        connection.commit()
        return cursor.rowcount > 0


def append_message(session_id: str, role: str, content: str, trace: list[dict] | None = None) -> None:
    with _LOCK:
        connection = _connect()
        connection.execute(
            "INSERT INTO chat_messages (session_id, role, content, trace, created_at) VALUES (?, ?, ?, ?, ?)",
            (
                session_id,
                role,
                content,
                json.dumps(trace, ensure_ascii=False) if trace else None,
                _now(),
            ),
        )
        connection.execute(
            "UPDATE chat_sessions SET updated_at = ? WHERE id = ?", (_now(), session_id)
        )
        connection.commit()


def recent_messages(session_id: str, limit: int = 6) -> list[dict[str, str]]:
    with _LOCK:
        rows = _connect().execute(
            "SELECT role, content FROM chat_messages WHERE session_id = ? ORDER BY id DESC LIMIT ?",
            (session_id, limit),
        ).fetchall()
        return [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]


def autotitle_session(session_id: str, first_message: str) -> None:
    """Give new sessions a short, human-readable title from the first question."""
    title = " ".join(first_message.split())[:60] or "New chat"
    with _LOCK:
        connection = _connect()
        row = connection.execute(
            "SELECT COUNT(*) AS total FROM chat_messages WHERE session_id = ?", (session_id,)
        ).fetchone()
        if row and row["total"] <= 1:
            connection.execute(
                "UPDATE chat_sessions SET title = ? WHERE id = ?", (title, session_id)
            )
            connection.commit()
