-- =============================================================================
-- Bootstrap: collega ogni utente Auth (senza profilo) a "Studio Legale Alpha".
--
-- Perché serve: l'RLS isola i dati per `tenant_id`, che arriva nel JWT dal
-- custom_access_token_hook leggendo public.profiles. Un utente senza riga in
-- profiles non ha tenant → l'RLS blocca tutto e l'app mostra "nessun documento".
--
-- Idempotente: tocca solo gli utenti che NON hanno ancora un profilo. Il primo
-- utente registrato (per created_at) diventa 'admin', gli altri 'member'.
--
-- Eseguire DOPO aver registrato gli utenti in Supabase Auth e DOPO aver
-- abilitato il custom_access_token_hook (Dashboard → Authentication → Hooks).
-- Gli utenti già loggati devono fare logout/login per ottenere un JWT con il
-- claim tenant_id.
-- =============================================================================

with alpha as (
  select id as tenant_id
  from public.tenants
  where id = '11111111-1111-1111-1111-111111111111'
),
ranked as (
  select
    u.id,
    u.email,
    row_number() over (order by u.created_at) as rn
  from auth.users u
  left join public.profiles p on p.id = u.id
  where p.id is null
)
insert into public.profiles (id, tenant_id, role, full_name)
select
  r.id,
  alpha.tenant_id,
  case when r.rn = 1 then 'admin' else 'member' end,
  r.email
from ranked r
cross join alpha;
