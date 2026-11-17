"""API contract tests for the deployed frontend's expectations.

The app has no sign-in for this review build, so the important contract is that
`/query` and `/sessions` work for an anonymous browser and stay separated per
guest. The account routes are still covered because they come back later.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

import main

STUB_RESULT: dict[str, Any] = {
    "answer": "**Assessment.** Methane ignition at High severity (p. 42).",
    "confidence": 0.74,
    "intent": "knowledge",
    "trace": [
        {"id": "supervisor-1", "agent": "supervisor", "name": "Supervisor", "role": "Coordinator",
         "status": "done", "ms": 3, "summary": "Intent: knowledge."},
        {"id": "research-2", "agent": "research", "name": "Research", "role": "Evidence gatherer",
         "status": "done", "ms": 12, "summary": "1 passage."},
    ],
    "evidence": [{"page": 42, "source": "vol2.pdf", "score": 0.8, "excerpt": "methane"}],
    "hazard": {"id": "methane", "label": "Methane", "severity": "High"},
    "compliance": {"checks": [], "recommendations": [], "gaps": 0},
    "critique": {"grounded": True, "coverage": 0.8, "confidence": 0.74, "issues": [], "request_replan": False},
    "plan": {"intent": "knowledge", "rewritten": "methane", "tasks": [], "rounds": 1},
}

GUEST_A = {"X-Guest-Id": "reviewer-aaaa1111"}
GUEST_B = {"X-Guest-Id": "reviewer-bbbb2222"}


def _login(client: TestClient, email: str = "demo@test.local", password: str = "demo1234") -> str:
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["token"]


def test_health_and_roster(client: TestClient) -> None:
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    roster = client.get("/agents").json()
    assert len(roster["agents"]) == 6
    assert roster["pipeline"][0] == "Supervisor"
    assert {agent["id"] for agent in roster["agents"]} == {
        "supervisor", "research", "analysis", "compliance", "report", "critic"
    }


def test_auth_endpoints_still_available_for_later(client: TestClient) -> None:
    created = client.post(
        "/auth/register",
        json={"name": "Asha Verma", "email": "asha@test.local", "password": "strongpass123"},
    )
    assert created.status_code == 200, created.text
    token = created.json()["token"]

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["user"]["email"] == "asha@test.local"

    assert client.post("/auth/login", json={"email": "asha@test.local", "password": "wrong"}).status_code == 401
    assert client.get("/auth/me", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_query_is_served_without_login(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "run_pipeline", lambda question, history: STUB_RESULT)

    response = client.post("/query", json={"query": "What causes methane explosions?"}, headers=GUEST_A)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["session_id"]
    assert payload["trace"][0]["agent"] == "supervisor"
    assert payload["confidence"] == 0.74


def test_guest_conversations_are_isolated(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "run_pipeline", lambda question, history: STUB_RESULT)
    mine = client.post("/query", json={"query": "Roof fall precautions"}, headers=GUEST_A).json()

    own = client.get("/sessions", headers=GUEST_A).json()["sessions"]
    other = client.get("/sessions", headers=GUEST_B).json()["sessions"]

    assert any(session["id"] == mine["session_id"] for session in own)
    assert all(session["id"] != mine["session_id"] for session in other)
    assert client.get(f"/sessions/{mine['session_id']}", headers=GUEST_B).status_code == 404


def test_query_persists_session_with_agent_trace(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "run_pipeline", lambda question, history: STUB_RESULT)

    created = client.post("/sessions", json={"title": "Methane review"}, headers=GUEST_A)
    assert created.status_code == 200
    session_id = created.json()["session_id"]

    response = client.post(
        "/query", json={"query": "What causes methane explosions?", "session_id": session_id}, headers=GUEST_A
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["session_id"] == session_id
    assert payload["trace"][0]["agent"] == "supervisor"
    assert payload["confidence"] == 0.74
    assert payload["intent"] == "knowledge"

    stored = client.get(f"/sessions/{session_id}", headers=GUEST_A).json()
    assert [message["role"] for message in stored["messages"]] == ["user", "assistant"]
    assert stored["messages"][1]["trace"][0]["name"] == "Supervisor"

    listed = client.get("/sessions", headers=GUEST_A).json()["sessions"]
    assert listed[0]["message_count"] == 2

    assert client.delete(f"/sessions/{session_id}", headers=GUEST_A).json() == {"ok": True}


def test_query_creates_session_when_missing(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "run_pipeline", lambda question, history: STUB_RESULT)

    payload = client.post("/query", json={"query": "Roof fall precautions"}, headers=GUEST_A).json()
    assert payload["session_id"]
    assert payload["response"].startswith("**Assessment.**")


def test_updates_contract(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "fetch_dgms_updates", lambda limit=5: [{"title": "Conveyor safety advisory", "link": "", "published": "2026-01-05"}])
    monkeypatch.setattr(main, "triage_bulletin", lambda title, summary: {
        "id": "machinery", "label": "Machinery, haulage and transport", "severity": "Medium",
        "confidence": 0.5, "drivers": ["Unguarded conveyor"], "controls": ["Lock-out before unblocking"],
    })
    main._updates_cache.update({"at": 0.0, "payload": None})

    payload = client.get("/updates").json()
    assert payload["updates"][0]["danger_analysis"].startswith("**Risk Level:**")
    assert payload["updates"][0]["risk_level"] == "Medium"
