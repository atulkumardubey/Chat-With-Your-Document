from contextlib import contextmanager

import psycopg2
import psycopg2.extras
from pgvector.psycopg2 import register_vector

from app.config import settings


@contextmanager
def get_connection():
    conn = psycopg2.connect(
        host=settings.db_host,
        port=settings.db_port,
        dbname=settings.db_name,
        user=settings.db_user,
        password=settings.db_password,
    )
    # Without this, psycopg2 can negotiate a non-UTF8 client encoding on some Windows/locale
    # setups, causing "'ascii' codec can't encode character" on text with non-ASCII punctuation
    # (en-dashes, curly quotes, etc. commonly extracted from PDFs).
    conn.set_client_encoding("UTF8")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def get_vector_connection():
    """Like get_connection, but registers the pgvector type adapter.

    Requires `CREATE EXTENSION vector` to have already run (see init_schema),
    so it must not be used for the initial schema-creation connection.
    """
    with get_connection() as conn:
        register_vector(conn)
        yield conn


DOCUMENTS_TABLE_SQL = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS documents (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('pdf', 'excel')),
    pages INT,
    sheets INT,
    status TEXT NOT NULL DEFAULT 'indexing' CHECK (status IN ('indexing', 'indexed', 'failed')),
    error TEXT,
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

ADD_ERROR_COLUMN_SQL = "ALTER TABLE documents ADD COLUMN IF NOT EXISTS error TEXT"

# embedding dimension can't be parameterized via psycopg2 placeholders, so it's inlined directly.
CHUNKS_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS chunks (
    id SERIAL PRIMARY KEY,
    document_id INT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb,
    embedding VECTOR({settings.embedding_dim}) NOT NULL,
    chunk_strategy TEXT NOT NULL,
    source_format TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

INDEXES_SQL = """
-- Drop the old IVFFlat index (broke on near-empty tables — lists never retrained).
DROP INDEX IF EXISTS chunks_embedding_cosine_idx;

-- Fast filter on document_id: every search query applies this predicate.
CREATE INDEX IF NOT EXISTS chunks_document_id_idx
    ON chunks (document_id);

-- Sort order used by GET /api/documents.
CREATE INDEX IF NOT EXISTS documents_uploaded_at_idx
    ON documents (uploaded_at DESC);

-- HNSW vector index for cosine similarity.
-- Unlike IVFFlat, HNSW builds incrementally so it works correctly at any data size.
CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw_idx
    ON chunks USING hnsw (embedding vector_cosine_ops);
"""


def init_schema() -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(DOCUMENTS_TABLE_SQL)
            cur.execute(ADD_ERROR_COLUMN_SQL)
            cur.execute(CHUNKS_TABLE_SQL)
            cur.execute(INDEXES_SQL)


if __name__ == "__main__":
    init_schema()
    print("Schema initialized successfully")
