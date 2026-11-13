# MineRakshak — Digital Mine Safety Officer (multi-agent)

A DGMS mining-safety assistant upgraded from a single RAG prompt into a **supervisor-led team of six
collaborating agents**. The FastAPI backend, the React frontend and the FAISS knowledge base are the
original project's; the agent layer is the enhancement.

| Before | After |
| --- | --- |
| One prompt → one RAG call → one answer | Supervisor plans, delegates to five specialists and merges the result |
| No task decomposition | Intent-aware plan with per-agent responsibilities |
| No self-checking | Critic verifies grounding/coverage and can send the run back for a second research pass |
| Risk analysis was a single free-text prompt | Analysis agent uses a hazard taxonomy + severity rules, model-optional |
| Audit PDF was one prompt | Compliance + Report agents produce the briefing, then it is typeset as a PDF |
| No visibility | Every answer carries the agent trace; an **Agent Mesh** screen explains the team |
| No accounts/sessions in the repo | Auth + conversation history implemented (the frontend already expected them) |

## Architecture

```
React SPA (Vercel)
   │  Authorization: Bearer <token>
   ▼
FastAPI (Render / Hugging Face Spaces)
   │
   ├─ /auth/*, /sessions/*          SQLite (users, tokens, chats, traces)
   │
   └─ LangGraph supervisor graph (shared AgentState = blackboard)
        Supervisor  ──► Research ──► Analysis ──► Compliance ──► Report ──► Critic
                          ▲                                                  │
                          └────────────── replan if coverage is thin ───────┘
                                               (max 2 passes)

Research tools: FAISS cosine index (1,054 DGMS pages) · Qwen3-Embedding-0.6B (1,024-d) · Qwen3-Reranker-0.6B
Reasoning:      Gemini 3.8 Flash via the google-genai SDK (optional; deterministic fallback without a key)
```

### The agents

| Agent | Job | What it adds |
| --- | --- | --- |
| **Supervisor** | Reads the request + recent conversation, sets intent, writes the plan | Delegation instead of a fixed pipeline; resolves follow-up questions |
| **Research** | Rewrites queries, searches FAISS, reranks, reports coverage | Multiple evidence passes, explicit coverage metric |
| **Analysis** | Classifies hazard, severity, drivers, incident signals | Structured, comparable assessments from a mining taxonomy |
| **Compliance** | Maps findings to statutory checks and controls | Flags what must be verified on site instead of asserting legality |
| **Report** | Writes the cited briefing / audit narrative | Citations only from retrieved pages; no invented statistics |
| **Critic** | Grounding + coverage gate, replan trigger | The loop that makes the system self-correcting |

## API

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/auth/register`, `/auth/login` | Create account / sign in, returns a bearer token |
| `GET` | `/auth/me` | Restore session |
| `POST` | `/auth/logout` | Revoke token |
| `GET/POST` | `/sessions` | List / create conversations |
| `GET/PATCH/DELETE` | `/sessions/{id}` | Load (with traces), rename, delete |
| `POST` | `/query` | **Agentic answer** + `trace`, `confidence`, `intent`, `evidence` |
| `GET` | `/updates` | Live bulletins, each classified by the analysis agent |
| `POST` | `/audit_report_pdf` | Agent-written audit briefing as a PDF |
| `GET` | `/agents` | Roster, pipeline order, LLM status |
| `GET` | `/health` | Service, retrieval and LLM status |

`/query` keeps its original contract (`{query, session_id}` → `{response, session_id}`) and adds fields, so the
existing frontend keeps working.

## Models

| Layer | Model | Notes |
| --- | --- | --- |
| Reasoning | `gemini-3.8-flash` | Current stable Flash model. Gemini 2.5 is retired on 1 Dec 2026, so no 2.5 model string is used anywhere. Sampling parameters are not sent: they are deprecated on these generations. |
| Embeddings | `Qwen/Qwen3-Embedding-0.6B` | 1,024-dim, Apache-2.0, instruction-tuned (query prefix lives in `agents/retrieval.py`). |
| Reranking | `Qwen/Qwen3-Reranker-0.6B` | Falls back to `BAAI/bge-reranker-v2-m3` if a sentence-transformers build cannot load it. |

Both model IDs are environment overrides (`GEMINI_MODEL`, `EMBED_MODEL`, `RERANK_MODEL`). Changing
`EMBED_MODEL` requires rebuilding the index — `index_meta.json` records the model and dimension, and the
service refuses to query a mismatched index instead of returning nonsense:

```bash
cd backend && python scripts/build_index.py
```

## Repository layout

```
backend/
  main.py                 FastAPI routes (query, updates, audit PDF, health)
  agents/                 LangGraph state, nodes, graph, prompts, taxonomy, retrieval
  auth.py                 auth + session endpoints
  db.py / security.py     SQLite persistence, PBKDF2 + hashed bearer tokens
  report_pdf.py           markdown → A4 PDF
  scripts/smoke_pipeline.py
  tests/                  agent-graph and API tests (offline, no key needed)
