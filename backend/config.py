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
# Free-tier capacity is per model: the newest Flash can answer 503 UNAVAILABLE
# while an older stable Flash still serves. These are tried in order after
# GEMINI_MODEL, so a saturated model never drops the graph to templates.
GEMINI_FALLBACK_MODELS = [
    name.strip()
    for name in os.getenv(
        "GEMINI_FALLBACK_MODELS", "gemini-3.7-flash,gemini-3.6-flash"
    ).split(",")
    if name.strip()
]

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

# Agent calls are structured extraction, not long-form reasoning: "low" thinking
# keeps a four-call pipeline inside the 60 s cap the Vercel proxy enforces on the
# Hobby plan. Set GEMINI_THINKING_LEVEL="" to send no thinking config at all.
GEMINI_THINKING_LEVEL = os.getenv("GEMINI_THINKING_LEVEL", "low").strip().lower()
# Per-call ceiling, in seconds. Free-tier capacity failures arrive as 503/504;
# a short timeout with a single SDK attempt lets the next model answer instead
# of burning the request budget retrying a saturated one.
GEMINI_TIMEOUT_S = float(os.getenv("GEMINI_TIMEOUT_S", "15"))

# The specialist roster is fixed and the intent rules already cover the requests
# this service receives, so the Supervisor plans deterministically and the model
# is spent on evidence work instead. AGENT_SUPERVISOR_LLM=1 restores the model.
SUPERVISOR_LLM = os.getenv("AGENT_SUPERVISOR_LLM", "0") not in {"0", "false", "False"}
# Bulletin triage is a taxonomy lookup the deterministic classifier answers; a
# model call per bulletin cost five of the twenty free-tier requests every cache
# refresh. AGENT_BULLETIN_LLM=1 restores it.
BULLETIN_LLM = os.getenv("AGENT_BULLETIN_LLM", "0") not in {"0", "false", "False"}

DB_PATH = pathlib.Path(os.getenv("DB_PATH", str(BASE_DIR / "data" / "minerakshak.db")))
MAX_AGENT_ROUNDS = int(os.getenv("AGENT_MAX_ROUNDS", "2"))
RETRIEVAL_TOP_K = int(os.getenv("RETRIEVAL_TOP_K", "5"))
ENABLE_RERANK = os.getenv("ENABLE_RERANK", "0") not in {"0", "false", "False"}

# Embedding backend. "onnx" runs the same Granite weights through ONNX Runtime
# (~350 MB process) instead of PyTorch + sentence-transformers (~750 MB), which
# is what lets the API fit a 512 MB free instance; "torch" is the reference path
# used to build the index. The ONNX export is pinned to a reviewed revision:
# its vectors match the torch encoder exactly (cosine 1.000000).
EMBED_BACKEND = os.getenv("EMBED_BACKEND", "onnx").strip().lower()
EMBED_ONNX_REPO = os.getenv(
    "EMBED_ONNX_REPO", "keisuke-miyako/granite-embedding-small-english-r2-onnx-fp32"
)
EMBED_ONNX_FILE = os.getenv("EMBED_ONNX_FILE", "model.onnx")
EMBED_ONNX_REVISION = os.getenv("EMBED_ONNX_REVISION", "5f8b507347bf281bcaceefcc51ae5435a31fbbdd")

# Free hosts give a fraction of a core; extra threads cost memory arenas
# without buying throughput.
TORCH_THREADS = int(os.getenv("TORCH_THREADS", "1"))

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


def gemini_models() -> list[str]:
    """Ordered model candidates: the configured model, then free-tier backups."""
    ordered: list[str] = []
    for name in [GEMINI_MODEL, *GEMINI_FALLBACK_MODELS]:
        if name and name not in ordered:
            ordered.append(name)
    return ordered
