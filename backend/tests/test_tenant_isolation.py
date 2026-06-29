"""Tenant-isolation gate.

Two layers are tested:

1. Always-on unit checks (no network): the JWT → TenantContext boundary fails closed,
   rejects bad/expired/claimless tokens, and the fake embedding provider is deterministic
   and correctly dimensioned.

2. Integration check (opt-in: set RUN_DB_TESTS=1 with a configured Supabase): seed two
   tenants + a chunk each, then assert that querying match_document_chunks under tenant
   A's JWT never returns tenant B's rows — i.e. RLS holds at the database engine.
"""

from __future__ import annotations

import os
import time
import uuid

import jwt
import pytest
from fastapi import HTTPException

from app.core.config import Settings
from app.core.security import get_tenant_context
from app.services.embeddings import FakeEmbeddingProvider

JWT_SECRET = "test-secret-key-at-least-32-bytes-long-000"


def _settings(**over) -> Settings:
    base = dict(
        supabase_jwt_secret=JWT_SECRET,
        embeddings_provider="fake",
        embeddings_dimension=8,
    )
    base.update(over)
    return Settings(**base)


def _token(tenant_id: str | None, *, secret: str = JWT_SECRET, role: str = "member") -> str:
    claims = {
        "sub": str(uuid.uuid4()),
        "aud": "authenticated",
        "exp": int(time.time()) + 3600,
        "tenant_role": role,
    }
    if tenant_id is not None:
        claims["tenant_id"] = tenant_id
    return jwt.encode(claims, secret, algorithm="HS256")


# ---- Layer 1: always-on unit checks ----------------------------------------
def test_valid_token_yields_tenant_context():
    tid = str(uuid.uuid4())
    ctx = get_tenant_context(authorization=f"Bearer {_token(tid)}", settings=_settings())
    assert ctx.tenant_id == tid
    assert ctx.role == "member"
    assert ctx.access_token


def test_token_without_tenant_claim_is_rejected():
    with pytest.raises(HTTPException) as exc:
        get_tenant_context(authorization=f"Bearer {_token(None)}", settings=_settings())
    assert exc.value.status_code == 403  # fail closed: no tenant → no access


def test_missing_authorization_header_is_rejected():
    with pytest.raises(HTTPException) as exc:
        get_tenant_context(authorization=None, settings=_settings())
    assert exc.value.status_code == 401


def test_bad_signature_is_rejected():
    token = _token(str(uuid.uuid4()), secret="attacker-secret")
    with pytest.raises(HTTPException) as exc:
        get_tenant_context(authorization=f"Bearer {token}", settings=_settings())
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_fake_embeddings_are_deterministic_and_dimensioned():
    provider = FakeEmbeddingProvider(dimension=8)
    a = await provider.embed_query("contratto di locazione")
    b = await provider.embed_query("contratto di locazione")
    assert a == b
    assert len(a) == 8
    assert all(-1.0 <= x <= 1.0 for x in a)


# ---- Layer 2: live RLS check (opt-in) --------------------------------------
@pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1",
    reason="Set RUN_DB_TESTS=1 with a configured Supabase to run the live RLS check.",
)
@pytest.mark.asyncio
async def test_rls_blocks_cross_tenant_retrieval():
    """Seed two tenants; tenant A's query must never surface tenant B's chunks."""
    from app.core.security import TenantContext
    from app.core.supabase import service_client, user_client

    settings = Settings()  # real env
    sb = service_client()

    tenant_a, tenant_b = str(uuid.uuid4()), str(uuid.uuid4())
    sb.table("tenants").insert(
        [{"id": tenant_a, "name": "A"}, {"id": tenant_b, "name": "B"}]
    ).execute()

    dim = settings.embeddings_dimension
    vec_a = [0.1] * dim
    vec_b = [0.9] * dim
    doc_a, doc_b = str(uuid.uuid4()), str(uuid.uuid4())
    for tid, did, vec, fn in (
        (tenant_a, doc_a, vec_a, "alpha.pdf"),
        (tenant_b, doc_b, vec_b, "beta.pdf"),
    ):
        sb.table("documents").insert(
            {"id": did, "tenant_id": tid, "filename": fn, "storage_path": f"{tid}/{did}/{fn}",
             "mime_type": "application/pdf", "status": "ready"}
        ).execute()
        sb.table("document_chunks").insert(
            {"tenant_id": tid, "document_id": did, "chunk_index": 0,
             "content": f"secret of {fn}", "page": 1, "embedding": vec}
        ).execute()

    # Query AS tenant A using A's JWT (signed with the real project secret).
    ctx_a = TenantContext(
        user_id=str(uuid.uuid4()),
        tenant_id=tenant_a,
        role="admin",
        access_token=_token(tenant_a, secret=settings.supabase_jwt_secret, role="admin"),
    )
    rows = (
        user_client(ctx_a)
        .rpc("match_document_chunks", {"query_embedding": vec_b, "match_count": 50})
        .execute()
        .data
        or []
    )

    returned_docs = {r["document_id"] for r in rows}
    assert doc_b not in returned_docs, "RLS LEAK: tenant A retrieved tenant B's chunk"
    assert returned_docs <= {doc_a}
