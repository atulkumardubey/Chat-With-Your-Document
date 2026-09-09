"""RAG Quality Gate: Comprehensive evaluation with LLM-as-judge metrics.

Uploads the eval fixture documents through the full ingestion pipeline (parse →
chunk → embed → store), then runs every golden-set question against those specific
documents and scores the answers with RAGAS-style LLM-as-judge metrics.

Run:
    python -m eval.run_quality_gate
"""

import json
import logging
import sys
from pathlib import Path
from typing import Any

from app.config import settings
from app.db import get_connection
from app.ingestion.chunkers import chunk_units
from app.ingestion.excel_parser import get_sheet_count, parse_excel
from app.ingestion.pdf_parser import get_page_count, parse_pdf
from app.ingestion.embedder import embed_query
from app.llm.prompts import build_user_prompt
from app.llm.nvidia_client import chat_completion
from app.retrieval.vector_store import insert_chunks, search

from eval.judge import (
    is_correct_refusal,
    score_answer_relevance,
    score_context_precision,
    score_context_recall,
    score_faithfulness,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# Names used in the documents table — prefixed so they don't collide with user uploads
EVAL_PDF_NAME = "[eval] sample.pdf"
EVAL_EXCEL_NAME = "[eval] sample.xlsx"

# Maps golden-set source_type → which fixture document to query against
SOURCE_TO_DOC_TYPE: dict[str, str | None] = {
    "pdf_text": "pdf",
    "pdf_table": "pdf",
    "pdf_chart": "pdf",
    "excel_sheet1": "excel",
    "excel_sheet2": "excel",
    "refusal": None,  # Unanswerable — no doc scoping needed
}

# Quality thresholds — if ANY metric falls below, the result is FIX (do not ship)
THRESHOLDS = {
    "faithfulness": 0.70,
    "answer_relevance": 0.70,
    "context_precision": 0.60,
    "context_recall": 0.60,
    "correct_refusal_rate": 1.00,
}

RETRIEVAL_MISS_THRESHOLD = settings.similarity_threshold
CHUNKING_PROBLEM_THRESHOLD = 0.40
GENERATION_ERROR_THRESHOLD = 0.50


# ---------------------------------------------------------------------------
# Document ingestion
# ---------------------------------------------------------------------------

def _delete_existing_eval_docs() -> None:
    """Remove any leftover quality-gate docs from a previous run so each run is clean."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM documents WHERE name IN (%s, %s)",
                (EVAL_PDF_NAME, EVAL_EXCEL_NAME),
            )


def _insert_document(name: str, doc_type: str, pages: int | None, sheets: int | None) -> int:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO documents (name, type, pages, sheets, status)"
                " VALUES (%s, %s, %s, %s, 'indexed') RETURNING id",
                (name, doc_type, pages, sheets),
            )
            return cur.fetchone()[0]


def ingest_fixtures() -> dict[str, int]:
    """Upload fixture docs through the full ingestion pipeline.

    Returns:
        {"pdf": <doc_id>, "excel": <doc_id>}
    """
    logger.info("Removing any previous quality-gate eval documents...")
    _delete_existing_eval_docs()

    doc_ids: dict[str, int] = {}

    # ---- PDF ----
    pdf_path = str(FIXTURES_DIR / "sample.pdf")
    pages = get_page_count(pdf_path)
    pdf_doc_id = _insert_document(EVAL_PDF_NAME, "pdf", pages, None)
    pdf_units = parse_pdf(pdf_path, EVAL_PDF_NAME)
    pdf_chunks = chunk_units(pdf_units, settings.default_chunk_strategy)
    insert_chunks(pdf_doc_id, pdf_chunks)
    doc_ids["pdf"] = pdf_doc_id
    logger.info(
        f"Ingested PDF: {len(pdf_chunks)} chunks "
        f"(strategy={settings.default_chunk_strategy}, doc_id={pdf_doc_id})"
    )

    # ---- Excel ----
    xlsx_path = str(FIXTURES_DIR / "sample.xlsx")
    sheets = get_sheet_count(xlsx_path)
    xlsx_doc_id = _insert_document(EVAL_EXCEL_NAME, "excel", None, sheets)
    xlsx_units = parse_excel(xlsx_path, EVAL_EXCEL_NAME, settings.default_excel_format)
    xlsx_chunks = chunk_units(xlsx_units, settings.default_chunk_strategy)
    insert_chunks(xlsx_doc_id, xlsx_chunks)
    doc_ids["excel"] = xlsx_doc_id
    logger.info(
        f"Ingested Excel: {len(xlsx_chunks)} chunks "
        f"(format={settings.default_excel_format}, doc_id={xlsx_doc_id})"
    )

    return doc_ids


# ---------------------------------------------------------------------------
# Evaluation helpers
# ---------------------------------------------------------------------------

def load_golden_set(path: str = "eval/golden_set.json") -> list[dict]:
    with open(path, "r") as f:
        return json.load(f)


def classify_failure(result: dict[str, Any]) -> str:
    """Return a string label for the dominant failure mode."""
    if not result.get("contexts"):
        return "retrieval_miss"
    if result.get("context_precision", 1.0) < CHUNKING_PROBLEM_THRESHOLD:
        return "chunking_problem"
    if (
        result.get("faithfulness", 1.0) < GENERATION_ERROR_THRESHOLD
        or result.get("answer_relevance", 1.0) < GENERATION_ERROR_THRESHOLD
    ):
        return "generation_error"
    return "unknown"


def evaluate_question(question_data: dict, doc_ids: dict[str, int]) -> dict:
    """Run one golden-set question through the RAG pipeline and score it.

    Retrieval is scoped to the uploaded fixture document that matches the
    question's source_type (pdf vs excel). Unanswerable questions have no
    doc-scope so the pipeline can use any document (testing correct refusal).
    """
    q_id = question_data["id"]
    question = question_data["question"]
    answerable = question_data["answerable"]
    reference = question_data.get("reference")
    source_type = question_data.get("source_type", "")

    # Resolve which uploaded document this question targets
    doc_type = SOURCE_TO_DOC_TYPE.get(source_type)
    document_id = doc_ids.get(doc_type) if doc_type else None

    result: dict[str, Any] = {
        "question_id": q_id,
        "question": question,
        "answerable": answerable,
        "source_type": source_type,
        "document_id": document_id,
        "answer": None,
        "contexts": [],
        "best_similarity": 0.0,
    }

    try:
        # Retrieve relevant chunks from the specific uploaded document
        query_embedding = embed_query(question)
        chunks = search(query_embedding, top_k=settings.top_k, document_id=document_id)
        result["contexts"] = [c["content"] for c in chunks]
        result["best_similarity"] = chunks[0]["similarity"] if chunks else 0.0

        # Generate answer using the same prompt the app uses
        context_blocks = [c["content"] for c in chunks] if chunks else []
        prompt = build_user_prompt(question, context_blocks)
        answer = chat_completion(prompt)
        result["answer"] = answer

        if answerable:
            result["faithfulness"] = score_faithfulness(answer, result["contexts"])
            result["answer_relevance"] = score_answer_relevance(question, answer)
            result["context_precision"] = score_context_precision(question, result["contexts"])
            result["context_recall"] = score_context_recall(reference, result["contexts"])

            result["all_passed"] = (
                result["faithfulness"] >= THRESHOLDS["faithfulness"]
                and result["answer_relevance"] >= THRESHOLDS["answer_relevance"]
                and result["context_precision"] >= THRESHOLDS["context_precision"]
                and result["context_recall"] >= THRESHOLDS["context_recall"]
            )
            if not result["all_passed"]:
                result["failure_type"] = classify_failure(result)
        else:
            result["is_correct_refusal"] = is_correct_refusal(answer)
            result["all_passed"] = result["is_correct_refusal"]
            if not result["all_passed"]:
                result["failure_type"] = "incorrect_answer_to_unanswerable"

    except Exception as e:
        logger.error(f"Error evaluating Q{q_id}: {e}")
        result["error"] = str(e)
        result["all_passed"] = False

    return result


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def run_quality_gate() -> int:
    """Upload fixtures, evaluate all 20 golden-set questions, print scorecard."""

    # Step 1: ensure fixture files exist
    if not (FIXTURES_DIR / "sample.pdf").exists() or not (FIXTURES_DIR / "sample.xlsx").exists():
        logger.error(
            "Fixture files not found. Run: python eval/generate_test_docs.py"
        )
        return 1

    # Step 2: ingest fixtures through the real upload pipeline
    logger.info("Ingesting fixture documents...")
    doc_ids = ingest_fixtures()

    # Step 3: load golden set
    logger.info("Loading golden set...")
    golden_set = load_golden_set()

    # Step 4: evaluate each question
    logger.info(f"Evaluating {len(golden_set)} questions...")
    all_results = []
    for q_data in golden_set:
        logger.info(f"  Q{q_data['id']:02d} ({q_data['source_type']}): {q_data['question'][:55]}...")
        result = evaluate_question(q_data, doc_ids)
        all_results.append(result)

    # Step 5: aggregate scores
    answerable = [r for r in all_results if r["answerable"]]
    unanswerable = [r for r in all_results if not r["answerable"]]
    metrics: dict[str, float] = {}

    if answerable:
        metrics["faithfulness"] = sum(r.get("faithfulness", 0.0) for r in answerable) / len(answerable)
        metrics["answer_relevance"] = sum(r.get("answer_relevance", 0.0) for r in answerable) / len(answerable)
        metrics["context_precision"] = sum(r.get("context_precision", 0.0) for r in answerable) / len(answerable)
        metrics["context_recall"] = sum(r.get("context_recall", 0.0) for r in answerable) / len(answerable)

    if unanswerable:
        correct = sum(1 for r in unanswerable if r.get("is_correct_refusal"))
        metrics["correct_refusal_rate"] = correct / len(unanswerable)

    # Step 6: print scorecard
    print("\n" + "=" * 70)
    print("RAG QUALITY GATE SCORECARD")
    print(f"  PDF doc_id={doc_ids['pdf']}  |  Excel doc_id={doc_ids['excel']}")
    print(f"  Strategy: {settings.default_chunk_strategy}  |  Excel format: {settings.default_excel_format}")
    print("=" * 70)
    print(f"{'METRIC':<24} {'SCORE':>6} {'THRESHOLD':>10} {'STATUS'}")
    print("-" * 70)

    gate_passed = True
    for metric, threshold in THRESHOLDS.items():
        if metric not in metrics:
            continue
        score = metrics[metric]
        passed = score >= threshold
        gate_passed = gate_passed and passed
        status = "PASS" if passed else "FAIL"
        print(f"{metric:<24} {score:6.2f} {threshold:>10.2f}   {status}")

    print("=" * 70)
    verdict = "SHIP" if gate_passed else "FIX"
    print(f"VERDICT: {verdict}")
    print("=" * 70 + "\n")

    # Step 7: top-5 failures
    failures = [r for r in all_results if not r.get("all_passed")]
    if failures:
        failures_sorted = sorted(
            failures,
            key=lambda r: (r.get("faithfulness", 1.0) + r.get("answer_relevance", 1.0)),
        )[:5]

        print("TOP-5 FAILURES:")
        print("-" * 70)
        for i, fail in enumerate(failures_sorted, 1):
            ftype = fail.get("failure_type", "unknown")
            print(f"{i}. Q{fail['question_id']:02d} [{fail['source_type']}] {fail['question'][:48]}")
            print(f"   Failure: {ftype}")
            if fail.get("answerable"):
                print(
                    f"   Faithfulness={fail.get('faithfulness', 0):.2f}  "
                    f"Relevance={fail.get('answer_relevance', 0):.2f}  "
                    f"Precision={fail.get('context_precision', 0):.2f}  "
                    f"Recall={fail.get('context_recall', 0):.2f}"
                )
            if fail.get("answer"):
                print(f"   Answer: {fail['answer'][:120]}...")
        print()

    # Step 8: save JSON report
    report = {
        "verdict": verdict,
        "metrics": metrics,
        "thresholds": THRESHOLDS,
        "ingestion": {
            "pdf_doc_id": doc_ids["pdf"],
            "excel_doc_id": doc_ids["excel"],
            "chunk_strategy": settings.default_chunk_strategy,
            "excel_format": settings.default_excel_format,
        },
        "summary": {
            "total": len(all_results),
            "answerable": len(answerable),
            "unanswerable": len(unanswerable),
            "passed": sum(1 for r in all_results if r.get("all_passed")),
            "failed": len(failures),
        },
        "results": all_results,
    }

    report_path = Path("eval") / "quality_gate_report.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)

    logger.info(f"Report saved to {report_path}")
    return 0 if gate_passed else 1


if __name__ == "__main__":
    sys.exit(run_quality_gate())
