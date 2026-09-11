"""LLM-as-judge scoring functions for RAG quality evaluation.

Metrics: Faithfulness, Answer Relevance, Context Precision, Context Recall.
All metrics score 0.0-1.0. Uses NVIDIA NIM LLM with JSON output parsing.
"""

import json
import logging
import re

from app.config import settings
from app.llm.nvidia_client import _client, _strip_thinking
from app.llm.prompts import REFUSAL_MESSAGE

logger = logging.getLogger(__name__)


def judge_completion(system_prompt: str, user_prompt: str) -> str:
    """Call the LLM with a custom system prompt for judging.

    Args:
        system_prompt: Role/instruction prompt (e.g., "You are an impartial evaluator...")
        user_prompt: The judge question to answer

    Returns:
        Raw LLM response, with chain-of-thought stripped.
    """
    response = _client.chat.completions.create(
        model=settings.nvidia_llm_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.0,  # Deterministic scoring
    )
    raw = response.choices[0].message.content or ""
    return _strip_thinking(raw)


_JSON_BLOCK_RE = re.compile(r'```(?:json)?\s*(\{.*?\})\s*```', re.DOTALL)
_JSON_OBJECT_RE = re.compile(r'\{[^{}]*"score"[^{}]*\}', re.DOTALL)


def _parse_json_score(response: str) -> float:
    """Extract {"score": <float>} from LLM response, even when surrounded by reasoning text.

    The judge LLM sometimes outputs numbered reasoning steps before the JSON
    (e.g. "1. **Understand the Task**...") without using <think> tags, so a
    plain json.loads() on the full response fails. We try three strategies:
      1. Pull JSON from a ```json ... ``` fenced block.
      2. Find the first {...} object that contains "score" anywhere in the text.
      3. Fall back to parsing the whole response directly.
    """
    # Strategy 1 — fenced code block
    m = _JSON_BLOCK_RE.search(response)
    if m:
        candidate = m.group(1)
    else:
        # Strategy 2 — bare JSON object containing "score"
        m = _JSON_OBJECT_RE.search(response)
        candidate = m.group(0) if m else response

    try:
        data = json.loads(candidate)
        score = float(data.get("score", 0.0))
        return max(0.0, min(1.0, score))
    except (json.JSONDecodeError, ValueError, TypeError) as e:
        logger.warning(f"Failed to parse score JSON: {response[:120]}... Error: {e}")
        return 0.0


def score_faithfulness(answer: str, contexts: list[str]) -> float:
    """Measure if every claim in the answer is supported by the retrieved contexts.

    Faithfulness ∈ [0.0, 1.0]:
    - 1.0: all claims are supported
    - 0.5: some claims lack support
    - 0.0: answer contradicts or is unsupported by contexts

    Args:
        answer: The generated answer to evaluate
        contexts: List of retrieved context chunks

    Returns:
        Faithfulness score 0.0-1.0
    """
    contexts_text = "\n\n".join(f"[Chunk {i+1}]\n{ctx}" for i, ctx in enumerate(contexts))

    system_prompt = """You are an impartial RAG evaluation judge. Assess faithfulness.

Faithfulness: Does the answer contain only claims directly supported by the provided contexts?
- Every factual claim must be traceable to at least one context chunk.
- If the answer includes information NOT in the contexts, or contradicts them, reduce the score.

OUTPUT RULES: Respond with ONLY a JSON object — no reasoning, no preamble, no markdown.
Format: {"score": <float 0.0-1.0>, "reason": "<one sentence>"}"""

    user_prompt = f"""CONTEXTS:
{contexts_text}

ANSWER:
{answer}

JSON:"""

    response = judge_completion(system_prompt, user_prompt)
    return _parse_json_score(response)


