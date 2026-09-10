import asyncio
import json
import queue
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

router = APIRouter(prefix="/api", tags=["quality-gate"])

_REPORT_PATH = Path(__file__).resolve().parents[2] / "eval" / "quality_gate_report.json"
_DEFAULT_QUESTIONS = Path(__file__).resolve().parents[2] / "eval" / "my_questions.json"

# In-memory run state keyed by run_id
_runs: dict[str, dict] = {}


# ── Report endpoint ───────────────────────────────────────────────────────────

@router.get("/quality-gate-report")
def get_quality_gate_report() -> dict:
    if not _REPORT_PATH.exists():
        raise HTTPException(
            status_code=404,
            detail="No quality gate report found. Run an evaluation first.",
        )
    with open(_REPORT_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# ── Run trigger ───────────────────────────────────────────────────────────────

class RunRequest(BaseModel):
    doc_id: int
    questions_file: str | None = None  # None → auto-detect my_questions.json or generate


@router.post("/quality-gate/run")
def start_quality_gate_run(body: RunRequest) -> dict:
    run_id = str(uuid.uuid4())
    q: queue.Queue = queue.Queue()
    _runs[run_id] = {"queue": q, "done": False}

    # Resolve questions file
    qfile = body.questions_file
    if qfile is None and _DEFAULT_QUESTIONS.exists():
        qfile = str(_DEFAULT_QUESTIONS)

    t = threading.Thread(
        target=_run_eval_worker,
        args=(run_id, body.doc_id, qfile),
        daemon=True,
    )
    t.start()
    return {"run_id": run_id}


# ── SSE stream ────────────────────────────────────────────────────────────────

@router.get("/quality-gate/run/{run_id}/events")
async def stream_run_events(run_id: str) -> StreamingResponse:
    if run_id not in _runs:
        raise HTTPException(status_code=404, detail="Run not found")

    async def generate():
        run = _runs[run_id]
        q = run["queue"]
        while True:
            try:
                event = q.get_nowait()
                yield f"data: {json.dumps(event)}\n\n"
                if event.get("type") in ("done", "error"):
                    break
            except queue.Empty:
                if run.get("done"):
                    break
                # Keepalive so the browser doesn't close the connection
                yield ": keepalive\n\n"
                await asyncio.sleep(0.3)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Worker (runs in a background thread) ─────────────────────────────────────

def _run_eval_worker(run_id: str, doc_id: int, questions_file: str | None) -> None:
    run = _runs[run_id]
    q = run["queue"]

    try:
        # Lazy imports — keeps module-level import order clean
        from eval.question_generator import generate_qa_pairs, get_document_info
        from eval.run_quality_gate import (
            THRESHOLDS,
            _aggregate,
            _save_report,
            evaluate_question,
        )

        doc = get_document_info(doc_id)
        if not doc:
            q.put({"type": "error", "message": f"Document {doc_id} not found."})
            return
        if doc["status"] != "indexed":
            q.put({"type": "error", "message": f"Document is not fully indexed (status={doc['status']})."})
            return

        # Load or generate questions
        if questions_file:
            with open(questions_file, "r", encoding="utf-8") as f:
                golden_set = json.load(f)
            for i, item in enumerate(golden_set, 1):
                item["id"] = i
        else:
            golden_set = generate_qa_pairs(doc_id, n_answerable=16, n_unanswerable=4)

        total = len(golden_set)
        q.put({"type": "start", "total": total, "doc": doc["name"], "doc_id": doc_id})

        results: list[dict | None] = [None] * total
        completed = 0

        with ThreadPoolExecutor(max_workers=4) as pool:
            future_to_idx = {
                pool.submit(evaluate_question, question, doc_id): i
                for i, question in enumerate(golden_set)
            }
            for fut in as_completed(future_to_idx):
                idx = future_to_idx[fut]
                question = golden_set[idx]
                try:
                    result = fut.result()
                except Exception as exc:
                    result = {
                        "question_id": question["id"],
                        "question": question["question"],
                        "answerable": question["answerable"],
                        "source_type": question.get("source_type", ""),
                        "all_passed": False,
                        "error": str(exc),
                    }
                results[idx] = result
                completed += 1
                q.put({
                    "type": "progress",
                    "completed": completed,
                    "total": total,
                    "result": result,
                })

        # Final aggregation + save report
        final_results = [r for r in results if r is not None]
        metrics = _aggregate(final_results)
        gate_passed = all(
            metrics.get(k, 0.0) >= v for k, v in THRESHOLDS.items() if k in metrics
        )
        verdict = "SHIP" if gate_passed else "FIX"
        summary = {
            "total": len(final_results),
            "answerable": sum(1 for r in final_results if r.get("answerable")),
            "unanswerable": sum(1 for r in final_results if not r.get("answerable")),
            "passed": sum(1 for r in final_results if r.get("all_passed")),
            "failed": sum(1 for r in final_results if not r.get("all_passed")),
        }
        _save_report(
            verdict, metrics, final_results,
            {"mode": "document", "document": doc, "questions_file": questions_file},
        )
        q.put({
            "type": "done",
            "verdict": verdict,
            "metrics": metrics,
            "thresholds": THRESHOLDS,
            "summary": summary,
        })

    except Exception as exc:
        import traceback
        traceback.print_exc()
        q.put({"type": "error", "message": str(exc)})
    finally:
        run["done"] = True
