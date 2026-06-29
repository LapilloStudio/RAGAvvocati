"""Document ingestion + listing endpoints. All scoped to the caller's tenant."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile, status

from app.api.deps import CurrentTenant
from app.core.supabase import user_client
from app.models.schemas import DocumentOut, DocumentUploadResponse
from app.services import ingestion, parsing

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("", response_model=DocumentUploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    ctx: CurrentTenant,
    background: BackgroundTasks,
    file: UploadFile = File(...),
) -> DocumentUploadResponse:
    mime_type = file.content_type or ""
    if mime_type not in parsing.SUPPORTED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type: {mime_type}. Allowed: PDF, DOCX, XLSX.",
        )

    data = await file.read()
    document = await ingestion.create_document(
        ctx, filename=file.filename or "document", mime_type=mime_type, data=data
    )

    # Parse/chunk/embed off the request path.
    background.add_task(
        ingestion.process_document,
        ctx,
        document_id=document.id,
        data=data,
        mime_type=mime_type,
    )
    return DocumentUploadResponse(document=document)


@router.get("", response_model=list[DocumentOut])
async def list_documents(ctx: CurrentTenant) -> list[DocumentOut]:
    # RLS-scoped read: only this tenant's documents are visible.
    sb = user_client(ctx)
    rows = (
        sb.table("documents")
        .select("id, filename, mime_type, status, size_bytes, created_at")
        .order("created_at", desc=True)
        .execute()
        .data
        or []
    )
    return [DocumentOut(**r) for r in rows]
