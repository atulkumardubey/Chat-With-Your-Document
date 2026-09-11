# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Backend
```bash
# Start backend (auto-reloads on file change)
uvicorn app.main:app --reload

# One-time manual schema init (normally handled automatically at startup)
python Backend.py
```

### Frontend
```bash
cd frontend
npm run dev       # dev server at http://localhost:5173
npm run build     # production build
npm run preview   # preview production build
```

### Evaluation / Quality Gate
```bash
# List indexed documents
python -m eval.run_quality_gate --list

# Run quality gate with hand-crafted questions (fast)
python -m eval.run_quality_gate --doc-id <ID> --questions eval/my_questions.json

# Run quality gate with auto-generated questions (slow — one LLM call per chunk)
python -m eval.run_quality_gate --doc-id <ID>
```

There are no formal unit tests (`pytest`/`jest`). The eval suite is the primary correctness check.

## Environment Setup

Copy `.env.example` to `.env`. Required variables:

| Variable | Notes |
|---|---|
| `DB_PASSWORD` | No default — startup raises `RuntimeError` if missing |
| `NVIDIA_API_KEY` | No default — must be set |
| `EMBEDDING_DIM` | Must match the model's actual output dim (384 for bge-small-en-v1.5) |
| `DEFAULT_CHUNK_STRATEGY` | `fixed` / `recursive` / `section_aware` |
| `DEFAULT_EXCEL_FORMAT` | `rows` / `markdown` / `column` |

`app/config.py` exposes a module-level `settings` singleton — any missing required var causes an import-time crash, not a runtime one.

PostgreSQL must have the `pgvector` extension: `CREATE EXTENSION IF NOT EXISTS vector;`  
Database `ragdb` must exist before first run. Schema tables and indexes are created automatically at startup.

## Architecture

### Request Flow

```
Browser (5173)
  └─ /api/* proxy (vite.config.js)
       └─ FastAPI (8000)
            ├─ POST /api/upload          →  ingestion pipeline  →  PostgreSQL (chunks + vectors)
            ├─ POST /api/chat            →  RAG pipeline         →  NVIDIA NIM → answer + citations
            ├─ GET  /api/documents
            ├─ DELETE /api/documents/{id}
            ├─ GET  /api/quality-gate-report        (reads eval/quality_gate_report.json)
            ├─ POST /api/quality-gate/run           (starts background thread, returns run_id)
            └─ GET  /api/quality-gate/run/{id}/events  (SSE stream)
```

### Backend Package (`app/`)

| Layer | Path | Role |
|---|---|---|
| Config | `app/config.py` | `Settings` dataclass, reads `.env` via python-dotenv |
| DB | `app/db.py` | psycopg2 helpers, inline DDL (`init_schema`), no migrations |
| Routes | `app/api/routes_documents.py`, `routes_chat.py`, `routes_quality_gate.py` | Thin HTTP handlers; delegate to services |
| Ingestion | `app/ingestion/` | Parse → chunk → embed → store |
| Retrieval | `app/retrieval/` | Vector search + RAG orchestration |
| LLM | `app/llm/` | NVIDIA NIM client (OpenAI-compat SDK), system/user prompts |

### Ingestion Pipeline (Upload)

1. `pdf_parser.py` — pdfplumber for text/tables per page; PyMuPDF extracts images ≥100 px (max 5/doc) → NVIDIA vision model captions them (45 s timeout per image; base64 data URLs)
2. `excel_parser.py` — pandas reads all sheets, serialized per `DEFAULT_EXCEL_FORMAT`
3. `chunkers.py` — three strategies (see table below)
4. `embedder.py` — `SentenceTransformer` lazy-loaded via `@lru_cache`; `normalize_embeddings=True`
5. `vector_store.py` — bulk insert into `chunks` with pgvector `VECTOR(384)` column

**Chunker strategies:**

| Strategy | Default size | Behavior |
|---|---|---|
| `fixed` | 1000 chars | Naive sliding window with 100-char overlap; ignores semantic boundaries |
| `recursive` | 800 chars | LangChain `RecursiveCharacterTextSplitter`; preserves sentence/paragraph boundaries |
| `section_aware` | 1200 chars max | Keeps each page/table/sheet whole if it fits; falls back to recursive only when a unit exceeds `max_chunk_size`. Best for structured documents |

`chunk_units()` raises `ValueError` on unknown strategy names. Default is controlled by `DEFAULT_CHUNK_STRATEGY`.

### RAG Pipeline (Chat)

`app/retrieval/retriever.py` → `retrieve_and_answer`:

