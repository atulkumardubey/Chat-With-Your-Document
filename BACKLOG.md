# Product Backlog — Chat With Your Document

> **Stack:** FastAPI · pgvector · NVIDIA NIM · React · PostgreSQL  
> **Priority:** P1 = Must Have · P2 = Should Have · P3 = Nice to Have  
> **Effort:** S = Small (< 1 day) · M = Medium (1–3 days) · L = Large (3–7 days) · XL = Extra Large (> 1 week)

---

## Epic 1 — Document Management

| # | User Story | Priority | Effort | Status |
|---|-----------|----------|--------|--------|
| 1.1 | Upload PDF and Excel documents and index them for Q&A | P1 | L | ✅ Done |
| 1.2 | View list of uploaded documents with indexing status | P1 | S | ✅ Done |
| 1.3 | Delete a document and remove all its indexed data | P1 | S | ✅ Done |
| 1.4 | Upload multiple files at once (batch upload) | P2 | M | 🔲 Backlog |
| 1.5 | Support additional file types: Word (.docx), PowerPoint (.pptx), CSV | P2 | L | 🔲 Backlog |
| 1.6 | Re-index an existing document without re-uploading | P2 | M | 🔲 Backlog |
| 1.7 | Organize documents into folders / collections | P2 | L | 🔲 Backlog |
| 1.8 | Set a custom display name and description per document | P3 | S | 🔲 Backlog |
| 1.9 | Document version history — upload a new version of an existing file | P3 | L | 🔲 Backlog |
| 1.10 | Import documents directly from Google Drive / OneDrive / S3 | P3 | XL | 🔲 Backlog |

---

## Epic 2 — Chat and Retrieval

| # | User Story | Priority | Effort | Status |
|---|-----------|----------|--------|--------|
| 2.1 | Ask questions in plain English and get grounded answers with citations | P1 | L | ✅ Done |
| 2.2 | Scope chat to a single document or query across all documents | P1 | M | ✅ Done |
| 2.3 | Display source citations with page/sheet reference and snippet | P1 | M | ✅ Done |
| 2.4 | Refuse to answer questions not covered by the uploaded documents | P1 | M | ✅ Done |
| 2.5 | Strip LLM chain-of-thought / thinking process from responses | P1 | S | ✅ Done |
| 2.6 | Follow-up questions — maintain conversation context (multi-turn) | P1 | L | 🔲 Backlog |
| 2.7 | Keyword + semantic hybrid search for better retrieval precision | P2 | L | 🔲 Backlog |
| 2.8 | User can set Top-K and similarity threshold from the UI | P2 | M | 🔲 Backlog |
| 2.9 | Export full chat history as PDF or Markdown | P2 | M | 🔲 Backlog |
| 2.10 | Suggested follow-up questions after each assistant response | P2 | M | 🔲 Backlog |
| 2.11 | Copy answer to clipboard with one click | P2 | S | 🔲 Backlog |
| 2.12 | Thumbs up / thumbs down feedback per answer (RLHF signal) | P3 | M | 🔲 Backlog |
| 2.13 | Select different LLM models per conversation | P3 | M | 🔲 Backlog |
| 2.14 | Custom system prompt per document or collection | P3 | M | 🔲 Backlog |

---

## Epic 3 — Ingestion and Parsing

| # | User Story | Priority | Effort | Status |
|---|-----------|----------|--------|--------|
| 3.1 | Extract text and tables from PDFs | P1 | M | ✅ Done |
| 3.2 | Caption charts and images using Vision LLM | P1 | M | ✅ Done |
| 3.3 | Parse Excel files with multi-sheet support | P1 | M | ✅ Done |
| 3.4 | Async background indexing — UI polls for completion | P1 | M | ✅ Done |
| 3.5 | HNSW vector index for fast similarity search | P1 | S | ✅ Done |
| 3.6 | OCR for scanned PDFs (images-only, no text layer) | P2 | L | 🔲 Backlog |
| 3.7 | Semantic / topic-aware chunking to reduce context bleed | P2 | L | 🔲 Backlog |
| 3.8 | Configurable chunk size and overlap per document type | P2 | M | 🔲 Backlog |
| 3.9 | Detect and skip duplicate documents at upload time | P2 | M | 🔲 Backlog |
| 3.10 | Show ingestion progress percentage (not just indexing / indexed) | P3 | M | 🔲 Backlog |
| 3.11 | Support password-protected PDFs | P3 | M | 🔲 Backlog |

---

## Epic 4 — RAG Quality Gate (Evaluation)

| # | User Story | Priority | Effort | Status |
|---|-----------|----------|--------|--------|
| 4.1 | LLM-as-judge scoring: Faithfulness, Answer Relevance, Context Precision, Context Recall | P1 | L | ✅ Done |
| 4.2 | Correct refusal rate scoring for unanswerable questions | P1 | M | ✅ Done |
| 4.3 | SHIP / FIX verdict with configurable release thresholds | P1 | S | ✅ Done |
| 4.4 | Top-5 failure classification: retrieval_miss, chunking_problem, generation_error | P1 | M | ✅ Done |
| 4.5 | Run evaluation from the UI with live SSE progress stream | P1 | L | ✅ Done |
| 4.6 | Quality Gate report viewer in the UI (scorecard + per-question results) | P1 | L | ✅ Done |
| 4.7 | Parallel evaluation — 4 concurrent questions × 4 concurrent judge calls | P1 | M | ✅ Done |
| 4.8 | Hand-crafted Q&A files per document (fast path, no auto-generation) | P1 | S | ✅ Done |
| 4.9 | Auto-detect document-specific questions file by naming convention | P1 | S | ✅ Done |
| 4.10 | Historical report comparison — track metric trends across runs | P2 | L | 🔲 Backlog |
| 4.11 | CI/CD integration — exit code 1 on FIX verdict, post scorecard to PR | P2 | M | 🔲 Backlog |
| 4.12 | A/B test two chunking strategies and compare scorecard side by side | P2 | L | 🔲 Backlog |
| 4.13 | Auto-generate Q&A pairs from any document at upload time | P3 | M | 🔲 Backlog |
| 4.14 | Benchmark leaderboard — compare multiple documents or model configs | P3 | L | 🔲 Backlog |

