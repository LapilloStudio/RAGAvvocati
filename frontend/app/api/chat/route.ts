import { NextResponse } from "next/server";
import { getAuthContext } from "@/lib/supabase/server";
import { embedQuery, retrieve, generateAnswer } from "@/lib/rag";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 60;

const TENANT_HINT =
  "Studio non configurato: nessun tenant nel profilo. Abilita il custom access " +
  "token hook in Supabase ed esegui 0003_bootstrap_profiles.sql, poi rifai login.";

interface ChatBody {
  message?: string;
  session_id?: string;
  document_id?: string;
}

/** POST: retrieval (RLS-scoped) + Gemini answer with citations; persists the turn. */
export async function POST(req: Request) {
  const { supabase, user, tenantId } = await getAuthContext();
  if (!user) return NextResponse.json({ error: "Non autenticato" }, { status: 401 });
  if (!tenantId) return NextResponse.json({ error: TENANT_HINT }, { status: 403 });

  const { message, session_id, document_id } = (await req.json()) as ChatBody;
  if (!message || !message.trim()) {
    return NextResponse.json({ error: "Messaggio mancante" }, { status: 400 });
  }

  // Reuse or open a chat session (tenant-tagged).
  let sessionId = session_id;
  if (!sessionId) {
    const { data, error } = await supabase
      .from("chat_sessions")
      .insert({
        tenant_id: tenantId,
        user_id: user.id,
        title: message.slice(0, 60),
      })
      .select("id")
      .single();
    if (error) {
      return NextResponse.json(
        { error: `Creazione sessione fallita: ${error.message}` },
        { status: 500 },
      );
    }
    sessionId = data.id as string;
  }

  await supabase.from("chat_messages").insert({
    tenant_id: tenantId,
    session_id: sessionId,
    role: "user",
    content: message,
  });

  try {
    const queryEmbedding = await embedQuery(message);
    const chunks = await retrieve(supabase, queryEmbedding, 8, document_id ?? null);
    const { answer, citations } = await generateAnswer(message, chunks);

    await supabase.from("chat_messages").insert({
      tenant_id: tenantId,
      session_id: sessionId,
      role: "assistant",
      content: answer,
      citations,
    });

    return NextResponse.json({ session_id: sessionId, answer, citations });
  } catch (e) {
    const msg = e instanceof Error ? e.message : "Errore nella generazione della risposta";
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}
