"""Auto-generate a golden Q&A set from any uploaded document's indexed chunks.

Flow:
  1. Fetch all chunks for the document from the DB.
  2. Sample n_answerable diverse chunks (skip ones that are too short to make a good question).
  3. Call the LLM to produce one factual Q&A pair per chunk.
  4. Call the LLM once more to produce n_unanswerable out-of-scope questions.

Usage:
    from eval.question_generator import generate_qa_pairs
    pairs = generate_qa_pairs(doc_id=3)
"""

import json
import logging
import random

import psycopg2.extras

from app.config import settings
from app.db import get_connection
from app.llm.nvidia_client import _client, _strip_thinking

logger = logging.getLogger(__name__)

MIN_CHUNK_LENGTH = 60  # Chunks shorter than this rarely make meaningful questions

# ── LLM prompt templates ──────────────────────────────────────────────────────

_QA_SYSTEM = """You are a test-dataset creator for a RAG evaluation.

Given a text passage, generate ONE factual question whose answer can be found ONLY in that passage, plus the exact answer.

Rules:
- Question must be specific (asks for a number, name, comparison, or concrete fact).
- Answer must be directly extractable from the passage — no paraphrasing beyond necessary.
- Do NOT ask about the passage's structure or formatting.

Respond with ONLY valid JSON, no other text:
{"question": "<question text>", "answer": "<exact answer from passage>"}"""

_UNANSWERABLE_SYSTEM = """You are a test-dataset creator for a RAG evaluation.

Given sample excerpts from a document, produce exactly {n} questions that this document CANNOT answer — plausible things a user might ask but that fall entirely outside the document's scope.

Respond with ONLY valid JSON, no other text:
{"questions": ["<question 1>", "<question 2>", ...]}"""

# Generic fallbacks in case the LLM refuses to produce unanswerable questions
_FALLBACK_UNANSWERABLE = [
    "What is the CEO's personal email address?",
    "What is the current stock price of this company?",
    "When was this company originally founded?",
    "How many employees work in the marketing department?",
    "What is the company's credit rating?",
    "What is the office phone number?",
]


# ── DB helpers ────────────────────────────────────────────────────────────────

def get_document_info(doc_id: int) -> dict | None:
    """Return the documents row for doc_id, or None if not found."""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT id, name, type, pages, sheets, status FROM documents WHERE id = %s",
                (doc_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None


def list_documents() -> list[dict]:
    """Return all indexed documents (id, name, type, status)."""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT id, name, type, pages, sheets, status, uploaded_at"
                " FROM documents ORDER BY uploaded_at DESC"
            )
            return [dict(r) for r in cur.fetchall()]


def _get_chunks(doc_id: int) -> list[dict]:
    """Fetch all chunks for a document (id, content, metadata)."""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT id, content, metadata FROM chunks WHERE document_id = %s ORDER BY id",
                (doc_id,),
            )
            return [dict(r) for r in cur.fetchall()]


# ── LLM calls ────────────────────────────────────────────────────────────────

def _llm(system: str, user: str, temperature: float = 0.3) -> str:
    response = _client.chat.completions.create(
        model=settings.nvidia_llm_model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
    )
    return _strip_thinking(response.choices[0].message.content or "")


def _generate_qa_from_chunk(content: str) -> dict | None:
    """Ask the LLM to produce {"question": ..., "answer": ...} for one chunk."""
    try:
        raw = _llm(_QA_SYSTEM, f"Text passage:\n\n{content}")
        data = json.loads(raw)
        q = data.get("question", "").strip()
        a = data.get("answer", "").strip()
        if q and a:
            return {"question": q, "answer": a}
    except Exception as e:
        logger.warning(f"Q&A generation failed for chunk: {e}")
    return None


