"""RAG answer generation with Claude + native Citations.

Each retrieved chunk is passed to Claude as a `document` content block with
`citations: {enabled: true}`. The model's answer comes back split into text blocks whose
`citations` arrays reference the document blocks by index — we map those back to the
chunk's filename + page so every claim carries a verifiable source. This is the PRD's
"strict citations" requirement, served by the API rather than hand-stitched.

Generation uses claude-opus-4-8, streamed (large max_tokens). The Anthropic API does not
train on API traffic; enable Zero Data Retention at the org level and optionally pin EU
inference via ANTHROPIC_INFERENCE_GEO for the GDPR story.
"""

from __future__ import annotations

import logging

from anthropic import AsyncAnthropic

from app.core.config import Settings, get_settings
from app.models.schemas import Citation, RetrievedChunk

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "Sei un assistente per studi legali e commercialisti italiani. "
    "Rispondi in italiano, in modo preciso e professionale. "
    "Basa la risposta ESCLUSIVAMENTE sui documenti forniti come fonti. "
    "Se l'informazione non è presente nelle fonti, dichiaralo esplicitamente e non "
    "inventare. Cita sempre le fonti pertinenti."
)


def _build_document_blocks(chunks: list[RetrievedChunk]) -> list[dict]:
    """One document block per retrieved chunk, with citations enabled."""
    blocks: list[dict] = []
    for chunk in chunks:
        blocks.append(
            {
                "type": "document",
                "source": {
                    "type": "content",
                    "content": [{"type": "text", "text": chunk.content}],
                },
                "title": chunk.filename or "documento",
                "context": f"pagina {chunk.page}" if chunk.page is not None else None,
                "citations": {"enabled": True},
            }
        )
    return blocks


async def generate_answer(
    query: str, chunks: list[RetrievedChunk], settings: Settings | None = None
) -> tuple[str, list[Citation]]:
    """Return (answer_text, citations). Falls back gracefully when no sources match."""
    settings = settings or get_settings()

    if not chunks:
        return (
            "Non ho trovato informazioni pertinenti nei documenti del tuo studio per "
            "rispondere a questa domanda.",
            [],
        )

    client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    content: list[dict] = _build_document_blocks(chunks)
    content.append({"type": "text", "text": query})

    extra: dict = {}
    if settings.anthropic_inference_geo:
        extra["inference_geo"] = settings.anthropic_inference_geo

    async with client.messages.stream(
        model=settings.anthropic_model,
        max_tokens=settings.anthropic_max_tokens,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": content}],
        **extra,
    ) as stream:
        message = await stream.get_final_message()

    return _extract(message, chunks)


def _extract(message, chunks: list[RetrievedChunk]) -> tuple[str, list[Citation]]:
    """Pull answer text + map API citations back to chunk filename/page."""
    answer_parts: list[str] = []
    citations: list[Citation] = []
    seen: set[tuple[str | None, int | None, str | None]] = set()

    for block in message.content:
        if getattr(block, "type", None) != "text":
            continue
        answer_parts.append(block.text)
        for cit in getattr(block, "citations", None) or []:
            idx = getattr(cit, "document_index", None)
            chunk = chunks[idx] if idx is not None and 0 <= idx < len(chunks) else None
            key = (
                chunk.document_id if chunk else None,
                chunk.page if chunk else None,
                getattr(cit, "cited_text", None),
            )
            if key in seen:
                continue
            seen.add(key)
            citations.append(
                Citation(
                    document_id=chunk.document_id if chunk else None,
                    filename=chunk.filename if chunk else getattr(cit, "document_title", None),
                    page=chunk.page if chunk else None,
                    cited_text=getattr(cit, "cited_text", None),
                )
            )

    return "".join(answer_parts).strip(), citations
