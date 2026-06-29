"""Supabase client factories.

Two flavours, used deliberately:

* `service_client()` — uses the service-role key. It BYPASSES RLS, so it is used only
  for trusted server-side writes during ingestion, and every write still sets tenant_id
  explicitly from the TenantContext.

* `user_client(ctx)` — authenticated as the calling user (their access token attached as
  the PostgREST Authorization header). All reads/RPC through it run UNDER RLS, so tenant
  isolation is enforced by the database engine — the strong boundary used for retrieval.
"""

from __future__ import annotations

from functools import lru_cache

from supabase import Client, create_client

from app.core.config import get_settings
from app.core.security import TenantContext


@lru_cache
def service_client() -> Client:
    """Shared service-role client (RLS-bypassing). Server-side trusted writes only."""
    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


def user_client(ctx: TenantContext) -> Client:
    """Per-request client authenticated AS the caller → all calls honour RLS."""
    settings = get_settings()
    client = create_client(settings.supabase_url, settings.supabase_anon_key)
    # Attach the user's JWT so PostgREST/RPC/Storage run under their identity, which
    # makes public.current_tenant_id() resolve to this firm and RLS apply.
    client.postgrest.auth(ctx.access_token)
    return client
