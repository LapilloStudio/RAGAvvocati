"""API request/response models."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


# ---- Documents --------------------------------------------------------------
class DocumentOut(BaseModel):
    id: str
    filename: str
    mime_type: str
    status: str  # processing | ready | failed
    size_bytes: int | None = None
    created_at: datetime | None = None


class DocumentUploadResponse(BaseModel):
    document: DocumentOut
    message: str = "Document accepted; processing started."


# ---- Chat / RAG -------------------------------------------------------------
class Citation(BaseModel):
    """A verifiable source reference attached to an answer."""

    document_id: str | None = None
    filename: str | None = None
    page: int | None = None
    cited_text: str | None = None


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    session_id: str | None = None
    document_id: str | None = None  # optional: restrict to one document


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    citations: list[Citation] = Field(default_factory=list)


# ---- Retrieval (internal) ---------------------------------------------------
class RetrievedChunk(BaseModel):
    id: str
    document_id: str
    content: str
    page: int | None = None
    similarity: float = 0.0
    filename: str | None = None
