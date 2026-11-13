"""Research agent tool: FAISS + reranking over the DGMS page corpus.

Current stack (2026):
* Embeddings: ``ibm-granite/granite-embedding-small-english-r2`` (47M params,
  384-dim, Apache-2.0, released Aug 2025). It needs no query instruction prefix.
* Reranker: optional cross-encoder (``ENABLE_RERANK=1``), default off because a
  0.6B reranker is far too slow on free CPU hosting.
* The index must be rebuilt whenever the embedding model changes; ``index_meta.json``
  records the model and dimension so a stale index fails loudly instead of
  returning garbage.

The legacy ``agent1.py`` loaded metadata through LangChain's docstore, which is
not a dependency here; this module reads the same pickle correctly.
"""

from __future__ import annotations

import json
import logging
import math
import pickle
import re
import threading
from typing import Any

import config

logger = logging.getLogger("minerakshak.retrieval")

INDEX_META_PATH = config.BASE_DIR / "index_meta.json"
FAISS_PATH = config.BASE_DIR / "index.faiss"

# Instruction prefix for models that require one (e.g. Qwen3-Embedding).
# Granite R2 needs no prefix; keep this empty unless EMBED_MODEL changes.
EMBED_QUERY_PREFIX = ""

_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "in", "on", "for", "to", "with", "by", "at", "from",
    "is", "are", "was", "were", "be", "been", "this", "that", "these", "those", "it", "as",
    "which", "what", "how", "why", "when", "where", "who", "do", "does", "did", "not", "no",
    "can", "could", "should", "would", "may", "might", "will", "shall", "than", "then",
    "there", "their", "they", "we", "our", "you", "your", "about", "into", "over", "under",
    "between", "during", "after", "before", "more", "most", "some", "any", "all", "each",
    "also", "if", "but", "while", "give", "show", "tell", "list", "many", "much",
}


class RetrievalUnavailable(RuntimeError):
    """Raised when the vector index or embedding model cannot be loaded."""


