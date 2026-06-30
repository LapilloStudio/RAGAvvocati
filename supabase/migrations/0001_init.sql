-- =============================================================================
-- RAGAvvocati — initial schema
-- Multi-tenant B2B RAG. Tenant isolation is enforced at the DATABASE ENGINE via
-- Row-Level Security (RLS). Every tenant table carries a tenant_id and an RLS
-- policy comparing it to public.current_tenant_id(), which reads the tenant_id
-- claim from the caller's Supabase JWT. Cross-tenant access is impossible even
-- if application code has a bug.
-- =============================================================================

-- ---- Extensions -------------------------------------------------------------
create extension if not exists "pgcrypto";   -- gen_random_uuid()
create extension if not exists "vector";      -- pgvector

-- =============================================================================
-- Tenant resolver: the single source of truth for "who am I".
-- Reads the custom `tenant_id` claim injected into the JWT by the auth hook
-- (see custom_access_token_hook below). Returns NULL for unauthenticated /
-- claimless callers, which makes every RLS policy fail closed.
-- =============================================================================
create or replace function public.current_tenant_id()
returns uuid
language sql
stable
as $$
  select nullif(
    coalesce(
      current_setting('request.jwt.claims', true)::jsonb ->> 'tenant_id',
      ''
    ),
    ''
  )::uuid;
$$;

-- =============================================================================
-- Core tables
-- =============================================================================

-- Firms (tenants)
create table public.tenants (
  id          uuid primary key default gen_random_uuid(),
  name        text not null,
  created_at  timestamptz not null default now()
);

-- User → firm mapping. id mirrors auth.users.id so a profile row IS the user.
create table public.profiles (
  id          uuid primary key references auth.users(id) on delete cascade,
  tenant_id   uuid not null references public.tenants(id) on delete restrict,
  role        text not null default 'member' check (role in ('member', 'admin')),
  full_name   text,
  created_at  timestamptz not null default now()
);
create index profiles_tenant_id_idx on public.profiles (tenant_id);

-- Uploaded documents (original files live in Supabase Storage)
create table public.documents (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null references public.tenants(id) on delete cascade,
  filename      text not null,
  storage_path  text not null,            -- '<tenant_id>/<document_id>/<filename>'
  mime_type     text not null,
  size_bytes    bigint,
  status        text not null default 'processing'
                  check (status in ('processing', 'ready', 'failed')),
  error         text,
  uploaded_by   uuid references auth.users(id) on delete set null,
  created_at    timestamptz not null default now()
);
create index documents_tenant_id_idx on public.documents (tenant_id);

-- Parsed + embedded chunks (the retrievable vector store)
create table public.document_chunks (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null references public.tenants(id) on delete cascade,
  document_id   uuid not null references public.documents(id) on delete cascade,
  chunk_index   int not null,
  content       text not null,
  page          int,                      -- source page for citations (nullable)
  metadata      jsonb not null default '{}'::jsonb,
  embedding     vector(768),              -- Gemini text-embedding-004 → 768 dims
  created_at    timestamptz not null default now()
);
create index document_chunks_tenant_id_idx on public.document_chunks (tenant_id);
create index document_chunks_document_id_idx on public.document_chunks (document_id);
-- ANN index for cosine similarity search
create index document_chunks_embedding_idx
  on public.document_chunks using hnsw (embedding vector_cosine_ops);

-- Chat history
create table public.chat_sessions (
  id          uuid primary key default gen_random_uuid(),
  tenant_id   uuid not null references public.tenants(id) on delete cascade,
  user_id     uuid references auth.users(id) on delete set null,
  title       text,
  created_at  timestamptz not null default now()
);
create index chat_sessions_tenant_id_idx on public.chat_sessions (tenant_id);

create table public.chat_messages (
  id          uuid primary key default gen_random_uuid(),
  tenant_id   uuid not null references public.tenants(id) on delete cascade,
  session_id  uuid not null references public.chat_sessions(id) on delete cascade,
  role        text not null check (role in ('user', 'assistant')),
  content     text not null,
  citations   jsonb not null default '[]'::jsonb,   -- [{filename, page, cited_text}]
  created_at  timestamptz not null default now()
);
create index chat_messages_tenant_id_idx on public.chat_messages (tenant_id);
create index chat_messages_session_id_idx on public.chat_messages (session_id);

-- =============================================================================
-- Row-Level Security — the hard programmatic boundary
-- Pattern (identical for every tenant table):
--   * enable RLS
--   * SELECT/INSERT/UPDATE/DELETE allowed only when
--     tenant_id = public.current_tenant_id()
-- profiles is special: a user may always read their OWN profile (needed by the
-- auth hook / bootstrap), plus same-tenant visibility.
-- =============================================================================

