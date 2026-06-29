"""RAG chat endpoint: retrieve (RLS-scoped) → generate (Claude + citations) → persist."""

from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.api.deps import CurrentTenant
from app.core.supabase import user_client
from app.models.schemas import ChatRequest, ChatResponse
from app.services import rag, retrieval

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(ctx: CurrentTenant, body: ChatRequest) -> ChatResponse:
    # 1. Retrieve relevant chunks — only this tenant's data (enforced by RLS).
    chunks = await retrieval.retrieve(ctx, body.message, document_id=body.document_id)

    # 2. Generate a grounded answer with verifiable citations.
    answer, citations = await rag.generate_answer(body.message, chunks)

    # 3. Persist the turn (tenant-tagged).
    sb = user_client(ctx)
    session_id = body.session_id or str(uuid.uuid4())
    if not body.session_id:
        sb.table("chat_sessions").insert(
            {"id": session_id, "tenant_id": ctx.tenant_id, "user_id": ctx.user_id,
             "title": body.message[:80]}
        ).execute()

    sb.table("chat_messages").insert(
        [
            {"tenant_id": ctx.tenant_id, "session_id": session_id, "role": "user",
             "content": body.message},
            {"tenant_id": ctx.tenant_id, "session_id": session_id, "role": "assistant",
             "content": answer, "citations": [c.model_dump() for c in citations]},
        ]
    ).execute()

    return ChatResponse(session_id=session_id, answer=answer, citations=citations)
