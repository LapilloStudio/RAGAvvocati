# RAGAvvocati — Multi-Tenant B2B RAG for Professional Firms

A secure, GDPR-first Retrieval-Augmented Generation SaaS for law and tax/accounting
firms. The commercial differentiators are **hard tenant isolation**, **encryption at
rest and in transit**, a **No-Training / zero-retention** AI layer, and **strict
citations** on every answer.

> Status: initial scaffold. The architecture, multi-tenant schema, and the core
> ingestion/query pipelines are in place with tenant isolation built in from line one.
> The pipelines are deliberately stubbed (clearly marked `TODO`) — not production-complete.

## Architecture

Decoupled, built around Supabase as the managed data/auth/storage platform.

```
┌──────────────┐     access token (JWT w/ tenant_id)    ┌──────────────────┐
│  Next.js UI  │ ─────────────────────────────────────► │  FastAPI backend │
│ (Supabase    │                                         │  (RAG pipeline)  │
│  Auth)       │ ◄───────── streamed answer + citations ─┤                  │
└──────┬───────┘                                         └────────┬─────────┘
       │ supabase-js (RLS-protected reads)                        │ supabase-py
       ▼                                                          ▼  (under user JWT → RLS)
┌─────────────────────────────────────────────────────────────────────────┐
│  Supabase: Postgres 15 + pgvector · Auth · Storage   (EU region, AES-256) │
│  Row-Level Security enforces  tenant_id = current_tenant_id()  on every    │
│  row, plus the match_document_chunks() vector-search RPC.                  │
└─────────────────────────────────────────────────────────────────────────┘
                        │ generation (no-training / ZDR)
                        ▼
                 Anthropic Claude (claude-opus-4-8) + native Citations
```

| Layer | Technology |
|---|---|
| Backend | Python 3.12 · FastAPI · uvicorn |
| Frontend | Next.js (App Router) · React · TypeScript · Tailwind |
| Data / Vector / Auth / Storage | Supabase (Postgres 15 + pgvector, Auth, Storage) |
| LLM (generation) | Anthropic Claude `claude-opus-4-8` + Citations |
| Embeddings | Pluggable `EmbeddingProvider` (default: managed multilingual) |

## Tenant isolation (the core invariant)

Enforced at three layers so a single mistake can't leak data across firms:

1. **JWT claim** — a Supabase access-token hook stamps `tenant_id` into every user's JWT.
2. **RLS at the database engine** — every tenant table has a policy
   `USING (tenant_id = public.current_tenant_id())`; the vector-search RPC is
   `SECURITY INVOKER` so retrieval is RLS-scoped automatically.
3. **Application layer** — a `TenantContext` is threaded through every service, the
   backend queries Postgres *under the caller's JWT* (so RLS applies), and every write
   is tagged with the context `tenant_id` — never client input.

See `supabase/migrations/0001_init.sql` and `backend/app/core/security.py`.

## Repository layout

```
supabase/          # schema, RLS, RPC, storage policies, auth hook (source of truth)
backend/           # FastAPI RAG pipeline (ingestion + query)
frontend/          # Next.js UI (auth, upload, chat with citations)
.github/workflows/ # CI
```

## Quick start

### 1. Data platform (Supabase, local)

```bash
# install the Supabase CLI: https://supabase.com/docs/guides/cli
supabase start          # boots Postgres+pgvector+Auth+Storage, applies migrations
```
Note the printed `API URL`, `anon key`, `service_role key`, and `JWT secret`.
For production, create a project in an **EU region** for GDPR data residency.

### 2. Backend

```bash
cd backend
cp .env.example .env     # fill in Supabase + Anthropic + embeddings keys
pip install -e ".[dev]"
uvicorn app.main:app --reload      # http://localhost:8000  (docs at /docs)
pytest                              # runs the tenant-isolation gate
```

### 3. Frontend

```bash
cd frontend
cp .env.local.example .env.local   # Supabase URL + anon key + backend URL
npm install
npm run dev                         # http://localhost:3000
```

## Security & compliance notes

- **At rest / in transit:** Supabase encrypts data at rest (AES-256) and serves over
  TLS. Original files live in a **private** Storage bucket with per-tenant policies.
- **No-Training:** the Anthropic API does not train on API traffic by default. Enable
  **Zero Data Retention** at the org level; set `ANTHROPIC_INFERENCE_GEO=eu` to pin
  inference to the EU.
- **Citations:** answers use Claude's native Citations — every claim carries the source
  filename and page, returned to the UI for professional verification.
- **Secrets** live only in `.env` files (git-ignored) / your secret manager.

## License

Proprietary — © Lapillo Studio.
