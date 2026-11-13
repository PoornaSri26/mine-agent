"""Gemini client for the agent team (current `google-genai` SDK).

Notes for 2026:
* `google-generativeai` is the retired SDK; `google-genai` is the supported one.
* Sampling knobs (`temperature`, `top_p`, `top_k`) are deprecated and ignored on
  Gemini 3.6+/3.5-Flash-Lite and rejected by later generations, so nothing here
  sends them.
* A missing key or provider error must never break the graph: callers get
  `None` and fall back to deterministic, evidence-based reasoning.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import config

logger = logging.getLogger("minerakshak.llm")

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


class GeminiClient:
    def __init__(self) -> None:
        self._client: Any = None
        self._failed = False

    @property
    def available(self) -> bool:
        return config.llm_enabled()

    def _get_client(self) -> Any:
        if not config.llm_enabled() or self._failed:
            return None
        if self._client is None:
            try:
                from google import genai
                from google.genai import types

                self._client = genai.Client(
                    api_key=config.GOOGLE_API_KEY,
                    http_options=types.HttpOptions(timeout=60_000),
                )
                logger.info("Gemini client ready: %s", config.GEMINI_MODEL)
            except Exception as exc:  # pragma: no cover - depends on env
                self._failed = True
                logger.warning("Gemini unavailable, using offline reasoning: %s", exc)
        return self._client

    def _generate(self, prompt: str, system: str | None, json_mode: bool) -> str | None:
        client = self._get_client()
        if client is None:
            return None
        try:
            from google.genai import types

            response = client.models.generate_content(
                model=config.GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    response_mime_type="application/json" if json_mode else "text/plain",
                    max_output_tokens=2048,
                ),
            )
            return (getattr(response, "text", "") or "").strip() or None
        except Exception as exc:  # pragma: no cover - network dependent
            logger.warning("Gemini call failed (%s): %s", config.GEMINI_MODEL, exc)
            return None

    def text(self, prompt: str, system: str | None = None) -> str | None:
        return self._generate(prompt, system, json_mode=False)

    def json(self, prompt: str, system: str | None = None) -> dict[str, Any] | None:
        raw = self._generate(prompt, system, json_mode=True)
        if not raw:
            return None
        cleaned = _FENCE_RE.sub("", raw).strip()
        try:
            parsed = json.loads(cleaned)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if not match:
                return None
            try:
                parsed = json.loads(match.group(0))
                return parsed if isinstance(parsed, dict) else None
            except json.JSONDecodeError:
                logger.warning("Could not parse model JSON output")
                return None


llm = GeminiClient()
