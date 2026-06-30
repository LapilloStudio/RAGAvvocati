-- =============================================================================
-- RAGAvvocati — aggiorna la dimensione del vettore da 1536 a 768
-- Da eseguire SE il database è già stato inizializzato con 0001_init.sql
-- e la colonna embedding era vector(1536) (OpenAI).
-- Passando a Gemini text-embedding-004 la dimensione corretta è 768.
-- =============================================================================

-- 1. Rimuovi l'indice HNSW (ALTER TYPE fallisce se esiste un indice sulla colonna)
DROP INDEX IF EXISTS public.document_chunks_embedding_idx;

-- 2. Cambia la dimensione del vettore: 1536 → 768
ALTER TABLE public.document_chunks
  ALTER COLUMN embedding TYPE vector(768);

-- 3. DROP esplicito della funzione RPC: CREATE OR REPLACE non funziona quando
--    la firma cambia (tipo del parametro). Il DROP è per nome, senza firma,
--    così funziona sia che la vecchia fosse vector(1536) sia vector(768).
DROP FUNCTION IF EXISTS public.match_document_chunks(vector, int, uuid);

CREATE OR REPLACE FUNCTION public.match_document_chunks(
  query_embedding    vector(768),
  match_count        int  DEFAULT 8,
  filter_document_id uuid DEFAULT NULL
)
RETURNS TABLE (
  id          uuid,
  document_id uuid,
  content     text,
  page        int,
  similarity  float
)
LANGUAGE sql STABLE
AS $$
  SELECT
    dc.id,
    dc.document_id,
    dc.content,
    dc.page,
    1 - (dc.embedding <=> query_embedding) AS similarity
  FROM public.document_chunks dc
  WHERE dc.tenant_id = public.current_tenant_id()
    AND (filter_document_id IS NULL OR dc.document_id = filter_document_id)
    AND dc.embedding IS NOT NULL
  ORDER BY dc.embedding <=> query_embedding
  LIMIT GREATEST(match_count, 1);
$$;

-- 4. Ricrea l'indice HNSW per la nuova dimensione
CREATE INDEX document_chunks_embedding_idx
  ON public.document_chunks USING hnsw (embedding vector_cosine_ops);