def score_answer_relevance(question: str, answer: str) -> float:
    """Measure if the answer directly and fully addresses the question.

    Answer Relevance ∈ [0.0, 1.0]:
    - 1.0: answer directly and completely addresses the question
    - 0.5: answer is partially relevant or contains padding/off-topic content
    - 0.0: answer is off-topic or does not address the question

    Args:
        question: The user's question
        answer: The generated answer

    Returns:
        Answer Relevance score 0.0-1.0
    """
    system_prompt = """You are an impartial RAG evaluation judge. Assess answer relevance.

Answer Relevance: Does the answer directly and thoroughly address the question?
- Deduct points if partially relevant, off-topic, or incomplete.
- If the answer correctly refuses to answer an unanswerable question, score 1.0.

OUTPUT RULES: Respond with ONLY a JSON object — no reasoning, no preamble, no markdown.
Format: {"score": <float 0.0-1.0>, "reason": "<one sentence>"}"""

    user_prompt = f"""QUESTION:
{question}

ANSWER:
{answer}

JSON:"""

    response = judge_completion(system_prompt, user_prompt)
    return _parse_json_score(response)


def score_context_precision(question: str, contexts: list[str]) -> float:
    """Measure what fraction of retrieved contexts are relevant to the question.

    Context Precision ∈ [0.0, 1.0]:
    - 1.0: all retrieved chunks are relevant to the question
    - 0.5: about half the chunks are relevant, half are noise
    - 0.0: none of the chunks are relevant (pure noise)

    Args:
        question: The user's question
        contexts: List of retrieved context chunks

    Returns:
        Context Precision score 0.0-1.0
    """
    contexts_text = "\n\n".join(f"[Chunk {i+1}]\n{ctx}" for i, ctx in enumerate(contexts))

    system_prompt = """You are an impartial RAG evaluation judge. Assess context precision.

Context Precision: Of the retrieved chunks, what fraction is relevant to answering the question?
- A chunk is relevant if it contains information that helps answer the question.
- Calculate: (# relevant chunks) / (total # chunks)

OUTPUT RULES: Respond with ONLY a JSON object — no reasoning, no preamble, no markdown.
Format: {"score": <float 0.0-1.0>, "reason": "<one sentence>"}"""

    user_prompt = f"""QUESTION:
{question}

RETRIEVED CONTEXTS:
{contexts_text}

JSON:"""

    response = judge_completion(system_prompt, user_prompt)
    return _parse_json_score(response)


def score_context_recall(reference: str, contexts: list[str]) -> float:
    """Measure what fraction of facts in the reference answer are covered by contexts.

    Context Recall ∈ [0.0, 1.0]:
    - 1.0: all reference facts are covered by the contexts
    - 0.5: about half the reference facts are in the contexts
    - 0.0: none of the reference facts are in the contexts

    Args:
        reference: The ground-truth reference answer
        contexts: List of retrieved context chunks

    Returns:
        Context Recall score 0.0-1.0
    """
    contexts_text = "\n\n".join(f"[Chunk {i+1}]\n{ctx}" for i, ctx in enumerate(contexts))

    system_prompt = """You are an impartial RAG evaluation judge. Assess context recall.

Context Recall: What fraction of the facts in the reference answer are covered by the retrieved contexts?
- Extract key facts from the reference answer.
- Check if each fact appears (exactly or equivalently) in at least one context chunk.
- Calculate: (# facts covered) / (total # facts in reference)

OUTPUT RULES: Respond with ONLY a JSON object — no reasoning, no preamble, no markdown.
Format: {"score": <float 0.0-1.0>, "reason": "<one sentence>"}"""

    user_prompt = f"""REFERENCE ANSWER:
{reference}

RETRIEVED CONTEXTS:
{contexts_text}

JSON:"""

    response = judge_completion(system_prompt, user_prompt)
    return _parse_json_score(response)


def is_correct_refusal(answer: str) -> bool:
    """Return True if the answer is the canonical refusal produced by the retriever.

    The eval pipeline now sets answer = REFUSAL_MESSAGE directly when the
    similarity threshold is not met (mirroring retriever.py), so an exact
    match is both correct and sufficient.
    """
    return answer.strip() == REFUSAL_MESSAGE.strip()
