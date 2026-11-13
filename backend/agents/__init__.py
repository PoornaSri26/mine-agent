"""Multi-agent layer for MineRakshak.

`run_pipeline` is the only entry point the API needs: it executes the
supervisor graph and returns the answer plus the full agent trace.
"""

from agents import hazards
from agents.graph import get_graph, run_pipeline
from agents.roster import AGENTS, PIPELINE

__all__ = ["run_pipeline", "get_graph", "AGENTS", "PIPELINE", "hazards"]
