"use client";

import { createBrowserClient } from "@supabase/ssr";

/** Browser Supabase client (Auth + RLS-protected reads from the UI). */
export function createClient() {
  return createBrowserClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
  );
}