---

## Epic 5 — User Interface

| # | User Story | Priority | Effort | Status |
|---|-----------|----------|--------|--------|
| 5.1 | Dark / light theme toggle | P1 | S | ✅ Done |
| 5.2 | Sidebar with document list, search, and status indicators | P1 | M | ✅ Done |
| 5.3 | Expandable source citations per answer | P1 | M | ✅ Done |
| 5.4 | Upload drag-and-drop panel with file format validation | P1 | S | ✅ Done |
| 5.5 | Quality Gate report modal (scorecard + top failures + per-question drill-down) | P1 | L | ✅ Done |
| 5.6 | Eval run modal with live progress bar and per-question results | P1 | L | ✅ Done |
| 5.7 | Mobile-responsive layout | P2 | L | 🔲 Backlog |
| 5.8 | Keyboard shortcut: Ctrl+K to open document search | P2 | S | 🔲 Backlog |
| 5.9 | Pinned / favourite documents at top of sidebar | P2 | S | 🔲 Backlog |
| 5.10 | Onboarding tour for first-time users | P3 | M | 🔲 Backlog |
| 5.11 | Customisable accent colour / branding per tenant | P3 | M | 🔲 Backlog |

---

## Epic 6 — Security and Multi-User

| # | User Story | Priority | Effort | Status |
|---|-----------|----------|--------|--------|
| 6.1 | User registration and login (email + password) | P1 | L | 🔲 Backlog |
| 6.2 | JWT-based session management | P1 | M | 🔲 Backlog |
| 6.3 | Each user sees only their own documents | P1 | M | 🔲 Backlog |
| 6.4 | Role-based access: Admin, Editor, Viewer | P2 | L | 🔲 Backlog |
| 6.5 | Share a document collection with specific users | P2 | L | 🔲 Backlog |
| 6.6 | SSO via OAuth 2.0 (Google, Microsoft, GitHub) | P2 | L | 🔲 Backlog |
| 6.7 | Audit log — who uploaded, deleted, or queried which document | P2 | M | 🔲 Backlog |
| 6.8 | Per-user API rate limiting and storage quota | P3 | M | 🔲 Backlog |
| 6.9 | Data-at-rest encryption for stored documents and embeddings | P3 | L | 🔲 Backlog |

---

## Epic 7 — Infrastructure and DevOps

| # | User Story | Priority | Effort | Status |
|---|-----------|----------|--------|--------|
| 7.1 | Docker Compose setup for local development (API + DB + frontend) | P1 | M | 🔲 Backlog |
| 7.2 | Production Dockerfile for API and frontend | P1 | M | 🔲 Backlog |
| 7.3 | Environment-based configuration (dev / staging / prod) | P1 | S | 🔲 Backlog |
| 7.4 | Health check endpoint (`GET /health`) | P1 | S | 🔲 Backlog |
| 7.5 | Structured JSON logging with request IDs | P2 | M | 🔲 Backlog |
| 7.6 | Prometheus metrics + Grafana dashboard (latency, error rate, token usage) | P2 | L | 🔲 Backlog |
| 7.7 | GitHub Actions CI pipeline — lint, type-check, quality gate on every PR | P2 | M | 🔲 Backlog |
| 7.8 | Database migration framework (Alembic) | P2 | M | 🔲 Backlog |
| 7.9 | Horizontal scaling — stateless API behind a load balancer | P3 | XL | 🔲 Backlog |
| 7.10 | Redis caching for repeated embedding lookups | P3 | M | 🔲 Backlog |
| 7.11 | Kubernetes Helm chart for cloud deployment | P3 | XL | 🔲 Backlog |

---

## Epic 8 — Analytics and Observability

| # | User Story | Priority | Effort | Status |
|---|-----------|----------|--------|--------|
| 8.1 | Usage dashboard — questions asked per document, per day | P2 | M | 🔲 Backlog |
| 8.2 | Token usage tracker — cost estimation per query | P2 | M | 🔲 Backlog |
| 8.3 | Most-asked questions report per document | P2 | M | 🔲 Backlog |
| 8.4 | Similarity score histogram — understand retrieval quality at a glance | P2 | S | 🔲 Backlog |
| 8.5 | Alert when quality gate score drops below threshold across runs | P3 | M | 🔲 Backlog |
| 8.6 | LLM latency percentile tracking (p50 / p95 / p99) | P3 | M | 🔲 Backlog |

---

## Summary

| Status | Count |
|--------|-------|
| ✅ Done | 27 |
| 🔲 Backlog | 43 |
| **Total** | **70** |

---

*Last updated: September 2026*
