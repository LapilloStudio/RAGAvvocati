"""Retrieval: embed the query and fetch the most similar chunks for THIS tenant.

The RPC call goes through the per-user Supabase client, so it runs under RLS:
`match_document_chunks` only ever returns rows where
tenant_id = public.current_tenant_id(). Isolation is enforced by Postgres, not by us.
"""

from __future__ import annotations

from app.core.config import get_settings
from app.core.security import TenantContext
from app.core.supabase import user_client
from app.models.schemas import RetrievedChunk
from app.services.embeddings import get_embedding_provider


async def retrieve(
    ctx: TenantContext, query: str, *, document_id: str | None = None
) -> list[RetrievedChunk]:
    settings = get_settings()
    provider = get_embedding_provider(settings)
    query_embedding = await provider.embed_query(query)

    sb = user_client(ctx)  # authenticated as the caller → RLS applies

    result = sb.rpc(
        "match_document_chunks",
        {
            "query_embedding": query_embedding,
            "match_count": settings.retrieval_top_k,
            "filter_document_id": document_id,
        },
    ).execute()
    rows = result.data or []

    # Enrich with filenames for citations (also RLS-scoped).
    doc_ids = sorted({r["document_id"] for r in rows})
    filenames: dict[str, str] = {}
    if doc_ids:
        docs = (
            sb.table("documents").select("id, filename").in_("id", doc_ids).execute().data
            or []
        )
        filenames = {d["id"]: d["filename"] for d in docs}

    return [
        RetrievedChunk(
            id=r["id"],
            document_id=r["document_id"],
            content=r["content"],
            page=r.get("page"),
            similarity=r.get("similarity", 0.0),
            filename=filenames.get(r["document_id"]),
        )
        for r in rows
    ]
