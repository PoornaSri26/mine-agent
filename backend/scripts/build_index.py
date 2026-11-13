"""Rebuild the FAISS index for the current embedding model.

Run this whenever EMBED_MODEL changes (the index and the model must match):

    python scripts/build_index.py

It reads the page corpus from ``index.pkl`` so no re-parsing of the source PDF
is needed, embeds every page with the configured model, and writes a
cosine-similarity index plus ``index_meta.json``.
"""

from __future__ import annotations

import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import config  # noqa: E402
from agents.retrieval import FAISS_PATH, INDEX_META_PATH, read_documents  # noqa: E402


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    documents = read_documents()
    print(f"Loaded {len(documents)} pages from index.pkl")
    print(f"Embedding with {config.EMBED_MODEL} (this downloads the model on first run)")

    import faiss
    import numpy as np
    import torch
    from sentence_transformers import SentenceTransformer

    started = time.perf_counter()
    # CPU inference is much faster in float32 than the checkpoint's bf16 default.
    encoder = SentenceTransformer(config.EMBED_MODEL, model_kwargs={"dtype": torch.float32})
    vectors = encoder.encode(
        [doc["text"] for doc in documents],
        batch_size=32,
        normalize_embeddings=True,
        show_progress_bar=True,
        convert_to_numpy=True,
    ).astype("float32")

    index = faiss.IndexFlatIP(vectors.shape[1])  # inner product on normalised vectors == cosine
    index.add(np.asarray(vectors))

    faiss.write_index(index, str(FAISS_PATH))
    INDEX_META_PATH.write_text(
        json.dumps(
            {
                "embed_model": config.EMBED_MODEL,
                "documents": len(documents),
                "dimensions": int(vectors.shape[1]),
                "normalized": True,
                "metric": "cosine",
                "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    elapsed = time.perf_counter() - started
    print(
        f"Wrote {FAISS_PATH.name} ({FAISS_PATH.stat().st_size / 1e6:.1f} MB, "
        f"{vectors.shape[1]} dims) in {elapsed:.0f}s"
    )
    print(f"Wrote {INDEX_META_PATH.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
