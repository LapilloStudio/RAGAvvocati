"use client";

// Calls the app's own Next.js API routes (same-origin). The Supabase session
// travels automatically via cookies, so no Authorization header is needed and
// there is no external backend URL.

export interface Citation {
  document_id: string | null;
  filename: string | null;
  page: number | null;
  cited_text: string | null;
}

export interface ChatResponse {
  session_id: string;
  answer: string;
  citations: Citation[];
}

export interface DocumentOut {
  id: string;
  filename: string;
  mime_type: string;
  status: string;
  size_bytes: number | null;
  created_at: string | null;
}

async function errorMessage(res: Response, fallback: string): Promise<string> {
  try {
    const body = await res.json();
    if (body && typeof body.error === "string") return body.error;
  } catch {
    // no JSON body
  }
  return `${fallback}: ${res.status}`;
}

export async function sendChat(
  message: string,
  sessionId?: string,
  documentId?: string,
): Promise<ChatResponse> {
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, session_id: sessionId, document_id: documentId }),
  });
  if (!res.ok) throw new Error(await errorMessage(res, "Chat fallita"));
  return res.json();
}

export async function uploadDocument(file: File): Promise<void> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch("/api/documents", { method: "POST", body: form });
  if (!res.ok) throw new Error(await errorMessage(res, "Caricamento fallito"));
}

export async function listDocuments(): Promise<DocumentOut[]> {
  const res = await fetch("/api/documents");
  if (!res.ok) throw new Error(await errorMessage(res, "Lettura documenti fallita"));
  return res.json();
}
