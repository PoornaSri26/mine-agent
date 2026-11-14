---
title: MineRakshak API
emoji: ⛑️
colorFrom: yellow
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
---

# MineRakshak API

FastAPI + LangGraph service behind the MineRakshak multi-agent mine-safety officer.

This file is the Hugging Face Space card: `sdk: docker` and `app_port: 7860` are what make the Space run the
image built from `Dockerfile.huggingface`, so keep the front matter when the folder is uploaded as a Space.

Deploy notes:

* Set `GOOGLE_API_KEY` in **Settings → Variables and secrets** as a *secret*, never as a plain variable.
* Set `ALLOWED_ORIGINS` to the Vercel origin that calls this API.
* `index.faiss`, `index.pkl` and `index_meta.json` are committed, so the image serves retrieval
  immediately instead of downloading the embedder at build time.
* Health check: `GET /health`, which reports retrieval and LLM status.
