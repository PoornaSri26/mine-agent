"""LangGraph wiring: supervisor → research → analysis → compliance → report → critic.

The critic owns a conditional edge back to research, which is what makes the
run agentic rather than a fixed pipeline: when evidence is too thin the team
re-plans its own search instead of shipping a weak answer.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from langgraph.graph import END, START, StateGraph

from agents import nodes
from agents.state import AgentState

logger = logging.getLogger("minerakshak.graph")

_GRAPH: Any = None
_LOCK = threading.Lock()


def _build() -> Any:
    builder = StateGraph(AgentState)
    builder.add_node("supervisor", nodes.supervisor_node)
    builder.add_node("research", nodes.research_node)
    builder.add_node("analysis", nodes.analysis_node)
    builder.add_node("compliance", nodes.compliance_node)
    builder.add_node("report", nodes.report_node)
    builder.add_node("critic", nodes.critic_node)

    builder.add_edge(START, "supervisor")
    builder.add_edge("supervisor", "research")
    builder.add_edge("research", "analysis")
    builder.add_edge("analysis", "compliance")
    builder.add_edge("compliance", "report")
    builder.add_edge("report", "critic")
    builder.add_conditional_edges(
        "critic", nodes.route_after_critic, {"research": "research", "end": END}
    )
    return builder.compile()


def get_graph() -> Any:
    global _GRAPH
    if _GRAPH is None:
        with _LOCK:
            if _GRAPH is None:
                _GRAPH = _build()
                logger.info("Agent graph compiled")
    return _GRAPH


def run_pipeline(question: str, history: list[dict[str, str]] | None = None) -> dict[str, Any]:
    """Execute the graph for one user turn."""
    graph = get_graph()
    initial: AgentState = {
        "question": question,
        "history": history or [],
        "rounds": 0,
        "trace": [],
    }
    final = graph.invoke(initial, {"recursion_limit": 60})

    documents = final.get("documents") or []
    return {
        "answer": final.get("answer", ""),
        "confidence": float(final.get("confidence", 0.0)),
        "intent": final.get("intent", "knowledge"),
        "trace": final.get("trace", []),
        "evidence": [
            {
                "page": doc.get("page"),
                "source": doc.get("source", ""),
                "score": doc.get("score", 0.0),
                "excerpt": (doc.get("text", "")[:240]).strip(),
            }
            for doc in documents
        ],
        "hazard": final.get("hazard", {}),
        "compliance": final.get("compliance", {}),
        "critique": final.get("critique", {}),
        "plan": {
            "intent": final.get("intent", "knowledge"),
            "rewritten": final.get("rewritten", question),
            "tasks": final.get("tasks", []),
            "rounds": final.get("rounds", 1),
        },
    }
