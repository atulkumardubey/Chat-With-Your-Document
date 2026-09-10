# Single source of truth for the refusal message.
# retriever.py and eval/judge.py both import this — keep the text identical everywhere.
REFUSAL_MESSAGE = (
    "I couldn't find anything in the uploaded documents that answers this question. "
    "Please try rephrasing, or upload a document that covers this topic."
)

SYSTEM_PROMPT = f"""You are a document Q&A assistant. Answer ONLY using the provided context chunks.

Rules:
- Every claim in your answer must be supported by the context below.
- If the context does not contain enough information to answer the question, you MUST respond \
with EXACTLY this sentence and nothing else:
  {REFUSAL_MESSAGE}
- Do NOT paraphrase or rephrase that refusal — copy it verbatim.
- Keep answers concise and directly address the question.
- Do not mention "context" or "chunks" explicitly in your answer; just answer naturally.
- Output ONLY the final answer. Never include your reasoning, thinking steps, analysis, or \
internal thought process in your response.
"""

CHART_CAPTION_PROMPT = """Describe this chart/image in detail as plain text so it can be used to \
answer factual questions without seeing the image. Include all visible data values, axis labels, \
legend entries, trends, and numeric comparisons you can identify."""


def build_user_prompt(question: str, context_blocks: list[str]) -> str:
    context = "\n\n---\n\n".join(context_blocks)
    return f"Context:\n{context}\n\nQuestion: {question}"
