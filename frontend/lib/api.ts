"use client";

import { createClient } from "@/lib/supabase/client";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

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

/** Attach the current user's Supabase access token so the backend can verify tenant. */
async function authHeaders(): Promise<HeadersInit> {
  const supabase = createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();
  if (!session) throw new Error("Not authenticated");
  return { Authorization: `Bearer ${session.access_token}` };
}

export async function sendChat(
  message: string,
  sessionId?: string,
  documentId?: string,
): Promise<ChatResponse> {
  const res = await fetch(`${API_BASE}/api/v1/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(await authHeaders()) },
    body: JSON.stringify({ message, session_id: sessionId, document_id: documentId }),
  });
  if (!res.ok) throw new Error(`Chat failed: ${res.status}`);
  return res.json();
}

export async function uploadDocument(file: File): Promise<void> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/api/v1/documents`, {
    method: "POST",
    headers: await authHeaders(),
    body: form,
  });
  if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
}

export async function listDocuments(): Promise<DocumentOut[]> {
  const res = await fetch(`${API_BASE}/api/v1/documents`, {
    headers: await authHeaders(),
  });
  if (!res.ok) throw new Error(`List failed: ${res.status}`);
  return res.json();
}
