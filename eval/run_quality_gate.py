"""RAG Quality Gate: Comprehensive evaluation with LLM-as-judge metrics.

Two modes:

  Document mode (recommended):
    Pass an already-uploaded document's ID.  The script auto-generates a golden
    Q&A set from the document's indexed chunks, then evaluates the RAG pipeline
    against those questions — scoped to that document only.

        python -m eval.run_quality_gate --doc-id 3

    Use --list to see available documents.

  Fixture mode (CI / regression baseline):
    No arguments — uploads the synthetic fixture files (sample.pdf + sample.xlsx)
    and evaluates against the hand-crafted golden_set.json.

        python -m eval.run_quality_gate
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

import psycopg2.extras

from app.config import settings
from app.db import get_connection
from app.ingestion.chunkers import chunk_units
from app.ingestion.embedder import embed_query
from app.ingestion.excel_parser import get_sheet_count, parse_excel
from app.ingestion.pdf_parser import get_page_count, parse_pdf
from app.llm.nvidia_client import chat_completion
from app.llm.prompts import build_user_prompt
from app.retrieval.vector_store import insert_chunks, search

from eval.judge import (
    is_correct_refusal,
    score_answer_relevance,
    score_context_precision,
    score_context_recall,
    score_faithfulness,
)
from eval.question_generator import (
    generate_qa_pairs,
    get_document_info,
    list_documents,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
GOLDEN_SET_PATH = Path(__file__).parent / "golden_set.json"

# Fixture document names (prefixed to avoid colliding with real user uploads)
EVAL_PDF_NAME = "[eval] sample.pdf"
EVAL_EXCEL_NAME = "[eval] sample.xlsx"

# Maps golden_set source_type → fixture document type (fixture mode only)
SOURCE_TO_DOC_TYPE: dict[str, str | None] = {
    "pdf_text": "pdf",
    "pdf_table": "pdf",
    "pdf_chart": "pdf",
    "excel_sheet1": "excel",
    "excel_sheet2": "excel",
    "refusal": None,
}

# ── Quality thresholds ────────────────────────────────────────────────────────

THRESHOLDS = {
    "faithfulness": 0.70,
    "answer_relevance": 0.70,
    "context_precision": 0.60,
    "context_recall": 0.60,
    "correct_refusal_rate": 1.00,
}

RETRIEVAL_MISS_SIMILARITY = settings.similarity_threshold
CHUNKING_PROBLEM_PRECISION = 0.40
GENERATION_ERROR_SCORE = 0.50


# ── Failure classification ────────────────────────────────────────────────────

def classify_failure(result: dict[str, Any]) -> str:
    if not result.get("contexts"):
        return "retrieval_miss"
    if result.get("context_precision", 1.0) < CHUNKING_PROBLEM_PRECISION:
        return "chunking_problem"
    if (
        result.get("faithfulness", 1.0) < GENERATION_ERROR_SCORE
        or result.get("answer_relevance", 1.0) < GENERATION_ERROR_SCORE
    ):
        return "generation_error"
    return "unknown"


# ── Core evaluation ───────────────────────────────────────────────────────────

def evaluate_question(question_data: dict, document_id: int | None) -> dict:
    """Run one Q&A pair through the RAG pipeline and score it.

    Args:
        question_data: Dict with keys: id, question, reference, answerable.
        document_id: Scope retrieval to this document (None = search all docs).

    Returns:
        Result dict with all per-question scores and metadata.
    """
    q_id = question_data["id"]
    question = question_data["question"]
    answerable = question_data["answerable"]
    reference = question_data.get("reference")

    result: dict[str, Any] = {
        "question_id": q_id,
        "question": question,
        "answerable": answerable,
        "source_type": question_data.get("source_type", ""),
        "document_id": document_id,
        "answer": None,
        "contexts": [],
        "best_similarity": 0.0,
    }

    try:
        query_embedding = embed_query(question)
        chunks = search(query_embedding, top_k=settings.top_k, document_id=document_id)
        result["contexts"] = [c["content"] for c in chunks]
        result["best_similarity"] = chunks[0]["similarity"] if chunks else 0.0

        context_blocks = [c["content"] for c in chunks] if chunks else []
        answer = chat_completion(build_user_prompt(question, context_blocks))
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


# ── Scorecard printing ────────────────────────────────────────────────────────

def _print_scorecard(metrics: dict[str, float], doc_label: str, extra_info: str = "") -> bool:
    """Print the scorecard and return True if all metrics pass."""
    print("\n" + "=" * 72)
    print("RAG QUALITY GATE SCORECARD")
    print(f"  Document : {doc_label}")
    if extra_info:
        print(f"  Config   : {extra_info}")
    print("=" * 72)
    print(f"{'METRIC':<26} {'SCORE':>6}  {'THRESHOLD':>9}  STATUS")
    print("-" * 72)

    gate_passed = True
    for metric, threshold in THRESHOLDS.items():
        if metric not in metrics:
            continue
        score = metrics[metric]
        passed = score >= threshold
        gate_passed = gate_passed and passed
        print(f"{metric:<26} {score:6.2f}  {threshold:>9.2f}  {'PASS' if passed else 'FAIL'}")

    print("=" * 72)
    print(f"VERDICT: {'SHIP' if gate_passed else 'FIX'}")
    print("=" * 72 + "\n")
    return gate_passed


def _print_failures(all_results: list[dict]) -> None:
    failures = [r for r in all_results if not r.get("all_passed")]
    if not failures:
        return
    failures_sorted = sorted(
        failures,
        key=lambda r: r.get("faithfulness", 1.0) + r.get("answer_relevance", 1.0),
    )[:5]

    print("TOP-5 FAILURES:")
    print("-" * 72)
    for i, fail in enumerate(failures_sorted, 1):
        ftype = fail.get("failure_type", "unknown")
        print(f"{i}. Q{fail['question_id']:02d} [{fail['source_type']}] {fail['question'][:50]}")
        print(f"   Failure type : {ftype}")
        if fail.get("answerable"):
            print(
                f"   Faithfulness={fail.get('faithfulness', 0):.2f}  "
                f"Relevance={fail.get('answer_relevance', 0):.2f}  "
                f"Precision={fail.get('context_precision', 0):.2f}  "
                f"Recall={fail.get('context_recall', 0):.2f}"
            )
        if fail.get("answer"):
            print(f"   Answer : {str(fail['answer'])[:110]}...")
    print()


# ── Aggregation ───────────────────────────────────────────────────────────────

def _aggregate(all_results: list[dict]) -> dict[str, float]:
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

    return metrics


def _save_report(
    verdict: str,
    metrics: dict,
    all_results: list[dict],
    extra: dict,
) -> Path:
    failures = [r for r in all_results if not r.get("all_passed")]
    answerable = [r for r in all_results if r["answerable"]]
    unanswerable = [r for r in all_results if not r["answerable"]]

    report = {
        "verdict": verdict,
        "metrics": metrics,
        "thresholds": THRESHOLDS,
        "summary": {
            "total": len(all_results),
            "answerable": len(answerable),
            "unanswerable": len(unanswerable),
            "passed": sum(1 for r in all_results if r.get("all_passed")),
            "failed": len(failures),
        },
        **extra,
        "results": all_results,
    }
    path = Path("eval") / "quality_gate_report.json"
    with open(path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    logger.info(f"Report saved to {path}")
    return path


# ── Fixture ingestion (fixture mode) ─────────────────────────────────────────

def _delete_eval_fixtures() -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM documents WHERE name IN (%s, %s)",
                (EVAL_PDF_NAME, EVAL_EXCEL_NAME),
            )


def _insert_doc_row(name: str, doc_type: str, pages: int | None, sheets: int | None) -> int:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO documents (name, type, pages, sheets, status)"
                " VALUES (%s, %s, %s, %s, 'indexed') RETURNING id",
                (name, doc_type, pages, sheets),
            )
            return cur.fetchone()[0]


def ingest_fixtures() -> dict[str, int]:
    """Upload both fixture files through the real ingestion pipeline."""
    logger.info("Removing leftover eval fixture documents...")
    _delete_eval_fixtures()

    doc_ids: dict[str, int] = {}

    pdf_path = str(FIXTURES_DIR / "sample.pdf")
    pdf_doc_id = _insert_doc_row(EVAL_PDF_NAME, "pdf", get_page_count(pdf_path), None)
    pdf_chunks = chunk_units(parse_pdf(pdf_path, EVAL_PDF_NAME), settings.default_chunk_strategy)
    insert_chunks(pdf_doc_id, pdf_chunks)
    doc_ids["pdf"] = pdf_doc_id
    logger.info(f"PDF ingested: {len(pdf_chunks)} chunks (doc_id={pdf_doc_id})")

    xlsx_path = str(FIXTURES_DIR / "sample.xlsx")
    xlsx_doc_id = _insert_doc_row(EVAL_EXCEL_NAME, "excel", None, get_sheet_count(xlsx_path))
    xlsx_chunks = chunk_units(
        parse_excel(xlsx_path, EVAL_EXCEL_NAME, settings.default_excel_format),
        settings.default_chunk_strategy,
    )
    insert_chunks(xlsx_doc_id, xlsx_chunks)
    doc_ids["excel"] = xlsx_doc_id
    logger.info(f"Excel ingested: {len(xlsx_chunks)} chunks (doc_id={xlsx_doc_id})")

    return doc_ids


# ── Modes ─────────────────────────────────────────────────────────────────────

def run_document_mode(doc_id: int) -> int:
    """Evaluate a specific uploaded document using auto-generated Q&A pairs."""

    doc = get_document_info(doc_id)
    if not doc:
        logger.error(f"Document {doc_id} not found. Use --list to see available documents.")
        return 1
    if doc["status"] != "indexed":
        logger.error(f"Document {doc_id} has status '{doc['status']}'. Wait for indexing.")
        return 1

    logger.info(f"Generating golden Q&A set for: {doc['name']}")
    golden_set = generate_qa_pairs(doc_id, n_answerable=16, n_unanswerable=4)

    logger.info(f"Evaluating {len(golden_set)} questions against doc_id={doc_id}...")
    all_results = []
    for q_data in golden_set:
        label = "refusal" if not q_data["answerable"] else q_data["question"][:50]
        logger.info(f"  Q{q_data['id']:02d}: {label}...")
        # Unanswerable questions: no document scope — tests that the system refuses correctly
        scoped_doc_id = doc_id if q_data["answerable"] else None
        result = evaluate_question(q_data, scoped_doc_id)
        all_results.append(result)

    metrics = _aggregate(all_results)
    doc_label = f"{doc['name']} (doc_id={doc_id}, type={doc['type']})"
    config_info = (
        f"strategy={settings.default_chunk_strategy}  "
        f"excel_format={settings.default_excel_format}  "
        f"top_k={settings.top_k}"
    )
    gate_passed = _print_scorecard(metrics, doc_label, config_info)
    _print_failures(all_results)

    verdict = "SHIP" if gate_passed else "FIX"
    _save_report(verdict, metrics, all_results, {"document": doc, "mode": "document"})

    return 0 if gate_passed else 1


def run_fixture_mode() -> int:
    """Evaluate using synthetic fixture files and the hand-crafted golden_set.json."""

    if not (FIXTURES_DIR / "sample.pdf").exists() or not (FIXTURES_DIR / "sample.xlsx").exists():
        logger.error("Fixtures not found. Run: python eval/generate_test_docs.py")
        return 1

    logger.info("Ingesting fixture documents...")
    doc_ids = ingest_fixtures()

    logger.info("Loading golden set from golden_set.json...")
    with open(GOLDEN_SET_PATH, "r") as f:
        golden_set = json.load(f)

    logger.info(f"Evaluating {len(golden_set)} questions...")
    all_results = []
    for q_data in golden_set:
        logger.info(f"  Q{q_data['id']:02d} ({q_data['source_type']}): {q_data['question'][:55]}...")
        doc_type = SOURCE_TO_DOC_TYPE.get(q_data.get("source_type", ""))
        document_id = doc_ids.get(doc_type) if doc_type else None
        result = evaluate_question(q_data, document_id)
        all_results.append(result)

    metrics = _aggregate(all_results)
    doc_label = (
        f"[eval] sample.pdf (doc_id={doc_ids['pdf']}) + "
        f"sample.xlsx (doc_id={doc_ids['excel']})"
    )
    config_info = (
        f"strategy={settings.default_chunk_strategy}  "
        f"excel_format={settings.default_excel_format}"
    )
    gate_passed = _print_scorecard(metrics, doc_label, config_info)
    _print_failures(all_results)

    verdict = "SHIP" if gate_passed else "FIX"
    _save_report(
        verdict, metrics, all_results,
        {
            "mode": "fixture",
            "ingestion": {
                "pdf_doc_id": doc_ids["pdf"],
                "excel_doc_id": doc_ids["excel"],
                "chunk_strategy": settings.default_chunk_strategy,
                "excel_format": settings.default_excel_format,
            },
        },
    )
    return 0 if gate_passed else 1


def cmd_list_documents() -> None:
    """Print all documents in the database."""
    docs = list_documents()
    if not docs:
        print("No documents found. Upload a document first via the app.")
        return
    print(f"\n{'ID':>4}  {'STATUS':>8}  {'TYPE':>6}  NAME")
    print("-" * 60)
    for d in docs:
        print(f"{d['id']:>4}  {d['status']:>8}  {d['type']:>6}  {d['name']}")
    print()


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="RAG Quality Gate — evaluate an uploaded document or the built-in fixtures.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List uploadd documents and their IDs
  python -m eval.run_quality_gate --list

  # Evaluate a specific uploaded document (recommended)
  python -m eval.run_quality_gate --doc-id 3

  # Evaluate using synthetic fixture files (regression baseline)
  python -m eval.run_quality_gate
        """,
    )
    parser.add_argument(
        "--doc-id",
        type=int,
        metavar="ID",
        help="ID of an already-uploaded document to evaluate (auto-generates Q&A from its chunks).",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all uploaded documents with their IDs and exit.",
    )
    args = parser.parse_args()

    if args.list:
        cmd_list_documents()
        return 0

    if args.doc_id:
        return run_document_mode(args.doc_id)

    return run_fixture_mode()


if __name__ == "__main__":
    sys.exit(main())
