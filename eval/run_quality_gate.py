"""RAG Quality Gate — evaluate an uploaded document with LLM-as-judge metrics.

Usage
-----
# 1. List available uploaded documents
python -m eval.run_quality_gate --list

# 2a. Evaluate with YOUR hand-crafted questions (fast — recommended)
python -m eval.run_quality_gate --doc-id 3 --questions eval/my_questions.json

# 2b. Evaluate with auto-generated questions (slow — one LLM call per chunk)
python -m eval.run_quality_gate --doc-id 3
"""

import argparse
import json
import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from app.config import settings
from app.ingestion.embedder import embed_query
from app.llm.nvidia_client import chat_completion
from app.llm.prompts import build_user_prompt
from app.retrieval.vector_store import search

from eval.judge import (
    is_correct_refusal,
    score_answer_relevance,
    score_context_precision,
    score_context_recall,
    score_faithfulness,
)
from eval.question_generator import generate_qa_pairs, get_document_info, list_documents

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# ── Release thresholds ────────────────────────────────────────────────────────
# All metrics must reach their threshold for a SHIP verdict.

THRESHOLDS: dict[str, float] = {
    "faithfulness": 0.60,
    "answer_relevance": 0.60,
    "context_precision": 0.50,
    "context_recall": 0.40,
    "correct_refusal_rate": 1.00,
}

_CHUNKING_PROBLEM_PRECISION = 0.40
_GENERATION_ERROR_SCORE = 0.50


# ── Failure classification ────────────────────────────────────────────────────

def _classify_failure(result: dict[str, Any]) -> str:
    if not result.get("contexts"):
        return "retrieval_miss"
    if result.get("context_precision", 1.0) < _CHUNKING_PROBLEM_PRECISION:
        return "chunking_problem"
    if (
        result.get("faithfulness", 1.0) < _GENERATION_ERROR_SCORE
        or result.get("answer_relevance", 1.0) < _GENERATION_ERROR_SCORE
    ):
        return "generation_error"
    return "unknown"


# ── Core evaluation ───────────────────────────────────────────────────────────

def evaluate_question(q: dict, document_id: int | None) -> dict:
    """Run one Q&A pair through the RAG pipeline and score it.

    Mirrors the same retrieval logic as retriever.retrieve_and_answer():
    if no chunks are found or best_similarity < settings.similarity_threshold,
    the answer is set to REFUSAL_MESSAGE — this is what the production system
    does, so the eval must match it exactly.

    Both answerable AND unanswerable questions are scoped to document_id so
    that chunks from unrelated documents don't bleed into the test.
    """
    from app.llm.prompts import REFUSAL_MESSAGE as _REFUSAL

    result: dict[str, Any] = {
        "question_id": q["id"],
        "question": q["question"],
        "answerable": q["answerable"],
        "source_type": q.get("source_type", ""),
        "document_id": document_id,
        "answer": None,
        "contexts": [],
        "best_similarity": 0.0,
    }
    try:
        embedding = embed_query(q["question"])
        chunks = search(embedding, top_k=settings.top_k, document_id=document_id)
        result["contexts"] = [c["content"] for c in chunks]
        result["best_similarity"] = chunks[0]["similarity"] if chunks else 0.0

        # Mirror the production threshold gate — below threshold → refuse, same as retriever.py
        if not chunks or result["best_similarity"] < settings.similarity_threshold:
            answer = _REFUSAL
        else:
            answer = chat_completion(build_user_prompt(q["question"], result["contexts"]))
        result["answer"] = answer

        if q["answerable"]:
            # Run all 4 judge calls concurrently — they are fully independent.
            with ThreadPoolExecutor(max_workers=4) as pool:
                fut_faithfulness = pool.submit(score_faithfulness, answer, result["contexts"])
                fut_relevance    = pool.submit(score_answer_relevance, q["question"], answer)
                fut_precision    = pool.submit(score_context_precision, q["question"], result["contexts"])
                fut_recall       = pool.submit(score_context_recall, q.get("reference", ""), result["contexts"])
            result["faithfulness"]      = fut_faithfulness.result()
            result["answer_relevance"]  = fut_relevance.result()
            result["context_precision"] = fut_precision.result()
            result["context_recall"]    = fut_recall.result()

            result["all_passed"] = (
                result["faithfulness"] >= THRESHOLDS["faithfulness"]
                and result["answer_relevance"] >= THRESHOLDS["answer_relevance"]
                and result["context_precision"] >= THRESHOLDS["context_precision"]
                and result["context_recall"] >= THRESHOLDS["context_recall"]
            )
            if not result["all_passed"]:
                result["failure_type"] = _classify_failure(result)
        else:
            result["is_correct_refusal"] = is_correct_refusal(answer)
            result["all_passed"] = result["is_correct_refusal"]
            if not result["all_passed"]:
                result["failure_type"] = "incorrect_answer_to_unanswerable"

    except Exception as exc:
        logger.error(f"Error evaluating Q{q['id']}: {exc}")
        result["error"] = str(exc)
        result["all_passed"] = False

    return result