alter table public.tenants          enable row level security;
alter table public.profiles         enable row level security;
alter table public.documents        enable row level security;
alter table public.document_chunks  enable row level security;
alter table public.chat_sessions    enable row level security;
alter table public.chat_messages    enable row level security;

-- tenants: a member can read their own firm row.
create policy tenants_select_own on public.tenants
  for select using (id = public.current_tenant_id());

-- profiles: read own row OR any same-tenant profile.
create policy profiles_select on public.profiles
  for select using (
    id = auth.uid() or tenant_id = public.current_tenant_id()
  );
create policy profiles_update_own on public.profiles
  for update using (id = auth.uid()) with check (id = auth.uid());

-- Generic tenant policies for the data tables.
create policy documents_isolation on public.documents
  for all using (tenant_id = public.current_tenant_id())
          with check (tenant_id = public.current_tenant_id());

create policy document_chunks_isolation on public.document_chunks
  for all using (tenant_id = public.current_tenant_id())
          with check (tenant_id = public.current_tenant_id());

create policy chat_sessions_isolation on public.chat_sessions
  for all using (tenant_id = public.current_tenant_id())
          with check (tenant_id = public.current_tenant_id());

create policy chat_messages_isolation on public.chat_messages
  for all using (tenant_id = public.current_tenant_id())
          with check (tenant_id = public.current_tenant_id());

-- =============================================================================
-- Vector similarity search RPC.
-- SECURITY INVOKER (the default) → runs as the caller, so the RLS policy on
-- document_chunks applies automatically. The explicit tenant_id predicate is
-- defense-in-depth so the function is safe even if called with elevated rights.
-- =============================================================================
create or replace function public.match_document_chunks(
  query_embedding vector(768),
  match_count     int default 8,
  filter_document_id uuid default null
)
returns table (
  id          uuid,
  document_id uuid,
  content     text,
  page        int,
  similarity  float
)
language sql
stable
as $$
  select
    dc.id,
    dc.document_id,
    dc.content,
    dc.page,
    1 - (dc.embedding <=> query_embedding) as similarity
  from public.document_chunks dc
  where dc.tenant_id = public.current_tenant_id()
    and (filter_document_id is null or dc.document_id = filter_document_id)
    and dc.embedding is not null
  order by dc.embedding <=> query_embedding
  limit greatest(match_count, 1);
$$;

-- =============================================================================
-- Storage: private bucket for original files. Objects are keyed by
-- '<tenant_id>/<document_id>/<filename>', and policies restrict access to the
-- tenant that owns the leading path segment.
-- =============================================================================
insert into storage.buckets (id, name, public)
values ('documents', 'documents', false)
on conflict (id) do nothing;

create policy "documents_storage_tenant_read" on storage.objects
  for select using (
    bucket_id = 'documents'
    and (storage.foldername(name))[1] = public.current_tenant_id()::text
  );

create policy "documents_storage_tenant_write" on storage.objects
  for insert with check (
    bucket_id = 'documents'
    and (storage.foldername(name))[1] = public.current_tenant_id()::text
  );

create policy "documents_storage_tenant_delete" on storage.objects
  for delete using (
    bucket_id = 'documents'
    and (storage.foldername(name))[1] = public.current_tenant_id()::text
  );

-- =============================================================================
-- Auth hook: inject tenant_id + role into every issued JWT so RLS can read them
-- without a per-request table lookup. Register it in Supabase:
--   Dashboard → Authentication → Hooks → Customize Access Token (or
--   supabase/config.toml: [auth.hook.custom_access_token]).
-- =============================================================================
create or replace function public.custom_access_token_hook(event jsonb)
returns jsonb
language plpgsql
stable
as $$
declare
  claims     jsonb;
  v_tenant   uuid;
  v_role     text;
begin
  select tenant_id, role into v_tenant, v_role
  from public.profiles
  where id = (event ->> 'user_id')::uuid;

  claims := event -> 'claims';

  if v_tenant is not null then
    claims := jsonb_set(claims, '{tenant_id}', to_jsonb(v_tenant::text));
    claims := jsonb_set(claims, '{tenant_role}', to_jsonb(coalesce(v_role, 'member')));
  end if;

  return jsonb_set(event, '{claims}', claims);
end;
$$;

-- Allow the auth admin role to execute the hook.
grant execute on function public.custom_access_token_hook(jsonb) to supabase_auth_admin;
grant all on table public.profiles to supabase_auth_admin;
create policy "auth_admin_read_profiles" on public.profiles
  for select to supabase_auth_admin using (true);
