"""MineRakshak API — a supervisor-led team of mine-safety agents.

Existing endpoints keep their contract (`/query`, `/updates`,
`/audit_report_pdf`) and now return an agent trace alongside the answer.
`/agents` exposes the roster the frontend renders.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Any

import requests
from bs4 import BeautifulSoup
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

import config
import db
from agents import AGENTS, PIPELINE, hazards, run_pipeline
from agents.llm import llm
from agents.nodes import triage_bulletin
from agents.retrieval import VectorStore, warmup
from auth import request_owner
from auth import router as auth_router
from report_pdf import build_report_pdf
from rss_feed import fetch_dgms_updates

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("minerakshak.api")

UPDATES_TTL_SECONDS = int(os.getenv("UPDATES_TTL_SECONDS", "600"))
_updates_cache: dict[str, Any] = {"at": 0.0, "payload": None}


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    logger.info(
        "MineRakshak ready · llm=%s · model=%s · db=%s",
        "gemini" if llm.available else "offline",
        config.GEMINI_MODEL,
        config.DB_PATH,
    )
    if os.getenv("ENABLE_WARMUP", "0").lower() in {"1", "true", "yes"}:
        await asyncio.to_thread(warmup)
    yield


app = FastAPI(
    title="MineRakshak — Multi-Agent Mine Safety Service",
    description="Supervisor, research, analysis, compliance, report and critic agents over DGMS mining records.",
    version="2.0.0",
    lifespan=lifespan,
)

_origins = ["*"] if "*" in config.ALLOWED_ORIGINS else config.ALLOWED_ORIGINS
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router)


@app.get("/")
def root() -> dict[str, Any]:
    return {
        "message": "MineRakshak multi-agent service is running.",
        "agents": [agent["name"] for agent in AGENTS],
        "docs": "/docs",
    }


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "llm": {"enabled": llm.available, "model": config.GEMINI_MODEL, "mode": config.LLM_MODE},
        "retrieval": VectorStore.instance().status(),
        "database": str(config.DB_PATH),
    }


@app.get("/agents")
def agents() -> dict[str, Any]:
    return {
        "agents": AGENTS,
        "pipeline": PIPELINE,
        "llm": {"enabled": llm.available, "model": config.GEMINI_MODEL, "mode": config.LLM_MODE},
    }


# ------------------------------------------------------------------------- chat


@app.post("/query")
async def query_agent(request: Request, user: dict = Depends(request_owner)) -> dict[str, Any]:
    try:
        data = await request.json()
    except Exception:
        data = {}

    query = str(data.get("query") or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="Ask a mining-safety question first.")
    if len(query) > 2000:
        raise HTTPException(status_code=400, detail="Question is too long (2000 characters max).")

    session_id = data.get("session_id")
    if session_id:
        session = db.get_session(user["id"], str(session_id))
        if not session:
            raise HTTPException(status_code=404, detail="Conversation not found.")
        session_id = session["id"]
    else:
        session_id = db.create_session(user["id"], query[:60])["session_id"]

    history = db.recent_messages(session_id, 6)
    db.append_message(session_id, "user", query)

    started = time.perf_counter()
    try:
        result = await asyncio.to_thread(run_pipeline, query, history)
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Agent pipeline failed")
        raise HTTPException(status_code=500, detail="The agent team could not complete this request.") from exc

    db.append_message(session_id, "assistant", result["answer"], result["trace"])
    logger.info("Query served in %.1fs with %d agent steps", time.perf_counter() - started, len(result["trace"]))

    return {"response": result["answer"], "session_id": session_id, **result}


# ----------------------------------------------------------------------- updates


def _article_summary(link: str) -> str:
    if not link:
        return ""
    try:
        response = requests.get(link, timeout=8, headers={"User-Agent": "Mozilla/5.0 (MineRakshakBot)"})
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        paragraphs = [node.get_text(" ", strip=True) for node in soup.find_all("p")]
        return " ".join(paragraphs[:5])[:1500]
    except Exception:
        return ""


@app.get("/updates")
async def get_updates() -> dict[str, Any]:
    now = time.time()
    if _updates_cache["payload"] and now - _updates_cache["at"] < UPDATES_TTL_SECONDS:
        return _updates_cache["payload"]

    items = await asyncio.to_thread(fetch_dgms_updates, 5)
    items = [item for item in items if item.get("title") and item.get("title") != "No updates available"]

    async def analyze(item: dict[str, Any]) -> dict[str, Any]:
        summary = await asyncio.to_thread(_article_summary, item.get("link", ""))
        hazard = await asyncio.to_thread(triage_bulletin, item.get("title", ""), summary)
        return {
            "title": item.get("title", "Untitled bulletin"),
            "link": item.get("link", ""),
            "snapshot": bool(item.get("snapshot")),
            "published": item.get("published", ""),
            "danger_analysis": hazards.analysis_markdown(hazard),
            "risk_level": hazard.get("severity", "Low"),
            "hazard_type": hazard.get("label", ""),
            "confidence": hazard.get("confidence", 0.4),
        }

    analyzed = await asyncio.gather(*(analyze(item) for item in items)) if items else []
    message = ""
    if not analyzed:
        message = "No live bulletins could be fetched right now. Try again shortly."
    elif all(item.get("snapshot") for item in analyzed):
        message = "Live feeds are unreachable from the server - showing the bundled bulletin snapshot."
    payload = {
        "updates": list(analyzed),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "analyst": "Analysis agent",
        "message": message,
    }
    _updates_cache.update({"at": now, "payload": payload})
    return payload


# ------------------------------------------------------------------- audit report


def _safe_filename(value: str) -> str:
    cleaned = "".join(character if character.isalnum() or character in "-_" else "_" for character in value)
    return cleaned.strip("_")[:60] or "Mining_Safety"


@app.post("/audit_report_pdf")
async def audit_report_pdf(request: Request, user: dict = Depends(request_owner)) -> Response:  # noqa: ARG001
    try:
        data = await request.json()
    except Exception:
        data = {}

    state = str(data.get("state") or "All States")[:80]
    year = str(data.get("year") or "All Years")[:10]
    hazard_type = str(data.get("hazard_type") or "All Hazards")[:80]

    question = (
        f"Prepare a mining safety audit briefing for {state}, fiscal year {year}, hazard focus: {hazard_type}. "
        "Summarise the incident picture in the evidence, the dominant hazard category, severity, likely root "
        "causes, recommended controls and statutory checks that must be verified."
    )

    result = await asyncio.to_thread(run_pipeline, question, [])
    body = result["answer"]
    agent_lines = "\n".join(f"- {step['name']} ({step['role']}): {step['summary']}" for step in result["trace"])
    body = f"{body}\n\n**Agent run**\n{agent_lines}"

    pdf_bytes = await asyncio.to_thread(
        build_report_pdf,
        "Mining Safety Audit Briefing",
        {
            "State / Region": state,
            "Fiscal year": year,
            "Hazard focus": hazard_type,
            "Prepared by": "MineRakshak agent team",
            "Confidence": f"{result['confidence']:.2f}",
        },
        body,
    )

    filename = f"Audit_Report_{_safe_filename(state)}_{_safe_filename(year)}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