# ── Aggregation ───────────────────────────────────────────────────────────────

def _aggregate(results: list[dict]) -> dict[str, float]:
    answerable = [r for r in results if r["answerable"]]
    unanswerable = [r for r in results if not r["answerable"]]
    metrics: dict[str, float] = {}
    if answerable:
        metrics["faithfulness"] = sum(r.get("faithfulness", 0.0) for r in answerable) / len(answerable)
        metrics["answer_relevance"] = sum(r.get("answer_relevance", 0.0) for r in answerable) / len(answerable)
        metrics["context_precision"] = sum(r.get("context_precision", 0.0) for r in answerable) / len(answerable)
        metrics["context_recall"] = sum(r.get("context_recall", 0.0) for r in answerable) / len(answerable)
    if unanswerable:
        metrics["correct_refusal_rate"] = (
            sum(1 for r in unanswerable if r.get("is_correct_refusal")) / len(unanswerable)
        )
    return metrics


# ── Output helpers ────────────────────────────────────────────────────────────

def _print_scorecard(metrics: dict[str, float], doc_label: str, config: str) -> bool:
    print("\n" + "=" * 72)
    print("RAG QUALITY GATE SCORECARD")
    print(f"  Document : {doc_label}")
    print(f"  Config   : {config}")
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


def _print_failures(results: list[dict]) -> None:
    failures = sorted(
        [r for r in results if not r.get("all_passed")],
        key=lambda r: r.get("faithfulness", 1.0) + r.get("answer_relevance", 1.0),
    )[:5]
    if not failures:
        return
    print("TOP-5 FAILURES:")
    print("-" * 72)
    for i, f in enumerate(failures, 1):
        print(f"{i}. Q{f['question_id']:02d} [{f['source_type']}] {f['question'][:52]}")
        print(f"   Failure : {f.get('failure_type', 'unknown')}")
        if f.get("answerable"):
            print(
                f"   Scores  : Faithfulness={f.get('faithfulness',0):.2f}  "
                f"Relevance={f.get('answer_relevance',0):.2f}  "
                f"Precision={f.get('context_precision',0):.2f}  "
                f"Recall={f.get('context_recall',0):.2f}"
            )
        if f.get("answer"):
            print(f"   Answer  : {str(f['answer'])[:110]}...")
    print()


