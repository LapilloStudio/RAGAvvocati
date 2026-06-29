"""Ingestion pipeline: store → parse → chunk → embed → persist.

Tenant isolation is built in from line one: every row written here is tagged with
`ctx.tenant_id` taken from the verified TenantContext — never from client input. Files
are stored under a tenant-prefixed Storage key so the Storage RLS policies apply too.

Writes use the service-role client (trusted server-side), so the explicit tenant_id on
every insert is the load-bearing guard here; retrieval (the read path) additionally runs
under RLS. See app/services/retrieval.py.
"""

from __future__ import annotations

import logging
import uuid

from app.core.config import get_settings
from app.core.security import TenantContext
from app.core.supabase import service_client
from app.models.schemas import DocumentOut
from app.services import parsing
from app.services.embeddings import get_embedding_provider

logger = logging.getLogger(__name__)


def _chunk(text: str, size: int, overlap: int) -> list[str]:
    """Sliding-window character chunker with overlap."""
    text = text.strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]
    chunks: list[str] = []
    start = 0
    step = max(size - overlap, 1)
    while start < len(text):
        chunks.append(text[start : start + size])
        start += step
    return chunks


async def create_document(
    ctx: TenantContext,
    *,
    filename: str,
    mime_type: str,
    data: bytes,
) -> DocumentOut:
    """Store the original file + create the documents row (status=processing)."""
    if mime_type not in parsing.SUPPORTED_MIME_TYPES:
        raise parsing.UnsupportedDocumentError(mime_type)

    settings = get_settings()
    sb = service_client()
    document_id = str(uuid.uuid4())
    storage_path = f"{ctx.tenant_id}/{document_id}/{filename}"

    # 1. Original file → private, tenant-prefixed Storage bucket.
    sb.storage.from_(settings.storage_bucket).upload(
        path=storage_path,
        file=data,
        file_options={"content-type": mime_type, "upsert": "false"},
    )

    # 2. Metadata row — tenant_id stamped from the verified context.
    row = {
        "id": document_id,
        "tenant_id": ctx.tenant_id,
        "filename": filename,
        "storage_path": storage_path,
        "mime_type": mime_type,
        "size_bytes": len(data),
        "status": "processing",
        "uploaded_by": ctx.user_id,
    }
    sb.table("documents").insert(row).execute()
    return DocumentOut(**{k: row[k] for k in ("id", "filename", "mime_type", "status", "size_bytes")})


async def process_document(
    ctx: TenantContext, *, document_id: str, data: bytes, mime_type: str
) -> None:
    """Background task: parse, chunk, embed, and persist chunks; flip status."""
    settings = get_settings()
    sb = service_client()
    provider = get_embedding_provider(settings)

    try:
        segments = parsing.parse(data, mime_type)

        rows: list[dict] = []
        chunk_texts: list[str] = []
        pending: list[dict] = []
        chunk_index = 0
        for seg in segments:
            for piece in _chunk(seg.text, settings.chunk_size, settings.chunk_overlap):
                pending.append({"page": seg.page, "content": piece, "chunk_index": chunk_index})
                chunk_texts.append(piece)
                chunk_index += 1

        embeddings = await provider.embed_batch(chunk_texts)

        for meta, embedding in zip(pending, embeddings, strict=True):
            rows.append(
                {
                    "tenant_id": ctx.tenant_id,  # <- isolation guard on every chunk
                    "document_id": document_id,
                    "chunk_index": meta["chunk_index"],
                    "content": meta["content"],
                    "page": meta["page"],
                    "embedding": embedding,
                }
            )

        if rows:
            sb.table("document_chunks").insert(rows).execute()

        sb.table("documents").update({"status": "ready"}).eq("id", document_id).eq(
            "tenant_id", ctx.tenant_id
        ).execute()
        logger.info("Ingested document %s (%d chunks) for tenant %s",
                    document_id, len(rows), ctx.tenant_id)

    except Exception as exc:  # noqa: BLE001 — record failure, don't crash the worker
        logger.exception("Ingestion failed for document %s", document_id)
        sb.table("documents").update({"status": "failed", "error": str(exc)[:500]}).eq(
            "id", document_id
        ).eq("tenant_id", ctx.tenant_id).execute()
