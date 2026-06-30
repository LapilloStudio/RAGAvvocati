// RAG core in TypeScript: embeddings + retrieval (via the RLS-scoped RPC) +
// Gemini generation with prompt-based citations. No Python backend.

import {
  ChatGoogleGenerativeAI,
  GoogleGenerativeAIEmbeddings,
} from "@langchain/google-genai";
import type { SupabaseClient } from "@supabase/supabase-js";

const EMBED_MODEL = "text-embedding-004"; // 768 dims → matches vector(768)
const CHAT_MODEL = "gemini-2.5-flash";

function makeEmbeddings() {
  return new GoogleGenerativeAIEmbeddings({
    model: EMBED_MODEL,
    apiKey: process.env.GOOGLE_API_KEY,
  });
}

export async function embedQuery(text: string): Promise<number[]> {
  return makeEmbeddings().embedQuery(text);
}

export async function embedDocuments(texts: string[]): Promise<number[][]> {
  return makeEmbeddings().embedDocuments(texts);
}

export interface RetrievedChunk {
  id: string;
  document_id: string;
  content: string;
  page: number | null;
  similarity: number;
  filename: string | null;
}

export interface Citation {
  document_id: string | null;
  filename: string | null;
  page: number | null;
  cited_text: string | null;
}

/**
 * Retrieve the most similar chunks via match_document_chunks. The RPC is
 * SECURITY INVOKER, so calling it on a user-authed client auto-scopes results
 * to the caller's tenant (RLS). Filenames are joined back in for citations.
 */
export async function retrieve(
  supabase: SupabaseClient,
  queryEmbedding: number[],
  matchCount = 8,
  filterDocumentId?: string | null,
): Promise<RetrievedChunk[]> {
  const { data, error } = await supabase.rpc("match_document_chunks", {
    query_embedding: queryEmbedding,
    match_count: matchCount,
    filter_document_id: filterDocumentId ?? null,
  });
  if (error) throw new Error(`Ricerca fallita: ${error.message}`);

  const rows = (data ?? []) as Omit<RetrievedChunk, "filename">[];
  if (rows.length === 0) return [];

  const ids = [...new Set(rows.map((r) => r.document_id))];
  const { data: docs } = await supabase
    .from("documents")
    .select("id, filename")
    .in("id", ids);
  const nameById = new Map(
    (docs ?? []).map((d: { id: string; filename: string }) => [d.id, d.filename]),
  );

  return rows.map((r) => ({ ...r, filename: nameById.get(r.document_id) ?? null }));
}

const SYSTEM_PROMPT = `Sei un assistente per studi legali e commercialisti italiani.
Rispondi in italiano, in modo preciso e professionale.
Basa la risposta ESCLUSIVAMENTE sui documenti forniti come fonti.
Cita le fonti pertinenti inline usando il formato [Fonte N] (es. [Fonte 1]).
Se l'informazione non è presente nelle fonti, dichiaralo esplicitamente e non inventare.`;

/** Generate an answer grounded in the retrieved chunks, with [Fonte N] citations. */
export async function generateAnswer(
  query: string,
  chunks: RetrievedChunk[],
): Promise<{ answer: string; citations: Citation[] }> {
  if (chunks.length === 0) {
    return {
      answer:
        "Non ho trovato informazioni pertinenti nei documenti del tuo studio per rispondere a questa domanda.",
      citations: [],
    };
  }

  const context = chunks
    .map((c, i) => {
      const where = c.page != null ? ` (pag. ${c.page})` : "";
      return `[Fonte ${i + 1}] ${c.filename ?? "documento"}${where}\n---\n${c.content}`;
    })
    .join("\n\n");

  const llm = new ChatGoogleGenerativeAI({
    model: CHAT_MODEL,
    apiKey: process.env.GOOGLE_API_KEY,
    temperature: 0,
    maxRetries: 2,
  });

  const res = await llm.invoke([
    ["system", SYSTEM_PROMPT],
    [
      "human",
      `${context}\n\nDomanda: ${query}\n\nRispondi citando le fonti come [Fonte N] dove rilevante.`,
    ],
  ]);

  const answer = (
    typeof res.content === "string" ? res.content : String(res.content)
  ).trim();

  return { answer, citations: extractCitations(answer, chunks) };
}

function extractCitations(answer: string, chunks: RetrievedChunk[]): Citation[] {
  const seen = new Set<number>();
  const citations: Citation[] = [];
  const re = /\[Fonte\s+(\d+)\]/gi;
  let m: RegExpExecArray | null;
  while ((m = re.exec(answer)) !== null) {
    const idx = parseInt(m[1], 10) - 1;
    if (idx < 0 || idx >= chunks.length || seen.has(idx)) continue;
    seen.add(idx);
    const c = chunks[idx];
    citations.push({
      document_id: c.document_id,
      filename: c.filename,
      page: c.page,
      cited_text: null,
    });
  }
  return citations;
}
