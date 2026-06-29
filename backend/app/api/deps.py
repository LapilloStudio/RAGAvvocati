"""Shared FastAPI dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from app.core.security import TenantContext, get_tenant_context

# Every protected route depends on this: a verified, tenant-scoped identity.
CurrentTenant = Annotated[TenantContext, Depends(get_tenant_context)]
