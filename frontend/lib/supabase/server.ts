import { cookies } from "next/headers";
import {
  createServerClient,
  type CookieOptions,
} from "@supabase/ssr";
import type { SupabaseClient, User } from "@supabase/supabase-js";

type CookieToSet = { name: string; value: string; options: CookieOptions };

/** Server Supabase client (Server Components / Route Handlers). */
export async function createClient() {
  const cookieStore = await cookies();
  return createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return cookieStore.getAll();
        },
        setAll(cookiesToSet: CookieToSet[]) {
          try {
            cookiesToSet.forEach(({ name, value, options }) =>
              cookieStore.set(name, value, options),
            );
          } catch {
            // Called from a Server Component — safe to ignore; middleware refreshes.
          }
        },
      },
    },
  );
}

export interface AuthContext {
  supabase: SupabaseClient;
  user: User | null;
  tenantId: string | null;
}

/**
 * Resolve the caller from the session cookies: the Supabase client (which sends
 * the user's JWT, so RLS applies), the user, and the tenant_id claim that the
 * custom access token hook injected. tenantId is null if the hook isn't enabled
 * or the user has no profile → callers should fail closed.
 */
export async function getAuthContext(): Promise<AuthContext> {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return { supabase, user: null, tenantId: null };

  const {
    data: { session },
  } = await supabase.auth.getSession();

  let tenantId: string | null = null;
  if (session?.access_token) {
    try {
      const payload = JSON.parse(
        Buffer.from(session.access_token.split(".")[1], "base64").toString("utf8"),
      );
      tenantId = typeof payload.tenant_id === "string" ? payload.tenant_id : null;
    } catch {
      tenantId = null;
    }
  }

  return { supabase, user, tenantId };
}
