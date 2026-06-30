import { NextResponse } from "next/server";
import { getAuthContext } from "@/lib/supabase/server";
import { extractChunks } from "@/lib/parsing";
import { embedDocuments } from "@/lib/rag";

// Node runtime: pdf-parse/mammoth/xlsx need Buffer + fs. force-dynamic: per-user.
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 60; // Vercel Pro: up to 300 if large PDFs need it.

const TENANT_HINT =
  "Studio non configurato: nessun tenant nel profilo. Abilita il custom access " +
  "token hook in Supabase ed esegui 0003_bootstrap_profiles.sql, poi rifai login.";

/** GET: list the caller's documents (RLS-scoped). */
export async function GET() {
  const { supabase, user } = await getAuthContext();
  if (!user) return NextResponse.json({ error: "Non autenticato" }, { status: 401 });

  const { data, error } = await supabase
    .from("documents")
    .select("id, filename, mime_type, status, size_bytes, created_at")
    .order("created_at", { ascending: false });

  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json(data ?? []);
}

/** POST: ingest one uploaded file → Storage + parsed/embedded chunks. */
export async function POST(req: Request) {
  const { supabase, user, tenantId } = await getAuthContext();
  if (!user) return NextResponse.json({ error: "Non autenticato" }, { status: 401 });
  if (!tenantId) return NextResponse.json({ error: TENANT_HINT }, { status: 403 });

  const form = await req.formData();
  const file = form.get("file");
  if (!(file instanceof File)) {
    return NextResponse.json({ error: "Nessun file fornito" }, { status: 400 });
  }

  const documentId = crypto.randomUUID();
  const safeName = file.name.replace(/[^a-zA-Z0-9.\-_]/g, "_");
  const storagePath = `${tenantId}/${documentId}/${safeName}`;
  const mimeType = file.type || "application/octet-stream";

  // 1. Original file → private Storage bucket (RLS by leading tenant path).
  const buffer = Buffer.from(await file.arrayBuffer());
  const { error: upErr } = await supabase.storage
    .from("documents")
    .upload(storagePath, buffer, { contentType: mimeType, upsert: false });
  if (upErr) {
    return NextResponse.json(
      { error: `Salvataggio file fallito: ${upErr.message}` },
      { status: 500 },
    );
  }

  // 2. documents row (processing). tenant_id from the JWT claim → RLS validates.
  const { error: docErr } = await supabase.from("documents").insert({
    id: documentId,
    tenant_id: tenantId,
    filename: file.name,
    storage_path: storagePath,
    mime_type: mimeType,
    size_bytes: file.size,
    status: "processing",
    uploaded_by: user.id,
  });
  if (docErr) {
    return NextResponse.json(
      { error: `Registrazione documento fallita: ${docErr.message}` },
      { status: 500 },
    );
  }

  // 3. Parse → chunk → embed → insert chunks. On any failure mark as 'failed'.
  try {
    const chunks = await extractChunks(file);
    if (chunks.length === 0) {
      throw new Error("Nessun testo estratto dal documento.");
    }

    const vectors = await embedDocuments(chunks.map((c) => c.content));
    const rows = chunks.map((c, i) => ({
      tenant_id: tenantId,
      document_id: documentId,
      chunk_index: i,
      content: c.content,
      page: c.page,
      embedding: vectors[i],
    }));

    for (let i = 0; i < rows.length; i += 100) {
      const { error } = await supabase
        .from("document_chunks")
        .insert(rows.slice(i, i + 100));
      if (error) throw new Error(error.message);
    }

    await supabase.from("documents").update({ status: "ready" }).eq("id", documentId);
    return NextResponse.json({ id: documentId, status: "ready", chunks: rows.length });
  } catch (e) {
    const message = e instanceof Error ? e.message : "Errore di elaborazione";
    await supabase
      .from("documents")
      .update({ status: "failed", error: message })
      .eq("id", documentId);
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