def _save_report(verdict: str, metrics: dict, results: list[dict], extra: dict) -> None:
    answerable = [r for r in results if r["answerable"]]
    unanswerable = [r for r in results if not r["answerable"]]
    report = {
        "verdict": verdict,
        "metrics": metrics,
        "thresholds": THRESHOLDS,
        "summary": {
            "total": len(results),
            "answerable": len(answerable),
            "unanswerable": len(unanswerable),
            "passed": sum(1 for r in results if r.get("all_passed")),
            "failed": sum(1 for r in results if not r.get("all_passed")),
        },
        **extra,
        "results": results,
    }
    path = Path("eval") / "quality_gate_report.json"
    with open(path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    logger.info(f"Report saved to {path}")


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_list() -> None:
    docs = list_documents()
    if not docs:
        print("No uploaded documents found. Upload a document via the app first.")
        return
    print(f"\n{'ID':>4}  {'STATUS':>8}  {'TYPE':>6}  NAME")
    print("-" * 60)
    for d in docs:
        print(f"{d['id']:>4}  {d['status']:>8}  {d['type']:>6}  {d['name']}")
    print()


def cmd_evaluate(doc_id: int, questions_path: str | None) -> int:
    doc = get_document_info(doc_id)
    if not doc:
        logger.error(f"Document {doc_id} not found. Run --list to see available documents.")
        return 1
    if doc["status"] != "indexed":
        logger.error(f"Document {doc_id} has status '{doc['status']}'. Wait for indexing to complete.")
        return 1

    # Load or generate the golden question set
    if questions_path:
        logger.info(f"Loading questions from: {questions_path}")
        try:
            with open(questions_path, "r", encoding="utf-8") as f:
                golden_set = json.load(f)
            for i, q in enumerate(golden_set, 1):
                q["id"] = i  # Ensure consecutive IDs
            logger.info(f"Loaded {len(golden_set)} questions.")
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            logger.error(f"Cannot load questions file: {exc}")
            return 1
    else:
        logger.info(f"Auto-generating Q&A pairs for: {doc['name']} (this may take a few minutes)...")
        golden_set = generate_qa_pairs(doc_id, n_answerable=16, n_unanswerable=4)

    # Evaluate questions concurrently (4 workers to avoid API rate limits).
    # Each worker further parallelises its 4 judge calls, so peak concurrency = 4 × 4 = 16.
    logger.info(f"Running {len(golden_set)} questions through the RAG pipeline (parallel)...")
    results: list[dict] = [{}] * len(golden_set)
    with ThreadPoolExecutor(max_workers=4) as pool:
        future_to_idx = {
            pool.submit(evaluate_question, q, doc_id): i
            for i, q in enumerate(golden_set)
        }
        for fut in as_completed(future_to_idx):
            idx = future_to_idx[fut]
            q = golden_set[idx]
            label = q["question"][:55] if q["answerable"] else f"[refusal] {q['question'][:45]}"
            try:
                results[idx] = fut.result()
                logger.info(f"  Q{q['id']:02d} done: {label}")
            except Exception as exc:
                logger.error(f"  Q{q['id']:02d} failed: {exc}")
                results[idx] = {
                    "question_id": q["id"], "question": q["question"],
                    "answerable": q["answerable"], "source_type": q.get("source_type", ""),
                    "document_id": doc_id, "answer": None, "contexts": [],
                    "best_similarity": 0.0, "all_passed": False, "error": str(exc),
                }

    # Score, print, save
    metrics = _aggregate(results)
    config = (
        f"strategy={settings.default_chunk_strategy}  "
        f"top_k={settings.top_k}  "
        f"threshold={settings.similarity_threshold}"
    )
    gate_passed = _print_scorecard(
        metrics,
        doc_label=f"{doc['name']}  (doc_id={doc_id}, type={doc['type']})",
        config=config,
    )
    _print_failures(results)

    verdict = "SHIP" if gate_passed else "FIX"
    _save_report(
        verdict, metrics, results,
        {"mode": "document", "document": doc, "questions_file": questions_path},
    )
    return 0 if gate_passed else 1


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="RAG Quality Gate — evaluate an uploaded document.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Show all uploaded documents and their IDs
  python -m eval.run_quality_gate --list

  # Evaluate with hand-crafted questions (fast)
  python -m eval.run_quality_gate --doc-id 3 --questions eval/my_questions.json

  # Evaluate with auto-generated questions (slow)
  python -m eval.run_quality_gate --doc-id 3
        """,
    )
    parser.add_argument(
        "--doc-id", type=int, metavar="ID",
        help="ID of the uploaded document to evaluate.",
    )
    parser.add_argument(
        "--questions", metavar="PATH",
        help="Path to a hand-crafted JSON questions file (e.g. eval/my_questions.json). "
             "Requires --doc-id.",
    )
    parser.add_argument(
        "--list", action="store_true",
        help="List all uploaded documents with their IDs and exit.",
    )
    args = parser.parse_args()

    if args.list:
        cmd_list()
        return 0

    if not args.doc_id:
        parser.print_help()
        return 1

    if args.questions and not args.doc_id:
        parser.error("--questions requires --doc-id")

    return cmd_evaluate(args.doc_id, args.questions)


if __name__ == "__main__":
    sys.exit(main())
