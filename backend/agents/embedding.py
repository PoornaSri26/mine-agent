"""Embedder used by the research agent.

The deployed service runs the *same* Granite R2 model through ONNX Runtime rather
than PyTorch + sentence-transformers. Tokenizer, CLS pooling and L2
normalisation are identical to the model's own ``1_Pooling/config.json``, so the
committed FAISS index stays valid — measured cosine against the torch encoder on
the same text is 1.000000 (L2 distance 0.0).

The reason is memory: importing torch and sentence-transformers costs roughly
650 MB before a single query runs, which does not fit a 512 MB free instance.
This path needs about 350 MB including the 191 MB of fp32 weights.

``EMBED_BACKEND=torch`` keeps the sentence-transformers path for index building
and side-by-side comparison.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable

import numpy as np

import config

logger = logging.getLogger("minerakshak.embedding")

MAX_TOKENS = 512


class OnnxEmbedder:
    """Granite R2 through ONNX Runtime: same vectors, no PyTorch."""

    def __init__(self) -> None:
        import onnxruntime as ort
        from huggingface_hub import hf_hub_download
        from tokenizers import Tokenizer

        model_path = hf_hub_download(
            config.EMBED_ONNX_REPO, config.EMBED_ONNX_FILE, revision=config.EMBED_ONNX_REVISION
        )
        tokenizer_path = hf_hub_download(
            config.EMBED_ONNX_REPO, "tokenizer.json", revision=config.EMBED_ONNX_REVISION
        )

        self._tokenizer = Tokenizer.from_file(tokenizer_path)
        self._tokenizer.enable_truncation(max_length=MAX_TOKENS)

        options = ort.SessionOptions()
        options.intra_op_num_threads = config.TORCH_THREADS
        options.inter_op_num_threads = 1
        self._session = ort.InferenceSession(
            model_path, sess_options=options, providers=["CPUExecutionProvider"]
        )
        self._inputs = {item.name for item in self._session.get_inputs()}
        logger.info(
            "ONNX embedder ready: %s/%s@%s",
            config.EMBED_ONNX_REPO,
            config.EMBED_ONNX_FILE,
            config.EMBED_ONNX_REVISION[:8],
        )

    def encode(
        self,
        texts: Iterable[str],
        normalize_embeddings: bool = True,
        show_progress_bar: bool = False,  # accepted for sentence-transformers parity
    ) -> np.ndarray:
        batch = self._tokenizer.encode_batch([str(text) for text in texts])
        width = max((len(item.ids) for item in batch), default=1)
        ids = np.zeros((len(batch), width), dtype=np.int64)
        mask = np.zeros_like(ids)
        for row, encoded in enumerate(batch):
            ids[row, : len(encoded.ids)] = encoded.ids
            mask[row, : len(encoded.ids)] = 1

        feeds: dict[str, Any] = {"input_ids": ids, "attention_mask": mask}
        if "token_type_ids" in self._inputs:
            feeds["token_type_ids"] = np.zeros_like(ids)

        hidden = self._session.run(None, feeds)[0]
        vectors = np.asarray(hidden[:, 0, :], dtype="float32")  # CLS pooling
        if normalize_embeddings:
            norms = np.linalg.norm(vectors, axis=1, keepdims=True)
            vectors = vectors / np.where(norms == 0, 1.0, norms)
        return vectors

    def get_sentence_embedding_dimension(self) -> int:
        # Read from a real forward pass: ONNX exports declare the sequence axis
        # as dynamic, so the shape table cannot be trusted for this.
        return int(self.encode(["dimension probe"]).shape[1])


def build_encoder() -> Any:
    """Return the encoder selected by ``EMBED_BACKEND``."""
    if config.EMBED_BACKEND == "torch":
        import torch
        from sentence_transformers import SentenceTransformer

        torch.set_num_threads(config.TORCH_THREADS)
        return SentenceTransformer(
            config.EMBED_MODEL, model_kwargs={"dtype": torch.float32}
        )
    return OnnxEmbedder()


def backend_name() -> str:
    return "sentence-transformers" if config.EMBED_BACKEND == "torch" else "onnx-runtime"
