# -------------------------------------------------------
# MineRakshak agent service (FastAPI + LangGraph + FAISS)
# Works on Hugging Face Spaces (port 7860) and Render ($PORT).
# -------------------------------------------------------
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TRANSFORMERS_CACHE=/app/.cache/huggingface \
    SENTENCE_TRANSFORMERS_HOME=/app/.cache/sentence-transformers \
    HF_HOME=/app/.cache/huggingface \
    EMBED_BACKEND=onnx \
    TORCH_THREADS=1 \
    OMP_NUM_THREADS=1 \
    MALLOC_ARENA_MAX=2

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements-serve.txt .
RUN pip install --upgrade pip && pip install -r requirements-serve.txt

# Prefetch the pinned ONNX encoder so a container starts serving without a
# 191 MB download on the first query.
RUN python -c "from huggingface_hub import hf_hub_download as d; [d('keisuke-miyako/granite-embedding-small-english-r2-onnx-fp32', f, revision='5f8b507347bf281bcaceefcc51ae5435a31fbbdd') for f in ('model.onnx', 'tokenizer.json')]"

COPY . .

RUN mkdir -p /app/data /app/.cache

EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
    CMD curl -fsS "http://localhost:${PORT:-7860}/health" || exit 1

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-7860} --timeout-keep-alive 75"]