class _Stub:
    """Absorbs LangChain classes referenced by the pickled docstore."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    def __setstate__(self, state: Any) -> None:
        if isinstance(state, dict):
            self.__dict__.update(state)
        elif isinstance(state, tuple):
            for part in state:
                if isinstance(part, dict):
                    self.__dict__.update(part)
        else:
            self.__dict__["_state"] = state


class _StubUnpickler(pickle.Unpickler):
    def find_class(self, module: str, name: str) -> Any:  # noqa: D102 - pickle hook
        return type(name, (_Stub,), {})


def read_documents() -> list[dict[str, Any]]:
    """Page corpus stored in ``index.pkl`` (the source of truth for the index)."""
    path = config.BASE_DIR / "index.pkl"
    try:
        with open(path, "rb") as handle:
            meta = pickle.load(handle)
    except ModuleNotFoundError:
        with open(path, "rb") as handle:
            meta = _StubUnpickler(handle).load()

    if not isinstance(meta, (tuple, list)) or len(meta) < 2:
        raise RetrievalUnavailable("index.pkl has an unexpected structure")

    docstore, id_map = meta[0], meta[1]
    if not isinstance(id_map, dict):
        raise RetrievalUnavailable("index.pkl is missing its id map")

    raw = getattr(docstore, "_dict", None) or getattr(docstore, "__dict__", {}).get("_dict")
    if not isinstance(raw, dict):
        raise RetrievalUnavailable("Docstore contents could not be read")

    documents: list[dict[str, Any]] = []
    for position in sorted(id_map):
        doc = raw.get(id_map[position])
        if doc is None:
            continue
        fields = getattr(doc, "__dict__", {}).get("__dict__", {}) if not isinstance(doc, dict) else doc
        text = str(fields.get("page_content", "") or "")
        if len(text.strip()) < 60:
            continue
        info = fields.get("metadata", {}) or {}
        source = str(info.get("source", "mines-statistics.pdf")).replace("\\", "/").split("/")[-1]
        page = int(info.get("page", position)) + 1
        documents.append({"text": text, "source": source, "page": page})
    if not documents:
        raise RetrievalUnavailable("No usable documents in index.pkl")
    return documents


def terms(text: str) -> list[str]:
    return [
        word
        for word in re.findall(r"[a-z0-9]+", text.lower())
        if len(word) > 2 and word not in _STOPWORDS
    ]


def coverage(question: str, documents: list[dict[str, Any]]) -> float:
    """Share of question concepts present in the retrieved evidence."""
    wanted = set(terms(question))
    if not wanted:
        return 0.0
    haystack = " ".join(str(doc.get("text", "")) for doc in documents).lower()
    found = sum(1 for term in wanted if term in haystack)
    return round(found / len(wanted), 3)


class VectorStore:
    """Process-wide, lazily loaded FAISS store."""

    _instance: "VectorStore | None" = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._ready = False
        self._error: str | None = None
        self._load_lock = threading.Lock()
        self.documents: list[dict[str, Any]] = []
        self.index: Any = None
        self.encoder: Any = None
        self.reranker: Any = None
        self.reranker_name: str | None = None
        self.meta: dict[str, Any] = {}

    @classmethod
    def instance(cls) -> "VectorStore":
        with cls._lock:
            if cls._instance is None:
                cls._instance = VectorStore()
            return cls._instance

    def _config_error(self) -> str | None:
        if not INDEX_META_PATH.exists():
            return (
                "index_meta.json is missing; rebuild the vector store with "
                "`python scripts/build_index.py`."
            )
        try:
            meta = json.loads(INDEX_META_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return f"index_meta.json could not be read: {exc}"
        self.meta = meta
        if meta.get("embed_model") != config.EMBED_MODEL:
            return (
                f"Index was built with {meta.get('embed_model')!r} but EMBED_MODEL is "
                f"{config.EMBED_MODEL!r}; rebuild with `python scripts/build_index.py`."
            )
        return None

    def load(self) -> None:
        if self._ready:
            return
        with self._load_lock:
            if self._ready:
                return

            problem = self._config_error()
            if problem:
                self._error = problem
                raise RetrievalUnavailable(problem)

            self.documents = read_documents()
            try:
                import faiss
                from sentence_transformers import SentenceTransformer
            except Exception as exc:  # pragma: no cover - heavy optional deps
                self._error = f"Retrieval dependencies unavailable: {exc}"
                raise RetrievalUnavailable(self._error) from exc

            self.index = faiss.read_index(str(FAISS_PATH))
            # Qwen3 checkpoints load as bfloat16 by default, which is far slower on CPU.
            import torch

            self.encoder = SentenceTransformer(
                config.EMBED_MODEL, model_kwargs={"dtype": torch.float32}
            )
            dimension = self.encoder.get_sentence_embedding_dimension() or 0
            if dimension and dimension != getattr(self.index, "d", dimension):
                self._error = (
                    f"Index dimension {self.index.d} does not match {config.EMBED_MODEL} ({dimension}); "
                    "rebuild with `python scripts/build_index.py`."
                )
                raise RetrievalUnavailable(self._error)

            if config.ENABLE_RERANK:
                self.reranker, self.reranker_name = self._load_reranker()
            self._ready = True
            logger.info(
                "Vector store ready: %d docs · %s · rerank=%s",
                len(self.documents),
                config.EMBED_MODEL,
                self.reranker_name or "off",
            )

    def _load_reranker(self) -> tuple[Any, str | None]:
        try:
            from sentence_transformers import CrossEncoder

            model = CrossEncoder(config.RERANK_MODEL)
            return model, config.RERANK_MODEL
        except Exception as exc:  # pragma: no cover - model support varies
            logger.warning("Reranker %s unavailable (%s); trying fallback", config.RERANK_MODEL, exc)
        try:
            from sentence_transformers import CrossEncoder

            fallback = "BAAI/bge-reranker-v2-m3"
            return CrossEncoder(fallback), fallback
        except Exception as exc:  # pragma: no cover - optional
            logger.warning("Reranking disabled: %s", exc)
            return None, None

    def _embed_query(self, query: str) -> Any:
        import numpy as np

        vectors = self.encoder.encode(
            [EMBED_QUERY_PREFIX + query],
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return np.asarray(vectors, dtype="float32")

    def search(self, query: str, k: int | None = None, fetch_k: int = 16) -> dict[str, Any]:
        k = k or config.RETRIEVAL_TOP_K
        self.load()
        if self.index is None or self.encoder is None:
            raise RetrievalUnavailable(self._error or "Vector store not initialised")

        total = min(fetch_k, len(self.documents))
        scores, indices = self.index.search(self._embed_query(query), total)
        candidates: list[dict[str, Any]] = []
        for position, similarity in zip(indices[0], scores[0]):
            if 0 <= int(position) < len(self.documents):
                doc = dict(self.documents[int(position)])
                doc["vector_score"] = round(float(similarity), 4)
                candidates.append(doc)
        if not candidates:
            return {"documents": [], "coverage": 0.0, "top_score": 0.0}

        if self.reranker is not None:
            raw = self.reranker.predict([(query, doc["text"]) for doc in candidates])
            for doc, score in zip(candidates, raw):
                doc["score"] = round(1 / (1 + math.exp(-float(score))), 4)
        else:
            for doc in candidates:
                doc["score"] = doc.get("vector_score", 0.0)

        candidates.sort(key=lambda doc: doc.get("score", 0.0), reverse=True)
        top = candidates[:k]
        return {
            "documents": top,
            "coverage": coverage(query, top),
            "top_score": top[0].get("score", 0.0) if top else 0.0,
        }

    def status(self) -> dict[str, Any]:
        return {
            "ready": self._ready,
            "documents": len(self.documents),
            "embed_model": config.EMBED_MODEL,
            "rerank_model": self.reranker_name,
            "dimensions": self.meta.get("dimensions"),
            "error": self._error,
        }


def warmup() -> bool:
    """Optional startup warm-up; failures are reported, never fatal."""
    try:
        VectorStore.instance().load()
        return True
    except Exception as exc:  # pragma: no cover - environment dependent
        logger.warning("Retrieval warm-up failed: %s", exc)
        return False
