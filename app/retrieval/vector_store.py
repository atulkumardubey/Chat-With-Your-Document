import json

import psycopg2.extras

from app.db import get_vector_connection
from app.ingestion.chunkers import Chunk
from app.ingestion.embedder import embed_texts


def _to_vector_literal(vector: list[float]) -> str:
    # psycopg2 has no built-in adapter for plain python lists -> pgvector's `vector` type
    # (it would otherwise be sent as numeric[], which the <=> operator rejects).
    return "[" + ",".join(repr(v) for v in vector) + "]"


def insert_chunks(document_id: int, chunks: list[Chunk]) -> None:
    if not chunks:
        return
    vectors = embed_texts([c.text for c in chunks])
    rows = [
        (
            document_id,
            chunk.text,
            json.dumps(chunk.metadata),
            _to_vector_literal(vector),
            chunk.metadata.get("chunk_strategy"),
            chunk.metadata.get("format"),
        )
        for chunk, vector in zip(chunks, vectors)
    ]
    with get_vector_connection() as conn:
        with conn.cursor() as cur:
            psycopg2.extras.execute_values(
                cur,
                """
                INSERT INTO chunks (document_id, content, metadata, embedding, chunk_strategy, source_format)
                VALUES %s
                """,
                rows,
                template="(%s, %s, %s, %s::vector, %s, %s)",
            )


def search(
    query_embedding: list[float],
    top_k: int,
    document_id: int | None = None,
    chunk_strategy: str | None = None,
    source_format: str | None = None,
) -> list[dict]:
    """Cosine similarity search. Embeddings are pre-normalized so similarity = 1 - cosine_distance."""
    embedding_literal = _to_vector_literal(query_embedding)
    filters = []
    params: list = [embedding_literal]
    if document_id is not None:
        filters.append("document_id = %s")
        params.append(document_id)
    if chunk_strategy is not None:
        filters.append("chunk_strategy = %s")
        params.append(chunk_strategy)
    if source_format is not None:
        filters.append("source_format = %s")
        params.append(source_format)

    where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
    params.extend([embedding_literal, top_k])

    sql = f"""
        SELECT id, document_id, content, metadata, 1 - (embedding <=> %s::vector) AS similarity
        FROM chunks
        {where_clause}
        ORDER BY embedding <=> %s::vector
        LIMIT %s
    """

    with get_vector_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return [dict(row) for row in cur.fetchall()]
