"""Agent-graph tests that never touch the network or the heavy models."""

from __future__ import annotations

from typing import Any

import pytest

from agents import hazards
from agents.graph import run_pipeline
from agents.nodes import triage_bulletin

METHANE_DOC = {
    "text": (
        "Methane explosion at a coal working caused fatal injuries to four persons. "
        "Investigations attributed the explosion to inadequate ventilation and an accumulation "
        "of firedamp, with withdrawal limits not enforced before the blast."
    ),
    "source": "VOLUME_II_NON_COAL_2015-FULL.pdf",
    "page": 42,
    "score": 0.83,
}

ROOF_DOC = {
    "text": (
        "Fall of roof in an underground metalliferous mine killed two workers when unsupported "
        "strata collapsed at the face. The support plan had not been revised after the fault zone "
        "was intersected."
    ),
    "source": "VOLUME_II_NON_COAL_2015-FULL.pdf",
    "page": 91,
    "score": 0.77,
}


class FakeStore:
    """Stands in for FAISS so the graph logic is tested deterministically."""

    def __init__(self, batches: list[list[dict[str, Any]]]) -> None:
        self.batches = list(batches)
        self.calls = 0

    def search(self, query: str, k: int | None = None, fetch_k: int = 14) -> dict[str, Any]:
        self.calls += 1
        documents = self.batches.pop(0) if self.batches else []
        return {"documents": documents, "coverage": 0.8 if documents else 0.0, "top_score": 0.8 if documents else 0.0}


def patch_store(monkeypatch: pytest.MonkeyPatch, batches: list[list[dict[str, Any]]]) -> FakeStore:
    fake = FakeStore(batches)

    class StoreProxy:
        @classmethod
        def instance(cls) -> FakeStore:
            return fake

    monkeypatch.setattr("agents.nodes.VectorStore", StoreProxy)
    return fake


def test_pipeline_runs_every_agent_in_order(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_store(monkeypatch, [[METHANE_DOC]])

    result = run_pipeline("What causes methane explosions and how are they prevented?")

    assert [step["agent"] for step in result["trace"]] == [
        "supervisor",
        "research",
        "analysis",
        "compliance",
        "report",
        "critic",
    ]
    assert result["hazard"]["id"] == "methane"
    assert result["hazard"]["severity"] == "High"
    assert result["evidence"], "evidence must be carried into the response"
    assert "Methane" in result["answer"]
    assert result["confidence"] > 0.3
    assert all(step["ms"] >= 0 for step in result["trace"])


class FakeLLM:
    """Exercises the Gemini path without a key or any network call."""

    available = True

    def json(self, prompt: str, system: str | None = None, temperature: float = 0.1):
        text = (system or "").lower()
        if "supervisor" in text:
            return {
                "intent": "incident",
                "rewritten_query": "roof fall accidents support",
                "tasks": [{"agent": "research", "reason": "find evidence"}],
                "hazard_hint": "roof-fall",
            }
        if "hazard analyst" in text:
            return {
                "hazard_id": "roof-fall",
                "severity": "High",
                "confidence": 0.82,
                "key_findings": ["Unsupported spans caused the collapse"],
                "incident_signals": ["two workers killed"],
                "drivers": ["No support plan after intersecting the fault"],
            }
        return {
            "checks": [
                {"clause": "Support of ground", "requirement": "Written support plan", "status": "gap", "note": "None found"}
            ],
            "recommendations": ["Install systematic support before re-entry"],
            "gaps": 1,
        }

    def text(self, prompt: str, system: str | None = None, temperature: float = 0.25) -> str:
        return "**Assessment.** Model-written narrative citing p. 91."


def test_model_path_wires_through_every_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_store(monkeypatch, [[ROOF_DOC]])
    monkeypatch.setattr("agents.nodes.llm", FakeLLM())

    result = run_pipeline("What caused the roof fall?")

    assert result["hazard"]["id"] == "roof-fall"
    assert result["hazard"]["severity"] == "High"
    assert result["hazard"]["confidence"] == 0.82
    assert result["compliance"]["gaps"] == 1
    assert result["compliance"]["checks"][0]["status"] == "gap"
    assert "Model-written narrative" in result["answer"]
    assert result["evidence"], "citations must still be attached to model output"


def test_critic_triggers_second_research_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = patch_store(monkeypatch, [[], [ROOF_DOC]])

    result = run_pipeline("What caused the roof fall fatalities?")

    agents_run = [step["agent"] for step in result["trace"]]
    assert agents_run.count("research") == 2, "weak evidence must send the run back to research"
    assert fake.calls >= 2
    assert result["critique"]["coverage"] > 0
    assert result["hazard"]["id"] == "roof-fall"


def test_answer_reports_missing_evidence_without_inventing(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_store(monkeypatch, [[], []])

    result = run_pipeline("List 2024 accident statistics for coal mines")

    assert "No matching page was retrieved" in result["answer"]
    assert result["evidence"] == []
    assert result["confidence"] <= 0.5
    assert result["critique"]["grounded"] is False


def test_hazard_taxonomy_and_alert_markdown() -> None:
    hazard = hazards.classify("roof fall and strata collapse in the stope", [])

    assert hazard["id"] == "roof-fall"
    assert hazard["severity"] in {"High", "Medium", "Low"}
    markdown = hazards.analysis_markdown(hazard)
    assert markdown.startswith("**Risk Level:**")
    assert "**Hazard Type:**" in markdown
    assert "**Description:**" in markdown


def test_general_question_does_not_get_a_hazard_label_from_evidence_noise() -> None:
    documents = [
        {
            "text": "Other non-transportation machinery 0993 Drowning in water 0994 Buried in sands "
                    "0995 Bursting/leakage of oil pipe lines 0999 Unclassified",
            "page": 91,
            "source": "vol2.pdf",
            "score": 0.6,
        }
    ]

    hazard = hazards.classify("What do the DGMS records show about fatal accidents in non-coal mines?", documents)

    assert hazard["id"] == "general", "evidence-only keyword noise must not pick a hazard"
    assert hazard["severity"] == "High", "fatalities in the evidence keep the severity high"


def test_index_built_with_another_model_is_rejected(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    import agents.retrieval as retrieval

    meta = tmp_path / "index_meta.json"
    meta.write_text('{"embed_model": "sentence-transformers/all-MiniLM-L6-v2", "dimensions": 384}', encoding="utf-8")
    monkeypatch.setattr(retrieval, "INDEX_META_PATH", meta)

    store = retrieval.VectorStore()
    with pytest.raises(retrieval.RetrievalUnavailable, match="rebuild"):
        store.load()


def test_default_models_are_current_generations() -> None:
    import config

    assert config.GEMINI_MODEL.startswith(("gemini-3", "gemini-4")), "2.5 models are retired in Dec 2026"
    assert config.EMBED_MODEL.startswith("ibm-granite/"), "Granite R2 is the current 47M open embedding model"


def test_bulletin_triage_returns_structured_assessment() -> None:
    hazard = triage_bulletin("DGMS advisory on conveyor guarding", "A worker was entangled in an unguarded conveyor belt drive.")

    assert hazard["id"] == "machinery"
    assert hazard["controls"]
    assert 0.0 < hazard["confidence"] <= 0.95
