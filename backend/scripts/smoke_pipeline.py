"""Smoke test with the real FAISS index (no network required in offline mode).

Usage:
    python scripts/smoke_pipeline.py "methane accidents and precautions"
"""

from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import config  # noqa: E402
from agents.graph import run_pipeline  # noqa: E402
from agents.retrieval import VectorStore  # noqa: E402


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to cp1252
    question = sys.argv[1] if len(sys.argv) > 1 else "What causes roof falls and how are they prevented?"
    print(f"LLM mode: {config.LLM_MODE} | key present: {bool(config.GOOGLE_API_KEY)}")

    store = VectorStore.instance()
    store.load()
    print("Vector store:", json.dumps(store.status()))
    hits = store.search("methane explosion precautions")
    print(f"Raw search: {len(hits['documents'])} docs, coverage {hits['coverage']}, top page {hits['documents'][0]['page'] if hits['documents'] else None}")

    result = run_pipeline(question)
    print("\n=== TRACE ===")
    for step in result["trace"]:
        print(f"{step['agent']:11s} {step['status']:5s} {step['ms']:5d}ms  {step['summary']}")
    print(f"\nConfidence: {result['confidence']} | Intent: {result['intent']} | Citations: {len(result['evidence'])}")
    print("\n=== ANSWER ===\n")
    print(result["answer"][:1800])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
