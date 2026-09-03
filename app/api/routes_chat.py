from fastapi import APIRouter
from pydantic import BaseModel

from app.retrieval.retriever import retrieve_and_answer

router = APIRouter(prefix="/api", tags=["chat"])


class ChatRequest(BaseModel):
    message: str
    selectedDocId: int | None = None


class Citation(BaseModel):
    source: str | None = None
    page: int | None = None
    sheet: str | None = None
    row: str | None = None
    snippet: str


class ChatResponse(BaseModel):
    content: str
    citations: list[Citation]


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    result = retrieve_and_answer(request.message, document_id=request.selectedDocId)
    return ChatResponse(**result)
