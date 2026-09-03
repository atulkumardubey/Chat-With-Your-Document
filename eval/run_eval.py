"""Bake-off evaluation: runs the 15-question test set across every combination of
chunking strategy (fixed/recursive/section_aware) x Excel serialization format
(rows/markdown/column), scores accuracy per source type, and prints the winning
Excel format and chunking strategy with rationale.

Requires a configured .env (DB + NVIDIA_API_KEY) and the fixtures generated via
`python eval/generate_test_docs.py`.

Run with: python -m eval.run_eval
"""

import json
import os
from collections import defaultdict

from app.db import get_connection, init_schema
from app.ingestion.chunkers import chunk_units
from app.ingestion.excel_parser import parse_excel
from app.ingestion.pdf_parser import parse_pdf
from app.retrieval.retriever import retrieve_and_answer
from app.retrieval.vector_store import insert_chunks

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
QUESTIONS_PATH = os.path.join(os.path.dirname(__file__), "test_questions.json")

CHUNK_STRATEGIES = ["fixed", "recursive", "section_aware"]
EXCEL_FORMATS = ["rows", "markdown", "column"]


def _reset_data() -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE documents, chunks RESTART IDENTITY CASCADE")


def _insert_document(name: str, doc_type: str) -> int:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO documents (name, type, status) VALUES (%s, %s, 'indexed') RETURNING id",
                (name, doc_type),
            )
            return cur.fetchone()[0]


def _ingest(chunk_strategy: str, excel_format: str) -> None:
    _reset_data()

    pdf_path = os.path.join(FIXTURES_DIR, "sample.pdf")
    pdf_units = parse_pdf(pdf_path, "sample.pdf")
    pdf_doc_id = _insert_document("sample.pdf", "pdf")
    insert_chunks(pdf_doc_id, chunk_units(pdf_units, chunk_strategy))

    xlsx_path = os.path.join(FIXTURES_DIR, "sample.xlsx")
    xlsx_units = parse_excel(xlsx_path, "sample.xlsx", excel_format)
    xlsx_doc_id = _insert_document("sample.xlsx", "excel")
    insert_chunks(xlsx_doc_id, chunk_units(xlsx_units, chunk_strategy))


def _is_correct(answer: str, expected_keywords: list[str]) -> bool:
    lowered = answer.lower()
    return any(keyword.lower() in lowered for keyword in expected_keywords)


def run() -> None:
    init_schema()
    with open(QUESTIONS_PATH, encoding="utf-8") as f:
        questions = json.load(f)

    # results[(chunk_strategy, excel_format)][source_type] = (correct, total)
    results: dict[tuple[str, str], dict[str, list[int]]] = {}

    for chunk_strategy in CHUNK_STRATEGIES:
        for excel_format in EXCEL_FORMATS:
            print(f"\n=== chunk_strategy={chunk_strategy} excel_format={excel_format} ===")
            _ingest(chunk_strategy, excel_format)

            per_type = defaultdict(lambda: [0, 0])
            for q in questions:
                result = retrieve_and_answer(q["question"])
                correct = _is_correct(result["content"], q["expected_keywords"])
                per_type[q["source_type"]][0] += int(correct)
                per_type[q["source_type"]][1] += 1
                mark = "PASS" if correct else "FAIL"
                print(f"  [{mark}] ({q['source_type']}) {q['question']}")

            results[(chunk_strategy, excel_format)] = dict(per_type)

    _print_report(results)


def _print_report(results: dict[tuple[str, str], dict[str, list[int]]]) -> None:
    print("\n\n=== Accuracy by combination and source type ===")
    for (chunk_strategy, excel_format), per_type in results.items():
        total_correct = sum(c for c, _ in per_type.values())
        total_qs = sum(t for _, t in per_type.values())
        print(f"\n{chunk_strategy} / {excel_format}: {total_correct}/{total_qs} overall")
        for source_type, (correct, total) in sorted(per_type.items()):
            print(f"  {source_type}: {correct}/{total}")

    # Winning Excel format: average accuracy on excel_sheet1/excel_sheet2 questions, by format.
    excel_scores: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for (_, excel_format), per_type in results.items():
        for source_type in ("excel_sheet1", "excel_sheet2"):
            if source_type in per_type:
                c, t = per_type[source_type]
                excel_scores[excel_format][0] += c
                excel_scores[excel_format][1] += t

    print("\n=== Excel serialization format bake-off ===")
    best_format, best_rate = None, -1.0
    for fmt, (c, t) in excel_scores.items():
        rate = c / t if t else 0.0
        print(f"  {fmt}: {c}/{t} ({rate:.0%})")
        if rate > best_rate:
            best_format, best_rate = fmt, rate
    print(f"WINNER: '{best_format}' serialization format ({best_rate:.0%} accuracy on Excel questions)")

    # Winning chunking strategy: average accuracy across ALL questions, by strategy.
    strategy_scores: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for (chunk_strategy, _), per_type in results.items():
        for c, t in per_type.values():
            strategy_scores[chunk_strategy][0] += c
            strategy_scores[chunk_strategy][1] += t

    print("\n=== Chunking strategy bake-off ===")
    best_strategy, best_strategy_rate = None, -1.0
    for strategy, (c, t) in strategy_scores.items():
        rate = c / t if t else 0.0
        print(f"  {strategy}: {c}/{t} ({rate:.0%})")
        if rate > best_strategy_rate:
            best_strategy, best_strategy_rate = strategy, rate
    print(f"WINNER: '{best_strategy}' chunking strategy ({best_strategy_rate:.0%} accuracy overall)")


if __name__ == "__main__":
    run()
