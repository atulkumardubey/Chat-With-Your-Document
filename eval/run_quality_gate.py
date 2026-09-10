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
    "faithfulness": 0.70,
    "answer_relevance": 0.70,
    "context_precision": 0.60,
    "context_recall": 0.60,
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

    For answerable questions: scores faithfulness, answer_relevance,
    context_precision, context_recall via LLM-as-judge.

    For unanswerable questions (answerable=False): checks that the system
    correctly refuses to answer.  Retrieval is deliberately un-scoped so the
    system has every chance of finding something — a correct refusal under
    those conditions is the strongest possible PASS.
    """
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
        scoped_id = document_id if q["answerable"] else None
        embedding = embed_query(q["question"])
        chunks = search(embedding, top_k=settings.top_k, document_id=scoped_id)
        result["contexts"] = [c["content"] for c in chunks]
        result["best_similarity"] = chunks[0]["similarity"] if chunks else 0.0

        answer = chat_completion(build_user_prompt(q["question"], result["contexts"]))
        result["answer"] = answer

        if q["answerable"]:
            result["faithfulness"] = score_faithfulness(answer, result["contexts"])
            result["answer_relevance"] = score_answer_relevance(q["question"], answer)
            result["context_precision"] = score_context_precision(q["question"], result["contexts"])
            result["context_recall"] = score_context_recall(q.get("reference", ""), result["contexts"])

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

    # Evaluate each question
    logger.info(f"Running {len(golden_set)} questions through the RAG pipeline...")
    results = []
    for q in golden_set:
        label = q["question"][:55] if q["answerable"] else f"[refusal] {q['question'][:45]}"
        logger.info(f"  Q{q['id']:02d}: {label}...")
        results.append(evaluate_question(q, doc_id))

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
