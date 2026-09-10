"""LLM-as-judge scoring functions for RAG quality evaluation.

Metrics: Faithfulness, Answer Relevance, Context Precision, Context Recall.
All metrics score 0.0-1.0. Uses NVIDIA NIM LLM with JSON output parsing.
"""

import json
import logging

from app.config import settings
from app.llm.nvidia_client import _client, _strip_thinking
from app.retrieval.retriever import REFUSAL_MESSAGE

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


def _parse_json_score(response: str) -> float:
    """Extract {"score": <float>} from LLM response, default to 0.0 on parse error."""
    try:
        data = json.loads(response)
        score = float(data.get("score", 0.0))
        return max(0.0, min(1.0, score))  # Clamp to [0.0, 1.0]
    except (json.JSONDecodeError, ValueError, TypeError) as e:
        logger.warning(f"Failed to parse score JSON: {response[:100]}... Error: {e}")
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

    system_prompt = """You are an impartial RAG evaluation judge. Your task is to assess faithfulness.

Faithfulness: Does the answer contain only claims that are directly supported by the provided contexts?
- Every factual claim in the answer should be traceable to at least one context chunk.
- If the answer includes information NOT in the contexts, or contradicts them, reduce the score.

Respond with JSON: {"score": <float between 0.0 and 1.0>, "reason": "<brief explanation>"}"""

    user_prompt = f"""Evaluate the faithfulness of this answer against the contexts below.

CONTEXTS:
{contexts_text}

ANSWER:
{answer}

Provide your judgment as JSON."""

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
    system_prompt = """You are an impartial RAG evaluation judge. Your task is to assess answer relevance.

Answer Relevance: Does the answer directly and thoroughly address the question asked?
- The answer should focus on answering the question without padding.
- Deduct points if the answer is partially relevant, off-topic, or incomplete.
- If the answer correctly refuses to answer an unanswerable question, score 1.0.

Respond with JSON: {"score": <float between 0.0 and 1.0>, "reason": "<brief explanation>"}"""

    user_prompt = f"""Evaluate how well the answer addresses the question.

QUESTION:
{question}

ANSWER:
{answer}

Provide your judgment as JSON."""

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

    system_prompt = """You are an impartial RAG evaluation judge. Your task is to assess context precision.

Context Precision: Of the retrieved chunks, what fraction is actually relevant to answering the question?
- A chunk is relevant if it contains information that could help answer the question.
- A chunk is irrelevant if it is off-topic or unrelated noise.
- Calculate: (# relevant chunks) / (total # chunks)

Respond with JSON: {"score": <float between 0.0 and 1.0>, "reason": "<brief explanation of which chunks were relevant/irrelevant>"}"""

    user_prompt = f"""Evaluate the precision of these retrieved contexts for the given question.

QUESTION:
{question}

RETRIEVED CONTEXTS:
{contexts_text}

Provide your judgment as JSON."""

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

    system_prompt = """You are an impartial RAG evaluation judge. Your task is to assess context recall.

Context Recall: Of the facts/claims in the reference answer, what fraction is covered by the retrieved contexts?
- Extract key facts from the reference answer.
- Check if each fact appears (exactly or equivalently) in at least one context chunk.
- Calculate: (# facts covered by contexts) / (total # facts in reference)

Respond with JSON: {"score": <float between 0.0 and 1.0>, "reason": "<brief explanation of which facts were/weren't covered>"}"""

    user_prompt = f"""Evaluate how well the retrieved contexts cover the facts in this reference answer.

REFERENCE ANSWER:
{reference}

RETRIEVED CONTEXTS:
{contexts_text}

Provide your judgment as JSON."""

    response = judge_completion(system_prompt, user_prompt)
    return _parse_json_score(response)


def is_correct_refusal(answer: str) -> bool:
    """Return True if the answer is the canonical refusal produced by the retriever.

    The eval pipeline now sets answer = REFUSAL_MESSAGE directly when the
    similarity threshold is not met (mirroring retriever.py), so an exact
    match is both correct and sufficient.
    """
    return answer.strip() == REFUSAL_MESSAGE.strip()
