"""Authentication & the TenantContext — the application-layer half of tenant isolation.

A request is authenticated by its Supabase access token (JWT). We verify it with the
project's JWT secret and extract:
  * user_id   -> the `sub` claim
  * tenant_id -> the custom `tenant_id` claim injected by the Supabase auth hook
  * role      -> the custom `tenant_role` claim

The resulting `TenantContext` is threaded through every service call. A token without
a tenant_id claim is rejected: no request can act without a tenant.
"""

from __future__ import annotations

from dataclasses import dataclass

import jwt
from fastapi import Depends, Header, HTTPException, status

from app.core.config import Settings, get_settings


@dataclass(frozen=True, slots=True)
class TenantContext:
    """Everything downstream needs to act on behalf of exactly one firm."""

    user_id: str
    tenant_id: str
    role: str
    access_token: str  # forwarded to Supabase so DB calls run under RLS


def _bearer_token(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header",
        )
    return authorization.split(" ", 1)[1].strip()


def get_tenant_context(
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> TenantContext:
    """FastAPI dependency: verify the JWT and build the TenantContext (fail-closed)."""
    token = _bearer_token(authorization)

    try:
        claims = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
    except jwt.PyJWTError as exc:  # expired, bad signature, wrong audience, ...
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid access token: {exc}",
        ) from exc

    user_id = claims.get("sub")
    tenant_id = claims.get("tenant_id")
    role = claims.get("tenant_role", "member")

    if not user_id or not tenant_id:
        # Fail closed: a token with no tenant claim cannot be allowed to query data.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token is missing a tenant_id claim — user is not assigned to a firm",
        )

    return TenantContext(
        user_id=user_id, tenant_id=tenant_id, role=role, access_token=token
    )
