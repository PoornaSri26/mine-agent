"""Shared state for the multi-agent graph.

Every agent reads and writes the same typed state (a blackboard). `trace` uses
an additive reducer, so each node appends its own event without clobbering the
others and the API can return a full run trace to the frontend.
"""

from __future__ import annotations

import time
from operator import add
from typing import Annotated, Any, TypedDict


class Document(TypedDict, total=False):
    text: str
    source: str
    page: int
    score: float


class AgentState(TypedDict, total=False):
    question: str
    history: list[dict[str, str]]
    rewritten: str
    intent: str
    tasks: list[dict[str, str]]
    queries: list[str]
    documents: list[Document]
    coverage: float
    retrieval_note: str
    hazard: dict[str, Any]
    compliance: dict[str, Any]
    critique: dict[str, Any]
    rounds: int
    answer: str
    citations: list[dict[str, Any]]
    confidence: float
    trace: Annotated[list[dict[str, Any]], add]


def event(
    agent: str,
    name: str,
    role: str,
    started: float,
    summary: str,
    status: str = "done",
    bullets: list[str] | None = None,
) -> dict[str, Any]:
    """Build one trace entry for the UI (`ms` is measured, never guessed)."""
    entry: dict[str, Any] = {
        "id": f"{agent}-{int(started * 1000)}",
        "agent": agent,
        "name": name,
        "role": role,
        "status": status,
        "ms": int((time.perf_counter() - started) * 1000),
        "summary": summary,
    }
    if bullets:
        entry["bullets"] = bullets[:6]
    return entry
