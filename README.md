# Company Knowledge Assistant

> A multi-tenant RAG (Retrieval-Augmented Generation) SaaS that lets employees ask questions about internal HR policies, SOPs, and onboarding guides — and get instant, accurate, source-cited answers instead of messaging HR/IT.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        Clients                              │
│   Next.js Dashboard (Vercel)    Slack Bot (Socket Mode)     │
└──────────────────┬──────────────────────┬───────────────────┘
                   │  HTTPS               │  Slack Events
                   ▼                      ▼
┌─────────────────────────────────────────────────────────────┐
│               FastAPI Backend (Railway)                      │
│  ┌───────────┐  ┌──────────────┐  ┌──────────────────────┐ │
│  │ /documents│  │    /query    │  │    Slack Bolt Bot    │ │
│  │  (admin)  │  │  (RAG pipe)  │  │  (/ask, @mention)   │ │
│  └─────┬─────┘  └──────┬───────┘  └──────────┬───────────┘ │
│        │               │                      │             │
│  ┌─────▼───────────────▼──────────────────────▼──────────┐ │
│  │  Services: parser → chunker → embedder → retriever → llm│ │
│  └────────────────────────┬──────────────────────────────┘ │
└───────────────────────────┼─────────────────────────────────┘
                            │
                ┌───────────▼───────────┐
                │   Supabase (Postgres) │
                │   + pgvector HNSW     │
                │   + Supabase Auth     │
                └───────────────────────┘
                            │
          ┌─────────────────┼──────────────────┐
          ▼                 ▼                  ▼
    Voyage AI          Anthropic          Supabase Storage
   (embeddings)    (Claude Sonnet)       (file uploads)
```

---

## Monorepo Structure

```
/
├── .env.example              # All env vars reference
├── README.md
├── backend/                  # FastAPI app
│   ├── Dockerfile
│   ├── railway.toml
│   ├── pyproject.toml
│   ├── main.py
│   ├── .env.example
│   ├── supabase/functions/
│   │   └── match_document_chunks.sql
│   ├── evaluation/           # RAGAS evaluation suite (optional)
│   │   ├── dataset/
│   │   │   └── eval_questions.json
│   │   ├── build_dataset.py
│   │   ├── run_ragas.py
│   │   └── results/          # git-ignored output
│   └── app/
│       ├── core/             # config, supabase client
│       ├── api/              # routes + deps
│       ├── services/         # parser, chunker, embedder, retriever, llm
│       └── slack/            # Slack Bolt bot
├── frontend/                 # Next.js 14 App Router
│   ├── src/
│   │   ├── app/              # pages: login, dashboard, analytics, chat
│   │   ├── components/       # DocumentUploader, ChatWindow, charts…
│   │   └── lib/              # supabase client, api helpers
│   └── .env.example
└── docs/
    ├── schema.sql            # Full Postgres DDL (run in Supabase SQL Editor)
    ├── schema_diagram.md     # ERD
    └── slack_setup.md        # Slack app creation guide
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11+, FastAPI, uvicorn |
| Database | Supabase (Postgres 15 + pgvector) |
| Auth | Supabase Auth (email/password) |
| Embeddings | Voyage AI `voyage-3-large` (1024-dim) |
| LLM | Anthropic Claude (claude-sonnet-4-5) |
| Document Parsing | `unstructured` + `pypdf` + `python-docx` |
| Frontend | Next.js 14 (App Router), TypeScript, Tailwind CSS |
| Charts | recharts |
| Slack | Slack Bolt SDK (Socket Mode) |
| Backend hosting | Railway |
| Frontend hosting | Vercel |

---

## Prerequisites

