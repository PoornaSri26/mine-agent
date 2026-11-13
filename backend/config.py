"""Runtime configuration for the MineRakshak agent service.

Environment variables are read once at import time. Nothing here should be
committed with real secrets; `.env` is git-ignored and documented in
`.env.example`.
"""

from __future__ import annotations

import os
import pathlib

from dotenv import load_dotenv

BASE_DIR = pathlib.Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# Gemini is the reasoning engine for every agent. Either name is accepted
# because the repository historically used GOOGLE_API_KEY.
GOOGLE_API_KEY = (os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY") or "").strip()
# gemini-3.8-flash is the current stable Flash model (2.5 is retired Dec 2026).
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

# Retrieval models. Granite Embedding R2 (Aug 2025, Apache-2.0) is the current
# 47M/384-dim release: it beats the older bge/e5 small models on MTEB-v2 while
# indexing this corpus in seconds on a CPU host.
EMBED_MODEL = os.getenv("EMBED_MODEL", "ibm-granite/granite-embedding-small-english-r2")
# Optional cross-encoder reranker. Off by default: a 0.6B reranker costs ~1 min
# per query on free CPU hosting, so quality comes from the embedder + coverage.
RERANK_MODEL = os.getenv("RERANK_MODEL", "Alibaba-NLP/gte-reranker-modernbert-base")

# auto   -> use Gemini when a key exists, otherwise run the deterministic graph
# gemini -> require Gemini (raises if the key is missing)
# offline-> never call the network (used by tests and demos without a key)
LLM_MODE = os.getenv("AGENT_LLM_MODE", "auto").strip().lower()

DB_PATH = pathlib.Path(os.getenv("DB_PATH", str(BASE_DIR / "data" / "minerakshak.db")))
MAX_AGENT_ROUNDS = int(os.getenv("AGENT_MAX_ROUNDS", "2"))
RETRIEVAL_TOP_K = int(os.getenv("RETRIEVAL_TOP_K", "5"))
ENABLE_RERANK = os.getenv("ENABLE_RERANK", "0") not in {"0", "false", "False"}

ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if origin.strip()
]

TOKEN_TTL_DAYS = int(os.getenv("TOKEN_TTL_DAYS", "30"))

# Optional: seeds a ready-to-use demo login on first boot (documented in README).
DEMO_EMAIL = os.getenv("DEMO_EMAIL", "demo@minerakshak.app")
DEMO_PASSWORD = os.getenv("DEMO_PASSWORD", "demo1234")
DEMO_NAME = os.getenv("DEMO_NAME", "Demo Safety Officer")
SEED_DEMO = os.getenv("SEED_DEMO", "1") not in {"0", "false", "False"}


def llm_enabled() -> bool:
    """Whether the agents may call Gemini for this process."""
    if LLM_MODE == "offline":
        return False
    if LLM_MODE == "gemini":
        return bool(GOOGLE_API_KEY)
    return bool(GOOGLE_API_KEY)
