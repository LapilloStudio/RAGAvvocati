"""FastAPI application entrypoint."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import chat, documents
from app.core.config import get_settings

settings = get_settings()
logging.basicConfig(level=settings.log_level)

app = FastAPI(
    title="RAGAvvocati API",
    version="0.1.0",
    description="Multi-tenant B2B RAG backend for professional firms.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_V1 = "/api/v1"
app.include_router(documents.router, prefix=API_V1)
app.include_router(chat.router, prefix=API_V1)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}