def _generate_unanswerable(chunks: list[dict], n: int) -> list[str]:
    """Ask the LLM to produce n questions the document cannot answer."""
    sample = random.sample(chunks, min(6, len(chunks)))
    doc_excerpt = "\n---\n".join(c["content"][:250] for c in sample)
    try:
        raw = _llm(
            _UNANSWERABLE_SYSTEM.format(n=n),
            f"Document excerpt samples:\n\n{doc_excerpt}\n\nGenerate {n} unanswerable questions.",
            temperature=0.5,
        )
        data = json.loads(raw)
        questions = [q.strip() for q in data.get("questions", []) if q.strip()]
        if len(questions) >= n:
            return questions[:n]
    except Exception as e:
        logger.warning(f"Unanswerable question generation failed: {e}")

    # Fallback: return generic ones
    return random.sample(_FALLBACK_UNANSWERABLE, min(n, len(_FALLBACK_UNANSWERABLE)))


# ── Public API ────────────────────────────────────────────────────────────────

def generate_qa_pairs(
    doc_id: int,
    n_answerable: int = 16,
    n_unanswerable: int = 4,
) -> list[dict]:
    """Generate a golden Q&A set for an already-indexed document.

    Args:
        doc_id: Primary key of the document in the `documents` table.
        n_answerable: How many answerable Q&A pairs to generate (default 16).
        n_unanswerable: How many deliberately unanswerable questions to add (default 4).

    Returns:
        List of dicts with keys:
            id, question, reference (str or None), source_type, answerable (bool)

    Raises:
        ValueError: if the document does not exist or is not yet indexed.
    """
    doc = get_document_info(doc_id)
    if not doc:
        raise ValueError(f"Document {doc_id} not found.")
    if doc["status"] != "indexed":
        raise ValueError(
            f"Document {doc_id} has status '{doc['status']}'; wait for indexing to complete."
        )

    logger.info(f"Fetching chunks for '{doc['name']}' (doc_id={doc_id})...")
    all_chunks = _get_chunks(doc_id)
    if not all_chunks:
        raise ValueError(f"Document {doc_id} has no indexed chunks.")

    # Only use chunks that are long enough to produce a meaningful question
    usable = [c for c in all_chunks if len(c["content"].strip()) >= MIN_CHUNK_LENGTH]
    if not usable:
        usable = all_chunks  # Fallback

    actual_n = min(n_answerable, len(usable))
    if actual_n < n_answerable:
        logger.warning(
            f"Only {actual_n} usable chunks (< {n_answerable}); "
            f"will generate {actual_n} answerable pairs."
        )

    sampled = random.sample(usable, actual_n)
    logger.info(f"Sampled {actual_n} chunks from {len(usable)} usable; generating Q&A pairs...")

    qa_pairs: list[dict] = []

    for i, chunk in enumerate(sampled, 1):
        logger.info(f"  [{i}/{actual_n}] Generating Q&A...")
        qa = _generate_qa_from_chunk(chunk["content"])
        if qa:
            qa_pairs.append(
                {
                    "id": len(qa_pairs) + 1,
                    "question": qa["question"],
                    "reference": qa["answer"],
                    "source_type": doc["type"],  # 'pdf' or 'excel'
                    "answerable": True,
                }
            )

    logger.info(
        f"Generated {len(qa_pairs)}/{actual_n} answerable pairs "
        f"({actual_n - len(qa_pairs)} skipped due to LLM parse errors)."
    )

    # Unanswerable questions
    logger.info(f"Generating {n_unanswerable} unanswerable questions...")
    unanswerable_qs = _generate_unanswerable(all_chunks, n_unanswerable)
    for q in unanswerable_qs:
        qa_pairs.append(
            {
                "id": len(qa_pairs) + 1,
                "question": q,
                "reference": None,
                "source_type": "refusal",
                "answerable": False,
            }
        )

    logger.info(
        f"Golden set ready: {len(qa_pairs)} pairs "
        f"({len(qa_pairs) - n_unanswerable} answerable, {n_unanswerable} unanswerable)"
    )
    return qa_pairs
