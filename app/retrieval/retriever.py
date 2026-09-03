from app.config import settings
from app.ingestion.embedder import embed_query
from app.llm.prompts import build_user_prompt
from app.retrieval.vector_store import search

REFUSAL_MESSAGE = (
    "I couldn't find anything in the uploaded documents that answers this question. "
    "Please try rephrasing, or upload a document that covers this topic."
)


def _to_citation(row: dict) -> dict:
    metadata = row["metadata"]
    citation = {"source": metadata.get("source"), "snippet": row["content"][:280]}
    if "page" in metadata:
        citation["page"] = metadata["page"]
    if "sheet" in metadata:
        citation["sheet"] = metadata["sheet"]
        citation["row"] = metadata.get("row")
    return citation


def retrieve_and_answer(
    question: str,
    document_id: int | None = None,
    top_k: int | None = None,
) -> dict:
    from app.llm.nvidia_client import chat_completion  # lazy import keeps module import-order flexible

    query_embedding = embed_query(question)
    rows = search(query_embedding, top_k or settings.top_k, document_id=document_id)

    if not rows or rows[0]["similarity"] < settings.similarity_threshold:
        return {"content": REFUSAL_MESSAGE, "citations": []}

    context_blocks = [row["content"] for row in rows]
    prompt = build_user_prompt(question, context_blocks)
    answer = chat_completion(prompt)

    citations = [_to_citation(row) for row in rows]
    return {"content": answer, "citations": citations}
