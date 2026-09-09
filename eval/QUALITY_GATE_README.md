# RAG Quality Gate (Project 3)

Comprehensive evaluation framework for the RAG system using LLM-as-judge metrics. Replaces subjective "it looks good" assessments with quantitative scores and automated release decisions.

## What's Included

### 1. **Golden Set** (`eval/golden_set.json`)
- 20 Q&A pairs (14 answerable, 6 unanswerable)
- Covers all document types: PDF text, PDF table, PDF chart, Excel sheets 1 & 2, plus refusals
- Each question includes a ground-truth reference answer (null for unanswerable)

### 2. **Judge Module** (`eval/judge.py`)
LLM-as-judge scoring functions:

| Metric | What it measures | Scale |
|--------|-----------------|-------|
| **Faithfulness** | Claims in answer are supported by retrieved contexts | 0.0–1.0 |
| **Answer Relevance** | Answer directly addresses the question | 0.0–1.0 |
| **Context Precision** | Fraction of retrieved chunks relevant to question | 0.0–1.0 |
| **Context Recall** | Fraction of reference facts covered by contexts | 0.0–1.0 |
| **Correct Refusal Rate** | Unanswerable questions are correctly refused | 0.0–1.0 |

Each metric is scored via `judge_completion()` with:
- Custom system prompt ("You are an impartial evaluator...")
- JSON output parsing: `{"score": 0.0–1.0, "reason": "..."}`
- Chain-of-thought stripping (Nemotron is a reasoning model)

### 3. **Quality Gate Script** (`eval/run_quality_gate.py`)
Main evaluation orchestrator:

```bash
python -m eval.run_quality_gate
```

**Flow:**
1. Load golden set (20 Q&A pairs)
2. For each question:
   - Embed and retrieve top-5 chunks
   - Generate answer via RAG pipeline
   - Score all metrics (4 for answerable, 1 for unanswerable)
   - Classify failures: `retrieval_miss`, `chunking_problem`, `generation_error`
3. Aggregate scores and compare against thresholds
4. Print scorecard + SHIP/FIX verdict
5. Save full report to `eval/quality_gate_report.json`

## Release Thresholds

| Metric | Must Be ≥ | Default |
|--------|-----------|---------|
| Faithfulness | 0.70 | ✓ |
| Answer Relevance | 0.70 | ✓ |
| Context Precision | 0.60 | ✓ |
| Context Recall | 0.60 | ✓ |
| Correct Refusal Rate | 1.00 (must be perfect) | ✓ |

If **ANY** metric falls below its threshold → **FIX** (do not ship)

## Setup

1. **Ensure fixture docs exist:**
   ```bash
   python eval/generate_test_docs.py
   ```

2. **Start backend** (in separate terminal):
   ```bash
   uvicorn app.main:app --reload
   ```
   Backend creates schema + indexes on startup.

3. **Run evaluation:**
   ```bash
   python -m eval.run_quality_gate
   ```

## Example Output

```
======================================================================
RAG QUALITY GATE SCORECARD
======================================================================
faithfulness         |   0.82 |   0.70 | ✓ PASS
answer_relevance     |   0.76 |   0.70 | ✓ PASS
context_precision    |   0.71 |   0.60 | ✓ PASS
context_recall       |   0.68 |   0.60 | ✓ PASS
correct_refusal_rate |   1.00 |   1.00 | ✓ PASS
======================================================================
VERDICT: SHIP ✓
======================================================================

TOP-5 FAILURES (Most Critical):
--
1. Q 7: How many website visitors were there in May 2024? | generation_error
   Faithfulness: 0.45, Relevance: 0.52, Precision: 0.73
```

## Machine-Readable Report

After each run, `eval/quality_gate_report.json` contains:
- Per-question detailed scores
- Aggregated metrics
- Pass/fail status
- Failure classifications
- Full LLM judge reasoning

Use for CI/CD pipelines, dashboards, or automated release gates.

## Key Features

✓ **No new packages needed** — uses existing `openai` client (NVIDIA NIM) + `sentence-transformers`

✓ **Semantic scoring** — LLM-based evaluation captures meaning, not just keywords

✓ **Failure diagnosis** — classifies why questions fail (retrieval, chunking, or generation)

✓ **Correct refusal credit** — unanswerable questions score a PASS if correctly refused

✓ **Deterministic** — all judge calls use `temperature=0.0` for reproducible scoring

✓ **Extensible** — easy to add new metrics or adjust thresholds in `run_quality_gate.py`

## Troubleshooting

**"API key not found"**
- Ensure `NVIDIA_API_KEY` is set in `.env`

**"No contexts retrieved"**
- Check database has chunks indexed (run `python Backend.py` if needed)
- Verify backend is running on port 8000

**"JSON parse error in judge"**
- The LLM may ignore the JSON format request
- Increase `temperature` (currently 0.0) to encourage more varied outputs
- Check logs for what the LLM returned

**Metric scores suspiciously high/low**
- Review judge prompts in `eval/judge.py` — they define what each metric means
- Manually inspect a failed question's answer + contexts in the report

## Next Steps

1. Run the quality gate after making changes to:
   - Chunking strategy
   - Embedding model
   - LLM prompt
   - Retrieval logic

2. Use the report to identify systematic failures:
   - All refusals incorrect? → Fix similarity threshold
   - Low precision? → Adjust chunk size
   - Low faithfulness? → Revise LLM system prompt

3. Set a CI gate: fail the build if `verdict == "FIX"`

```bash
# In CI pipeline
python -m eval.run_quality_gate
if [ $? -ne 0 ]; then exit 1; fi
```
