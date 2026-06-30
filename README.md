# RAGAvvocati — Multi-Tenant B2B RAG for Professional Firms

A secure, GDPR-first Retrieval-Augmented Generation SaaS for law and tax/accounting
firms. The commercial differentiators are **hard tenant isolation**, **encryption at
rest and in transit**, and **citations** on every answer.

Single Next.js app — the whole RAG pipeline (PDF/DOCX/XLSX parsing, embeddings,
retrieval, generation) runs in TypeScript inside the App Router API routes. No separate
backend service: it deploys to **Vercel** as one app, talking to **Supabase**.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Next.js app on Vercel                                           │
│  ┌───────────────┐   same-origin fetch (session cookie)          │
│  │  UI (login,   │ ──────────────► /api/documents  (ingest/list) │
│  │  upload, chat)│ ──────────────► /api/chat        (RAG answer)  │
│  └───────────────┘         route handlers run under the USER JWT  │
└───────────────────────────────────┬─────────────────────────────┘
        │ supabase-js (user JWT → RLS applies on every call)
        ▼
┌─────────────────────────────────────────────────────────────────┐
│  Supabase: Postgres 15 + pgvector · Auth · Storage  (EU, AES-256)│
│  RLS enforces  tenant_id = current_tenant_id()  on every row,    │
│  plus the match_document_chunks() vector-search RPC.             │
└─────────────────────────────────────────────────────────────────┘
        │ embeddings + generation
        ▼
   Google Gemini — text-embedding-004 (768d) + gemini-2.5-flash
```

| Layer | Technology |
|---|---|
| App | Next.js (App Router) · React · TypeScript · Tailwind |
| RAG pipeline | LangChain JS (WebPDFLoader, text splitters) · mammoth (DOCX) · xlsx (XLSX) |
| Data / Vector / Auth / Storage | Supabase (Postgres 15 + pgvector, Auth, Storage) |
| Embeddings + LLM | Google Gemini (`text-embedding-004`, `gemini-2.5-flash`) |

## Tenant isolation (the core invariant)

Enforced at the **database engine** so a bug in app code can't leak data across firms:

1. **JWT claim** — a Supabase access-token hook stamps `tenant_id` into every user's JWT.
2. **RLS** — every tenant table has `USING (tenant_id = public.current_tenant_id())`; the
   vector-search RPC is `SECURITY INVOKER`, so retrieval is RLS-scoped automatically.
3. **Per-request user client** — every route handler talks to Postgres *under the caller's
   JWT* (session cookie), so RLS applies to reads and writes alike, and each write is
   tagged with the `tenant_id` from the JWT — never client input.

See `supabase/migrations/0001_init.sql` and `frontend/lib/supabase/server.ts`.

## Repository layout

```
supabase/          # schema, RLS, RPC, storage policies, auth hook (source of truth)
frontend/          # the Next.js app (UI + /api RAG pipeline) — deploy root on Vercel
.github/workflows/ # CI (typecheck + lint + build)
```

## Quick start (local)

### 1. Supabase

Create a project in an **EU region** (GDPR). Then, in the SQL Editor, run in order:

1. `supabase/migrations/0001_init.sql` — schema, RLS, RPC, storage, auth hook.
2. `supabase/migrations/0002_seed.sql` — two demo firms (Alpha, Beta).

Enable the auth hook: **Authentication → Hooks → Customize Access Token** → select
`custom_access_token_hook`. Create your user under **Authentication → Users**, then run:

3. `supabase/migrations/0003_bootstrap_profiles.sql` — attaches users without a profile
   to *Studio Legale Alpha* (first user becomes `admin`).

Copy from **Project Settings → API**: Project URL and the `anon` key.

### 2. App

```bash
cd frontend
cp .env.local.example .env.local   # fill in the values below
npm install
npm run dev                         # http://localhost:3000
```

`.env.local`:

```
NEXT_PUBLIC_SUPABASE_URL=https://YOUR-PROJECT.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=ey...
GOOGLE_API_KEY=AIza...              # https://aistudio.google.com/app/apikey
```

Log in, upload a PDF, ask a question → you get a Gemini answer with source citations
(filename + page). A second user on a different tenant never sees the first firm's docs.

## Deploy (Vercel)

One Vercel project, **Root Directory = `frontend`**. Set the three env vars above in
Project Settings → Environment Variables. Push → Vercel builds and serves the whole app.
On **Vercel Pro** the function timeout (60s, up to 300s) covers synchronous ingestion of
large PDFs.

## Security & compliance notes

- **At rest / in transit:** Supabase encrypts at rest (AES-256) and serves over TLS.
  Original files live in a **private** Storage bucket with per-tenant policies.
- **No-Training:** Gemini API content is not used to train models when accessed via a
  paid Google AI Studio / Vertex key. Use an EU-resident project for data residency.
- **Citations:** every answer references the source filename and page for verification.
- **Secrets** live only in `.env.local` (git-ignored) and the Vercel dashboard.

## License

Proprietary — © Lapillo Studio.