frontend/
  src/components/AgentTrace.tsx       agent run timeline in chat
  src/components/AgentsScreen.tsx     "Agent Mesh" screen
  src/services/api.ts                 configurable API origin
render.yaml               Render blueprint for the API
frontend/vercel.json      Vercel build config
```

## Run locally

**Backend** (Python 3.11+):

```bash
cd backend
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                  # add GOOGLE_API_KEY here
python scripts/build_index.py                         # only needed if you change EMBED_MODEL
uvicorn main:app --reload --port 8000
```

Without `GOOGLE_API_KEY` the service runs in deterministic mode (`AGENT_LLM_MODE=auto`): retrieval,
hazard analysis, compliance mapping and the critic all work, only the narrative is template-based.

**Frontend**:

```bash
cd frontend
npm install
echo "VITE_API_BASE_URL=http://localhost:8000" > .env.local
npm run dev
```

Demo login created on first boot: `demo@minerakshak.app` / `demo1234` (set `SEED_DEMO=0` to disable).

## Tests

```bash
cd backend && python -m pytest -q          # 17 tests, offline, no API key
cd frontend && npm run lint                # tsc --noEmit
```

Agent tests cover delegation order, the critic's second research pass, the no-evidence path, hazard
classification and the API contract (auth, persistence with traces, `/updates` format).

## Deploy

### 1. Backend — Hugging Face Spaces (recommended, free)

The API needs the full PyTorch + FAISS stack (~2 GB), which fits Spaces comfortably.

1. Create a **Docker** Space at huggingface.co/new-space.
2. Push the contents of `backend/` to it (Space `README.md` front-matter: `sdk: docker`, `app_port: 7860`).
3. Space → Settings → **Variables and secrets**: add `GOOGLE_API_KEY` as a *secret*, plus
   `ALLOWED_ORIGINS=https://<your-vercel-app>.vercel.app`.
4. Wait for the build; check `https://<space>.hf.space/health`.

### 2. Backend — Render (free alternative)

Render → New → Blueprint → this repo. It reads `render.yaml`, asks for `GOOGLE_API_KEY` and
`ALLOWED_ORIGINS`, and mounts a 1 GB disk for SQLite. **Caveat:** the free 512 MB instance can be too small
for the embedding models; if it restarts on first query, use Spaces or a paid instance.

### 3. Frontend — Vercel

```bash
cd frontend
vercel            # or: import the repo in the Vercel dashboard, root directory = frontend
```

Set `VITE_API_BASE_URL` to the deployed backend origin in Vercel → Settings → Environment Variables, then
redeploy. `GEMINI_API_KEY` must **never** appear in the frontend environment.

## Data and limitations

* The corpus is **DGMS "Statistics of Mines in India, Vol. II (Non-Coal), 2015"** (1,054 pages, extracted from
  the repository's `index.pkl`). Questions about other years or coal-sector statistics are outside it, and
  the agents say so rather than inventing numbers.
* Compliance output is *checks to verify* against the current regulation edition — not a legal opinion.
* `ALLOWED_ORIGINS` defaults to localhost; set it to the deployed frontend origin (or `*` for a review demo).
* This is an engineering prototype for review, not a certified safety system.

## Branch

Development happens on `feature/multi-agent-system`; `main` keeps the original implementation intact.