- Python 3.11+
- Node.js 18+
- A [Supabase](https://supabase.com) project (free tier works)
- A [Voyage AI](https://www.voyageai.com) API key **or** OpenAI API key
- An [Anthropic](https://console.anthropic.com) API key
- A [Slack App](https://api.slack.com/apps) (for Milestone 5 only)

---

## Local Setup

### 1. Clone & set up environment files

```bash
git clone <your-repo-url>
cd <repo-root>

# Backend
cp .env.example backend/.env
# Edit backend/.env with your real keys

# Frontend
cp frontend/.env.example frontend/.env.local
# Edit frontend/.env.local with your Supabase URL + anon key
```

### 2. Set up the database

1. Open your [Supabase project](https://app.supabase.com) → **SQL Editor**
2. Paste the entire contents of `docs/schema.sql`
3. Click **Run**
4. Verify: you should see tables `organizations`, `users`, `documents`, `document_chunks`, `query_logs` in the Table Editor

### 3. Run the backend

```bash
cd backend

# Install uv (fast Python package manager)
pip install uv

# Create virtualenv and install deps
uv venv
uv pip install -e .

# Activate venv (Windows)
.venv\Scripts\activate

# Start dev server
uvicorn main:app --reload --port 8000
```

Backend will be available at `http://localhost:8000`
- API docs: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/health`

### 4. Run the frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend will be available at `http://localhost:3000`

### 5. Test the full flow

1. Create an organization and admin user in Supabase Auth
2. Upload a PDF via the dashboard
3. Watch status change from `processing` → `ready`
4. Ask a question in the chat tab
5. View analytics in the dashboard

---

## Environment Variables Reference

### Backend (`backend/.env`)

| Variable | Required | Description |
|----------|----------|-------------|
| `SUPABASE_URL` | ✅ | Your Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | ✅ | Service role key (bypasses RLS) — keep secret |
| `SUPABASE_ANON_KEY` | ✅ | Public anon key |
| `VOYAGE_API_KEY` | ✅* | Voyage AI key for embeddings |
| `OPENAI_API_KEY` | ✅* | OpenAI key (fallback if no Voyage key) |
| `ANTHROPIC_API_KEY` | ✅ | Anthropic Claude key |
| `CLAUDE_MODEL` | ❌ | Defaults to `claude-sonnet-4-5` |
| `EMBEDDING_DIMENSION` | ❌ | `1024` (Voyage) or `1536` (OpenAI) |
| `SLACK_BOT_TOKEN` | ❌ | Required for Slack bot only |
| `SLACK_SIGNING_SECRET` | ❌ | Required for Slack bot only |
| `SLACK_APP_TOKEN` | ❌ | Required for Slack bot Socket Mode |
| `QUERY_RATE_LIMIT` | ❌ | Defaults to `10/minute` |
| `MAX_RETRIEVED_CHUNKS` | ❌ | Defaults to `5` |
| `CORS_ORIGINS` | ❌ | Comma-separated allowed origins |

*One of `VOYAGE_API_KEY` or `OPENAI_API_KEY` is required.

### Frontend (`frontend/.env.local`)

| Variable | Required | Description |
|----------|----------|-------------|
| `NEXT_PUBLIC_SUPABASE_URL` | ✅ | Supabase project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | ✅ | Supabase anon/public key |
| `NEXT_PUBLIC_BACKEND_URL` | ✅ | Backend URL (local: `http://localhost:8000`) |

---

## Deployment

### Backend → Railway

1. Push to GitHub
2. Create a new Railway project → "Deploy from GitHub repo"
3. Select the `backend/` directory as root (or use the provided `railway.toml`)
4. Add all environment variables from `backend/.env.example` in Railway's settings
5. Railway will auto-detect the `Dockerfile` and build

### Frontend → Vercel

1. Push to GitHub
2. Create a new Vercel project → import repo
3. Set **Root Directory** to `frontend/`
4. Add environment variables from `frontend/.env.example`
5. Deploy

---

## API Endpoints

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/health` | None | Health check |
| POST | `/api/documents/upload` | Admin JWT | Upload + index a document |
| GET | `/api/documents` | Admin JWT | List org's documents |
| GET | `/api/documents/{id}/status` | Admin JWT | Poll ingestion status |
| DELETE | `/api/documents/{id}` | Admin JWT | Delete doc + chunks |
| POST | `/api/query` | User JWT | Ask a question (RAG) |

---

## Evaluation (RAGAS)

The project includes a [RAGAS](https://docs.ragas.io/)-based evaluation suite that measures retrieval and generation quality **without changing any application behavior**. It lives in `backend/evaluation/` and is installed as an optional dependency group so the production Docker image stays lean.

### Metrics

| Metric | What it measures |
|--------|-----------------|
| **Faithfulness** | Is the generated answer grounded in the retrieved contexts? |
| **Response Relevancy** | Does the answer directly address the user's question? |
| **Context Precision** | Are the most relevant chunks ranked highest? |
| **Context Recall** | Did the retriever fetch all the information needed to answer? |

### Quick Start

```bash
cd backend

# 1. Install eval dependencies (in addition to the main app deps)
uv pip install -e ".[eval]"

# 2. Make sure backend/.env has GROQ_API_KEY, VOYAGE_API_KEY, and EVAL_ORG_ID set
#    EVAL_ORG_ID should be the UUID of an org that already has documents indexed.

# 3. Build the evaluation dataset (runs each question through the real pipeline)
python -m evaluation.build_dataset
#    → outputs: evaluation/results/eval_dataset.json

# 4. Run RAGAS metrics
python -m evaluation.run_ragas
#    → outputs: evaluation/results/ragas_scores.json
#               evaluation/results/ragas_scores.csv
```

### Notes

- The `eval` dependency group includes `ragas`, `langchain-groq`, and `langchain-voyageai`. These are **not** installed in the Railway Docker image.
- **Groq free-tier rate limits**: `build_dataset.py` pauses between queries (configurable via `EVAL_QUERY_DELAY` env var, default 6 s). `run_ragas.py` uses `RunConfig(max_workers=2, max_retries=10)` to stay within limits.
- The 10 sample questions in `evaluation/dataset/eval_questions.json` are **placeholder data** — replace them with real questions and ground-truth answers from your organisation's uploaded documents for meaningful results.
- `evaluation/results/` is git-ignored; results are generated locally and may contain org-specific data.

---

## Key Design Decisions

- **No LangChain/LlamaIndex**: chunking, embedding, and retrieval are written directly for debuggability and easy client demos
- **pgvector HNSW**: no training step, online inserts, excellent recall at < 1M chunks
- **Voyage AI embeddings**: consistently outperforms OpenAI on retrieval benchmarks; swappable via env var
- **Claude with strict prompt**: system prompt explicitly forbids hallucination and instructs the model to punt to HR/IT when context is insufficient
- **Multi-tenant from day 1**: every table scoped by `org_id`; RLS enforced; service-role key used only server-side

---

## Slack Setup

See [`docs/slack_setup.md`](docs/slack_setup.md) for the full Slack app configuration guide.

---

## Contributing

1. Backend formatting: `ruff format` + `ruff check`
2. Frontend formatting: `prettier` + `eslint`
3. No secrets in code — use `.env` files only
