-- =============================================================================
-- Dev seed (idempotent). Creates two demo firms so you can exercise tenant
-- isolation locally. Users/profiles are created through Supabase Auth (sign-up),
-- then map the user to a tenant by inserting into public.profiles, e.g.:
--
--   insert into public.profiles (id, tenant_id, role, full_name)
--   values ('<auth-user-uuid>', '11111111-1111-1111-1111-111111111111', 'admin', 'Mario Rossi');
--
-- Or run 0003_bootstrap_profiles.sql to attach every user without a profile to
-- Studio Legale Alpha automatically.
-- =============================================================================

insert into public.tenants (id, name) values
  ('11111111-1111-1111-1111-111111111111', 'Studio Legale Alpha'),
  ('22222222-2222-2222-2222-222222222222', 'Studio Legale Beta')
on conflict (id) do nothing;
