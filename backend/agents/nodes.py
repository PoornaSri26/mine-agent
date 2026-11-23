"""The six agents as LangGraph nodes.

Each node reads the shared state, does one job, appends a trace event and
returns only the keys it owns. When Gemini is unavailable every node still
produces a grounded, explainable result (the offline path is what the tests
exercise), so the deployment never dies because of one provider hiccup.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any

import config
from agents import hazards, prompts
from agents.llm import llm
from agents.retrieval import RetrievalUnavailable, VectorStore
from agents.retrieval import coverage as coverage_ratio
from agents.state import AgentState, Document, event

logger = logging.getLogger("minerakshak.agents")

COMPLIANCE_SIGNALS = ("regulation", "regulations", "statutory", "compliance", "act", "clause", "legal")
INCIDENT_SIGNALS = ("accident", "incident", "fatalit", "death", "injury", "collapsed", "explosion", "killed")
AUDIT_SIGNALS = ("audit", "report", "inspection", "assessment")

VALID_INTENTS = {"knowledge", "incident", "compliance", "audit"}


def _intent(question: str) -> str:
    text = question.lower()
    if any(signal in text for signal in COMPLIANCE_SIGNALS):
        return "compliance"
    if any(signal in text for signal in AUDIT_SIGNALS):
        return "audit"
    if any(signal in text for signal in INCIDENT_SIGNALS):
        return "incident"
    return "knowledge"


def _snippet(text: str, limit: int = 240) -> str:
    clean = re.sub(r"\s+", " ", text).strip()
    if len(clean) <= limit:
        return clean
    cut = clean[:limit]
    if " " in cut:
        cut = cut[: cut.rfind(" ")]
    return cut + "…"


def _evidence_block(documents: list[Document], max_docs: int = 4, chars: int = 700) -> str:
    lines = []
    for doc in documents[:max_docs]:
        lines.append(f"[p. {doc.get('page', '?')}] {_snippet(doc.get('text', ''), chars)}")
    return "\n\n".join(lines)


def _dedupe(documents: list[Document]) -> list[Document]:
    seen: set[tuple[Any, str]] = set()
    unique: list[Document] = []
    for doc in documents:
        key = (doc.get("page"), doc.get("text", "")[:80])
        if key in seen:
            continue
        seen.add(key)
        unique.append(doc)
    return unique


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _requested_year(question: str) -> int | None:
    match = re.search(r"\b(19|20)\d{2}\b", question)
    return int(match.group(0)) if match else None


# --------------------------------------------------------------------- supervisor


def supervisor_node(state: AgentState) -> dict[str, Any]:
    started = time.perf_counter()
    question = (state.get("question") or "").strip()
    history = state.get("history") or []

    prior_user = next(
        (message.get("content", "") for message in reversed(history) if message.get("role") == "user"),
        "",
    )
    rewritten = question
    if len(question.split()) <= 5 and prior_user:
        # Resolve follow-ups such as "and in 2015?" against the previous turn.
        rewritten = f"{prior_user} {question}".strip()

    intent = _intent(question)
    tasks = [
        {"agent": "research", "reason": "Ground the request in DGMS records before reasoning."},
        {"agent": "analysis", "reason": "Classify the hazard and its severity drivers."},
        {"agent": "compliance", "reason": "Map findings to statutory checks and controls."},
        {"agent": "report", "reason": "Write the cited answer for the safety officer."},
        {"agent": "critic", "reason": "Verify grounding and coverage before release."},
    ]
    plan_notes: list[str] = []

    if config.SUPERVISOR_LLM and llm.available:
        payload = llm.json(
            f"Conversation so far:\n{_history_block(history)}\n\nNew request:\n{question}",
            system=prompts.SUPERVISOR_SYSTEM,
        )
        if payload:
            candidate_intent = str(payload.get("intent", "")).lower()
            if candidate_intent in VALID_INTENTS:
                intent = candidate_intent
            candidate_query = str(payload.get("rewritten_query", "")).strip()
            if 3 <= len(candidate_query) <= 300:
                rewritten = candidate_query
            raw_tasks = payload.get("tasks")
            if isinstance(raw_tasks, list) and raw_tasks:
                parsed = [
                    {"agent": str(task.get("agent", "")), "reason": str(task.get("reason", ""))[:140]}
                    for task in raw_tasks
                    if isinstance(task, dict) and str(task.get("agent", "")).lower() in {"research", "analysis", "compliance", "report"}
                ]
                if parsed:
                    tasks = parsed
            plan_notes.append("Plan produced by the Supervisor model.")

    summary = f"Intent: {intent}. Delegated {len(tasks)} tasks to specialists."
    return {
        "intent": intent,
        "tasks": tasks,
        "rewritten": rewritten,
        "queries": [rewritten],
        "rounds": 0,
        "trace": [
            event(
                "supervisor",
                "Supervisor",
                "Coordinator",
                started,
                summary,
                bullets=[f"{task['agent']}: {task['reason']}" for task in tasks] + plan_notes,
            )
        ],
    }


def _history_block(history: list[dict[str, str]]) -> str:
    recent = history[-4:]
    return "\n".join(f"{message.get('role', 'user')}: {_snippet(message.get('content', ''), 220)}" for message in recent) or "(none)"


# ----------------------------------------------------------------------- research


def research_node(state: AgentState) -> dict[str, Any]:
    started = time.perf_counter()
    rounds = int(state.get("rounds", 0)) + 1
    queries = [query for query in (state.get("queries") or []) if query] or [state.get("rewritten") or state.get("question", "")]

    store = VectorStore.instance()
    documents: list[Document] = []
    note = ""
    status = "done"

    for query in queries[:3]:
        try:
            result = store.search(query)
        except RetrievalUnavailable as exc:
            note = str(exc)
            status = "warn"
            logger.warning("Retrieval unavailable: %s", exc)
            break
        documents.extend(result.get("documents", []))

    documents = _dedupe(documents)[: config.RETRIEVAL_TOP_K + 2]
    coverage = coverage_ratio(f"{state.get('question', '')} {state.get('rewritten', '')}", documents)

    if not documents and status != "warn":
        status = "warn"
        note = note or "No corpus page matched this request."

    summary = f"Pass {rounds}: {len(queries)} queries → {len(documents)} passages, coverage {int(coverage * 100)}%."
    bullets = [f"p. {doc.get('page')} · score {doc.get('score', 0):.2f}" for doc in documents[:4]]
    if note:
        bullets.append(note)

    return {
        "documents": documents,
        "coverage": coverage,
        "rounds": rounds,
        "retrieval_note": note,
        "trace": [event("research", "Research", "Evidence gatherer", started, summary, status, bullets)],
    }


# ----------------------------------------------------------------------- analysis


def analysis_node(state: AgentState) -> dict[str, Any]:
    started = time.perf_counter()
    question = state.get("question", "")
    documents = state.get("documents") or []

    hazard = hazards.classify(question, documents)

    if llm.available and documents:
        payload = llm.json(
            f"Question:\n{question}\n\nEvidence:\n{_evidence_block(documents)}",
            system=prompts.ANALYSIS_SYSTEM,
        )
        if payload:
            hazard = _merge_hazard(hazard, payload)

    summary = f"{hazard['label']} · severity {hazard['severity']} · confidence {hazard['confidence']:.2f}"
    bullets = hazard.get("key_findings") or hazard.get("signals") or hazard.get("drivers", [])
    return {
        "hazard": hazard,
        "trace": [event("analysis", "Analysis", "Hazard analyst", started, summary, bullets=list(bullets)[:4])],
    }


def _merge_hazard(base: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    hazard_id = str(payload.get("hazard_id", "")).strip()
    if hazard_id not in hazards.BY_ID:
        return base
    spec = hazards.BY_ID[hazard_id]
    severity = str(payload.get("severity", base["severity"])).capitalize()
    if severity not in {"High", "Medium", "Low"}:
        severity = base["severity"]
    try:
        confidence = _clamp(float(payload.get("confidence", base["confidence"])), 0.05, 0.95)
    except (TypeError, ValueError):
        confidence = base["confidence"]

    findings = [str(item)[:200] for item in payload.get("key_findings", []) if str(item).strip()][:4]
    signals = [str(item)[:160] for item in payload.get("incident_signals", []) if str(item).strip()][:4]
    drivers = [str(item)[:200] for item in payload.get("drivers", []) if str(item).strip()][:4] or spec["drivers"][:4]

    return {
        **base,
        "id": hazard_id,
        "label": spec["label"],
        "severity": severity,
        "confidence": round(confidence, 3),
        "drivers": drivers,
        "controls": spec["controls"][:4],
        "checks": [{"clause": clause, "requirement": requirement} for clause, requirement in spec["checks"]],
        "statute": spec["statute"],
        "key_findings": findings,
        "signals": signals or base.get("signals", []),
    }


# --------------------------------------------------------------------- compliance


def compliance_node(state: AgentState) -> dict[str, Any]:
    started = time.perf_counter()
    hazard = state.get("hazard") or hazards.classify(state.get("question", ""), [])
    documents = state.get("documents") or []
    base_checks = hazard.get("checks") or []

    checks: list[dict[str, str]] = []
    recommendations: list[str] = hazard.get("controls", [])[:4]

    if llm.available and documents:
        payload = llm.json(
            "Hazard: {label} (severity {severity})\nQuestion: {question}\n\nChecks to consider:\n{checks}\n\nEvidence:\n{evidence}".format(
                label=hazard.get("label", ""),
                severity=hazard.get("severity", ""),
                question=state.get("question", ""),
                checks="\n".join(f"- {check['clause']}: {check['requirement']}" for check in base_checks) or "(none)",
                evidence=_evidence_block(documents, max_docs=3, chars=520),
            ),
            system=prompts.COMPLIANCE_SYSTEM,
        )
        if payload and isinstance(payload.get("checks"), list):
            for item in payload["checks"][:6]:
                if not isinstance(item, dict):
                    continue
                status = str(item.get("status", "verify")).lower()
                checks.append(
                    {
                        "clause": str(item.get("clause", "Statutory check"))[:120],
                        "requirement": str(item.get("requirement", ""))[:300],
                        "status": status if status in {"covered", "verify", "gap"} else "verify",
                        "note": str(item.get("note", ""))[:220],
                    }
                )
            recs = [str(item)[:200] for item in payload.get("recommendations", []) if str(item).strip()]
            if recs:
                recommendations = recs[:5]

    if not checks:
        for check in base_checks:
            checks.append(
                {
                    "clause": check["clause"],
                    "requirement": check["requirement"],
                    "status": "verify",
                    "note": "Confirm against the current regulation edition and site records.",
                }
            )

    gaps = sum(1 for check in checks if check["status"] == "gap")
    summary = f"{len(checks)} statutory checks reviewed · {gaps} open gap(s)."
    bullets = [f"{check['clause']} → {check['status']}" for check in checks[:4]]

    return {
        "compliance": {
            "checks": checks,
            "recommendations": recommendations,
            "gaps": gaps,
            "statute": hazard.get("statute", ""),
        },
        "trace": [event("compliance", "Compliance", "Statutory reviewer", started, summary, bullets=bullets)],
    }


# ------------------------------------------------------------------------- report


def report_node(state: AgentState) -> dict[str, Any]:
    started = time.perf_counter()
    question = state.get("question", "")
    documents = state.get("documents") or []
    hazard = state.get("hazard") or hazards.classify(question, [])
    compliance = state.get("compliance") or {"checks": [], "recommendations": [], "gaps": 0}
    coverage = float(state.get("coverage", 0.0))

    narrative = None
    if llm.available and documents:
        narrative = llm.text(_report_prompt(question, documents, hazard, compliance), system=prompts.REPORT_SYSTEM)
    if not narrative:
        narrative = _offline_narrative(question, hazard, compliance, coverage, bool(documents))

    evidence_section = _evidence_section(documents)
    answer = f"{narrative.strip()}\n\n{evidence_section}".strip()

    total_checks = len(compliance.get("checks", []))
    check_quality = 0.0 if not total_checks else _clamp(1 - compliance.get("gaps", 0) / total_checks)
    confidence = round(_clamp(0.5 * coverage + 0.3 * hazard.get("confidence", 0.4) + 0.2 * check_quality, 0.05, 0.95), 3)

    citations = [
        {
            "page": doc.get("page"),
            "source": doc.get("source", ""),
            "score": doc.get("score", 0.0),
            "excerpt": _snippet(doc.get("text", ""), 220),
        }
        for doc in documents[:5]
    ]

    summary = f"{len(answer.split())} words · {len(citations)} citation(s) · confidence {confidence:.2f}"
    status = "done" if citations else "warn"
    return {
        "answer": answer,
        "citations": citations,
        "confidence": confidence,
        "trace": [
            event(
                "report",
                "Report",
                "Writer",
                started,
                summary,
                status,
                bullets=["Drafted with Gemini" if llm.available and documents else "Drafted from evidence templates (no model key)"],
            )
        ],
    }


def _report_prompt(question: str, documents: list[Document], hazard: dict[str, Any], compliance: dict[str, Any]) -> str:
    checks = "\n".join(
        f"- {check['clause']}: {check['status']} ({check['requirement']})" for check in compliance.get("checks", [])[:5]
    )
    return (
        f"Question:\n{question}\n\n"
        f"Hazard assessment:\n{hazard.get('label')} — severity {hazard.get('severity')} "
        f"(confidence {hazard.get('confidence')})\nDrivers: {'; '.join(hazard.get('drivers', [])[:4])}\n\n"
        f"Compliance checks:\n{checks or '(none)'}\n\n"
        f"Recommended controls:\n" + "\n".join(f"- {control}" for control in compliance.get("recommendations", [])[:4]) + "\n\n"
        f"Evidence:\n{_evidence_block(documents, max_docs=5, chars=650)}"
    )


def _evidence_section(documents: list[Document]) -> str:
    if not documents:
        return (
            "**Evidence from the DGMS corpus**\n"
            "- No matching page was retrieved for this request, so the answer above is limited to the hazard "
            "taxonomy and compliance reference rather than corpus evidence."
        )
    lines = [f"- (p. {doc.get('page')}) {_snippet(doc.get('text', ''), 210)} — {doc.get('source', 'DGMS report')}" for doc in documents[:4]]
    return "**Evidence from the DGMS corpus**\n\n" + "\n".join(lines)


def _offline_narrative(
    question: str, hazard: dict[str, Any], compliance: dict[str, Any], coverage: float, has_evidence: bool
) -> str:
    label = hazard.get("label", "General mining safety")
    severity = hazard.get("severity", "Medium")
    parts = [
        f"**Assessment.** The request points to **{label}** at **{severity}** severity "
        f"(confidence {hazard.get('confidence', 0.4):.2f})."
    ]

    findings = hazard.get("key_findings") or []
    if findings:
        parts.append("**Key findings**\n\n" + "\n".join(f"- {finding}" for finding in findings[:4]))
    else:
        parts.append("**Key findings**\n\n" + "\n".join(f"- {driver}" for driver in hazard.get("drivers", [])[:3]))

    recommendations = compliance.get("recommendations") or hazard.get("controls", [])
    if recommendations:
        parts.append(
            "**Recommended controls**\n\n" + "\n".join(f"{index}. {item}" for index, item in enumerate(recommendations[:4], start=1))
        )

    checks = compliance.get("checks", [])
    if checks:
        parts.append(
            "**Statutory checks to verify**\n\n"
            + "\n".join(f"- {check['clause']}: {check['requirement']}" for check in checks[:4])
        )

    limits = [
        f"- Corpus coverage of this question: {int(coverage * 100)}%.",
        "- The knowledge base is the DGMS *Statistics of Mines in India, Vol. II (Non-Coal), 2015*; "
        "other years or coal-sector data are not in it.",
    ]
    if not has_evidence:
        limits.append("- No page matched, so no corpus citation could be made.")
    limits.append("- Compliance points are checks to confirm with the current regulation edition, not a legal opinion.")
    parts.append("**Coverage and limits**\n\n" + "\n".join(limits))

    return "\n\n".join(parts)


# ------------------------------------------------------------------------- critic


def critic_node(state: AgentState) -> dict[str, Any]:
    started = time.perf_counter()
    documents = state.get("documents") or []
    citations = state.get("citations") or []
    coverage = float(state.get("coverage", 0.0))
    hazard = state.get("hazard") or {}
    confidence = float(state.get("confidence", 0.4))
    rounds = int(state.get("rounds", 1))
    question = state.get("question", "")

    issues: list[str] = []
    if not citations:
        issues.append("No corpus citation in the answer.")
    if coverage < 0.3:
        issues.append(f"Low evidence coverage ({int(coverage * 100)}%).")

    year = _requested_year(question)
    if year:
        evidence_text = " ".join(str(doc.get("text", "")) for doc in documents)
        if str(year) not in evidence_text:
            issues.append(f"Requested year {year} does not appear in the retrieved evidence.")

    grounded = bool(citations) and coverage >= 0.2
    request_replan = (not documents or coverage < 0.25) and rounds < config.MAX_AGENT_ROUNDS

    if not grounded:
        confidence = min(confidence, 0.35)
    elif coverage < 0.3:
        confidence = min(confidence, 0.5)

    queries: list[str] = []
    if request_replan:
        label = hazard.get("label", "")
        candidates = [
            question,
            f"{label} mining accidents causes precautions" if label else "",
            "mining accident statistics fatalities injuries",
        ]
        queries = [candidate for candidate in dict.fromkeys(candidates) if candidate]

    summary = (
        f"Grounded: {'yes' if grounded else 'no'} · coverage {int(coverage * 100)}% · confidence {confidence:.2f}. "
        + ("Requesting a second research pass." if request_replan else "Answer cleared for release.")
    )
    status = "warn" if issues else "done"
    return {
        "critique": {
            "grounded": grounded,
            "coverage": round(coverage, 3),
            "confidence": round(confidence, 3),
            "issues": issues,
            "request_replan": request_replan,
        },
        "confidence": round(confidence, 3),
        "queries": queries,
        "trace": [event("critic", "Critic", "Verifier", started, summary, status, bullets=issues[:4] or None)],
    }


def route_after_critic(state: AgentState) -> str:
    critique = state.get("critique") or {}
    return "research" if critique.get("request_replan") else "end"


# ------------------------------------------------------------ bulletin triage tool


def triage_bulletin(title: str, summary: str) -> dict[str, Any]:
    """Used by `GET /updates`: the analysis agent classifies one bulletin."""
    text = f"{title}. {summary}".strip()
    hazard = hazards.classify(text, [{"text": summary, "page": 0, "source": "bulletin", "score": 1.0}])
    if config.BULLETIN_LLM and llm.available:
        payload = llm.json(
            f"Bulletin title: {title}\nBulletin text: {_snippet(summary, 1200)}",
            system=prompts.ANALYSIS_SYSTEM,
        )
        if payload:
            hazard = _merge_hazard(hazard, payload)
    return hazard
