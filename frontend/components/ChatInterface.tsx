"use client";

import { useState } from "react";
import { sendChat, type Citation } from "@/lib/api";
import CitationList from "./CitationList";

interface Turn {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
}

export default function ChatInterface() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState<string | undefined>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSend(e: React.FormEvent) {
    e.preventDefault();
    const message = input.trim();
    if (!message || busy) return;
    setInput("");
    setError(null);
    setTurns((t) => [...t, { role: "user", content: message }]);
    setBusy(true);
    try {
      const res = await sendChat(message, sessionId);
      setSessionId(res.session_id);
      setTurns((t) => [
        ...t,
        { role: "assistant", content: res.answer, citations: res.citations },
      ]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Errore");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex h-[80vh] flex-col rounded-xl border border-slate-200 bg-white shadow-sm">
      <div className="flex-1 space-y-4 overflow-y-auto p-4">
        {turns.length === 0 && (
          <p className="text-sm text-slate-400">
            Fai una domanda sui documenti del tuo studio. Ogni risposta cita le fonti.
          </p>
        )}
        {turns.map((t, i) => (
          <div
            key={i}
            className={t.role === "user" ? "text-right" : "text-left"}
          >
            <div
              className={`inline-block max-w-[85%] rounded-lg px-3 py-2 text-sm ${
                t.role === "user"
                  ? "bg-slate-900 text-white"
                  : "bg-slate-100 text-slate-900"
              }`}
            >
              <p className="whitespace-pre-wrap">{t.content}</p>
              {t.role === "assistant" && t.citations && (
                <CitationList citations={t.citations} />
              )}
            </div>
          </div>
        ))}
        {busy && <p className="text-sm text-slate-400">Sto pensando…</p>}
        {error && <p className="text-sm text-red-600">{error}</p>}
      </div>
      <form onSubmit={onSend} className="flex gap-2 border-t border-slate-200 p-3">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Scrivi una domanda…"
          className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm"
        />
        <button
          type="submit"
          disabled={busy}
          className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          Invia
        </button>
      </form>
    </div>
  );
}
