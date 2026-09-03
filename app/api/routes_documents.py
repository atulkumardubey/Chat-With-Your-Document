import os
import tempfile
import traceback

from fastapi import APIRouter, HTTPException, UploadFile
from pydantic import BaseModel

from app.config import settings
from app.db import get_connection
from app.ingestion.chunkers import chunk_units
from app.ingestion.excel_parser import get_sheet_count, parse_excel
from app.ingestion.pdf_parser import get_page_count, parse_pdf
from app.retrieval.vector_store import insert_chunks

router = APIRouter(prefix="/api", tags=["documents"])


class DocumentOut(BaseModel):
    id: int
    name: str
    type: str
    pages: int | None = None
    sheets: int | None = None
    status: str
    uploadedAt: str


def _row_to_document(row: dict) -> DocumentOut:
    return DocumentOut(
        id=row["id"],
        name=row["name"],
        type=row["type"],
        pages=row["pages"],
        sheets=row["sheets"],
        status=row["status"],
        uploadedAt=row["uploaded_at"].isoformat(),
    )


@router.get("/documents", response_model=list[DocumentOut])
def list_documents() -> list[DocumentOut]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, name, type, pages, sheets, status, uploaded_at FROM documents ORDER BY uploaded_at DESC"
            )
            columns = [desc[0] for desc in cur.description]
            rows = [dict(zip(columns, row)) for row in cur.fetchall()]
    return [_row_to_document(row) for row in rows]


@router.delete("/documents/{doc_id}")
def delete_document(doc_id: int) -> dict:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM documents WHERE id = %s", (doc_id,))
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Document not found")
    return {"success": True}


@router.post("/upload", response_model=DocumentOut)
async def upload_document(file: UploadFile) -> DocumentOut:
    filename = file.filename or "upload"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in {"pdf", "xlsx", "xls"}:
        raise HTTPException(status_code=400, detail="Only .pdf, .xlsx, .xls files are supported")

    doc_type = "pdf" if ext == "pdf" else "excel"
    contents = await file.read()

    with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmp:
        tmp.write(contents)
        tmp_path = tmp.name

    try:
        pages = sheets = None
        if doc_type == "pdf":
            pages = get_page_count(tmp_path)
        else:
            sheets = get_sheet_count(tmp_path)

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO documents (name, type, pages, sheets, status)
                    VALUES (%s, %s, %s, %s, 'indexing')
                    RETURNING id, name, type, pages, sheets, status, uploaded_at
                    """,
                    (filename, doc_type, pages, sheets),
                )
                columns = [desc[0] for desc in cur.description]
                doc_row = dict(zip(columns, cur.fetchone()))

        try:
            if doc_type == "pdf":
                units = parse_pdf(tmp_path, filename)
            else:
                units = parse_excel(tmp_path, filename, settings.default_excel_format)

            chunks = chunk_units(units, settings.default_chunk_strategy)
            insert_chunks(doc_row["id"], chunks)
            new_status = "indexed"
            error_message = None
        except Exception as exc:
            traceback.print_exc()
            new_status = "failed"
            error_message = str(exc)

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE documents SET status = %s, error = %s WHERE id = %s RETURNING uploaded_at",
                    (new_status, error_message, doc_row["id"]),
                )
                (uploaded_at,) = cur.fetchone()

        doc_row["status"] = new_status
        doc_row["uploaded_at"] = uploaded_at
        return _row_to_document(doc_row)
    finally:
        os.unlink(tmp_path)
