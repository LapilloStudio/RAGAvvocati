"""RAG answer generation with Gemini + prompt-based citations.

Each retrieved chunk is numbered as [Fonte N] in the context block sent to Gemini.
The model is instructed to cite inline as [Fonte N]; we then parse those references
back to chunk filename + page so every claim carries a verifiable source.
"""

from __future__ import annotations

import logging
import re

import google.generativeai as genai

from app.core.config import Settings, get_settings
from app.models.schemas import Citation, RetrievedChunk

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "Sei un assistente per studi legali e commercialisti italiani. "
    "Rispondi in italiano, in modo preciso e professionale. "
    "Basa la risposta ESCLUSIVAMENTE sui documenti forniti come fonti. "
    "Cita le fonti pertinenti inline usando il formato [Fonte N] (es. [Fonte 1]). "
    "Se l'informazione non è presente nelle fonti, dichiaralo esplicitamente e non inventare."
)


def _build_context(chunks: list[RetrievedChunk]) -> str:
    parts: list[str] = []
    for i, chunk in enumerate(chunks, 1):
        header = f"[Fonte {i}] {chunk.filename or 'documento'}"
        if chunk.page is not None:
            header += f" (pag. {chunk.page})"
        parts.append(f"{header}\n---\n{chunk.content}")
    return "\n\n".join(parts)


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

    genai.configure(api_key=settings.gemini_api_key)
    model = genai.GenerativeModel(
        model_name=settings.gemini_model,
        system_instruction=SYSTEM_PROMPT,
    )

    context = _build_context(chunks)
    prompt = (
        f"{context}\n\n"
        f"Domanda: {query}\n\n"
        "Rispondi citando le fonti come [Fonte N] dove rilevante."
    )

    response = await model.generate_content_async(
        prompt,
        generation_config=genai.GenerationConfig(max_output_tokens=settings.gemini_max_tokens),
    )

    answer = response.text.strip() if response.text else ""
    citations = _extract_citations(answer, chunks)
    return answer, citations


def _extract_citations(answer: str, chunks: list[RetrievedChunk]) -> list[Citation]:
    """Parse [Fonte N] references in the answer and map them to chunk metadata."""
    seen_indices: set[int] = set()
    citations: list[Citation] = []

    for match in re.finditer(r"\[Fonte\s+(\d+)\]", answer, re.IGNORECASE):
        idx = int(match.group(1)) - 1  # convert 1-based to 0-based
        if idx < 0 or idx >= len(chunks) or idx in seen_indices:
            continue
        seen_indices.add(idx)
        chunk = chunks[idx]
        citations.append(
            Citation(
                document_id=chunk.document_id,
                filename=chunk.filename,
                page=chunk.page,
                cited_text=None,  # Gemini doesn't return the exact cited span
            )
        )

    return citations
