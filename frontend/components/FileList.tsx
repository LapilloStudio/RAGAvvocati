"use client";

import { useEffect, useState } from "react";
import { listDocuments, type DocumentOut } from "@/lib/api";

const STATUS_LABEL: Record<string, string> = {
  processing: "in elaborazione",
  ready: "pronto",
  failed: "errore",
};

export default function FileList() {
  const [docs, setDocs] = useState<DocumentOut[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const data = await listDocuments();
        if (active) setDocs(data);
      } catch (err) {
        if (active) setError(err instanceof Error ? err.message : "Errore");
      }
    }
    load();
    // Poll so 'processing' → 'ready' transitions show up.
    const id = setInterval(load, 5000);
    return () => {
      active = false;
      clearInterval(id);
    };
  }, []);

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <h2 className="mb-2 text-sm font-semibold">Documenti</h2>
      {error && <p className="text-xs text-red-600">{error}</p>}
      {docs.length === 0 ? (
        <p className="text-xs text-slate-400">Nessun documento ancora.</p>
      ) : (
        <ul className="space-y-1">
          {docs.map((d) => (
            <li key={d.id} className="flex items-center justify-between text-xs">
              <span className="truncate text-slate-700">{d.filename}</span>
              <span
                className={
                  d.status === "ready"
                    ? "text-green-600"
                    : d.status === "failed"
                      ? "text-red-600"
                      : "text-amber-600"
                }
              >
                {STATUS_LABEL[d.status] ?? d.status}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