1. Embed the question with `embed_query`
2. Cosine ANN search via HNSW index: `embedding <=> query_vector`
3. **Threshold gate**: top result similarity < `SIMILARITY_THRESHOLD` (default 0.35) → return `REFUSAL_MESSAGE`, skip LLM
4. Build prompt via `app/llm/prompts.py` (`SYSTEM_PROMPT` + `build_user_prompt`)
5. Call NVIDIA NIM (`NVIDIA_LLM_MODEL`); strip `<think>` chain-of-thought from response
6. Return `{content, citations}` — citations carry `source`, `page`/`sheet+row`, `snippet[:280]`

### LLM Client (`app/llm/nvidia_client.py`)

- Module-level singleton `_client = OpenAI(base_url=..., api_key=...)` shared by all callers, including the eval judge
- **No retries configured** — a single API failure surfaces as an exception
- **No streaming** — all calls use blocking `chat.completions.create()`
- Think-tag stripping removes `<think>…</think>` blocks (multiline regex) and loose "thinking process / internal reasoning" header patterns before returning
- `SYSTEM_PROMPT` embeds the exact `REFUSAL_MESSAGE` string and instructs the model to copy it verbatim — this is intentional tight coupling that makes `is_correct_refusal()` safe as an exact-match check. Always import `REFUSAL_MESSAGE` from `app/llm/prompts.py`, never define it elsewhere
- Chat calls use `temperature=0.2`; judge calls use `temperature=0.0`

### Database Schema

Two tables, no migration tooling — schema lives in `app/db.py`:

- **`documents`** — `id, name, type, pages, sheets, status, error, uploaded_at`
- **`chunks`** — `id, document_id (FK cascade), content, metadata (JSONB), embedding VECTOR(384), chunk_strategy, source_format, created_at`

Key indexes: HNSW cosine on `embedding`, btree on `document_id`, btree on `uploaded_at DESC`.

### Frontend (`frontend/src/`)

All state lives in `App.jsx`:
- `messagesByDoc` — `Record<docId | 'all', Message[]>`. Key is the integer doc id, or the string `'all'` when no document is selected. Each document has an independent chat history
- `activeDoc` — the currently selected document object (or `null` for "all docs" mode)
- Theme (`'dark'` | `'light'`) toggled via CSS class on `<div class="app-root">` — all colors are CSS custom properties scoped to `.app-root.dark` / `.app-root.light` in `App.css`

**Upload flow:** a placeholder doc with id `pending-${Date.now()}` is inserted into state immediately, then replaced with the real integer id from the POST response. The frontend polls `/api/documents` every 5 s (up to 60 polls / 5 min). When `status === 'indexed'`, a `role: 'system'` message is appended — rendered as a doc-ready card by `MessageBubble.jsx`.

**In-flight safety:** the doc key is captured at send time, so replies from a slow request always land in the correct thread even if the user switches documents mid-flight.

**Eval modals:** `EvalRunModal` (run trigger) only renders when `showEvalRun && activeDoc` — it requires an active document. `QualityGateReport` (read-only report viewer) has no such requirement.

### Eval System (`eval/`)

- `judge.py` — LLM-as-judge scoring: faithfulness, answer_relevance, context_precision, context_recall. All four return `0.0` on any JSON parse failure (silent degradation)
- `question_generator.py` — samples up to 16 chunks (filters those under 60 chars), fires one LLM call per chunk sequentially for answerable Q&A; generates unanswerable questions in a single batch call
- `my_questions.json` — hand-crafted golden Q&A pairs for regression testing; must match the indexed document or all answerable questions will fail
- `fixtures/` — gitignored sample files for local eval runs

**Eval thresholds** (hardcoded in `run_quality_gate.py`):

| Metric | Threshold |
|---|---|
| faithfulness | ≥ 0.70 |
| answer_relevance | ≥ 0.70 |
| context_precision | ≥ 0.60 |
| context_recall | ≥ 0.60 |
| correct_refusal_rate | = 1.00 |

**Failure classification:** `retrieval_miss` (no contexts returned) → `chunking_problem` (context_precision < 0.40) → `generation_error` (faithfulness or relevance < 0.50) → `unknown`.

**Concurrency:** questions are parallelized with `ThreadPoolExecutor(max_workers=4)`; the four judge calls per question are also parallelized with 4 workers — peak concurrency is 16 simultaneous LLM calls.

**Report file:** always written to `eval/quality_gate_report.json` (path resolved relative to `routes_quality_gate.py` via `Path(__file__).resolve().parents[2]`). File is always overwritten — no versioning, no atomic write.

**Run state:** in-memory dict `_runs` keyed by UUID in `routes_quality_gate.py`. A server restart loses all in-progress run state. SSE stream yields `: keepalive\n\n` every 0.3 s while the worker is busy.

### `document_id` Flow

The integer primary key assigned by Postgres on insert flows through every layer:

- **Upload** → response body → frontend replaces `pending-*` placeholder
- **Chat** → `selectedDocId` in POST body → retriever filters `chunks` by `document_id`
- **Eval** → `--doc-id` CLI arg or `doc_id` in route body → scopes vector search to single document, preventing cross-document contamination
