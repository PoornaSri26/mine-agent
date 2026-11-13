"""The audit report must come back as a real PDF, not plain text."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

import main
from report_pdf import build_report_pdf

BODY = """**Assessment.** Roof fall at High severity (p. 91).

**Recommended controls**
1. Systematic roof bolting to a written support plan
2. Pre-shift examination of roof and sides

**Statutory checks to verify**
- Support of ground: written support plan for every working place
"""


def test_pdf_renderer_outputs_pdf_bytes() -> None:
    pdf = build_report_pdf("Mining Safety Audit Briefing", {"State / Region": "Jharkhand", "Fiscal year": "2015"}, BODY)
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 1200


def test_audit_endpoint_returns_attachment(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    stub: dict[str, Any] = {
        "answer": BODY,
        "confidence": 0.7,
        "trace": [{"id": "report-1", "agent": "report", "name": "Report", "role": "Writer", "status": "done", "ms": 9, "summary": "Drafted."}],
    }
    monkeypatch.setattr(main, "run_pipeline", lambda question, history: stub)
    token = client.post("/auth/login", json={"email": "demo@test.local", "password": "demo1234"}).json()["token"]

    response = client.post(
        "/audit_report_pdf",
        json={"state": "Jharkhand", "year": "2015", "hazard_type": "Roof fall"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    assert "Audit_Report_Jharkhand_2015.pdf" in response.headers["content-disposition"]
    assert response.content.startswith(b"%PDF")
