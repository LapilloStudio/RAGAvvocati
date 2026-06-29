"use client";

import { useState } from "react";
import { uploadDocument } from "@/lib/api";

const ACCEPT =
  ".pdf,.docx,.xlsx,application/pdf," +
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document," +
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";

export default function DocumentUpload() {
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  async function onChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true);
    setMsg(null);
    try {
      await uploadDocument(file);
      setMsg(`"${file.name}" caricato. Elaborazione in corso…`);
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "Errore di caricamento");
    } finally {
      setBusy(false);
      e.target.value = "";
    }
  }

  return (
    <div className="rounded-xl border border-dashed border-slate-300 bg-white p-4">
      <label className="block cursor-pointer text-sm font-medium text-slate-700">
        {busy ? "Caricamento…" : "Carica documento (PDF, DOCX, XLSX)"}
        <input
          type="file"
          accept={ACCEPT}
          onChange={onChange}
          disabled={busy}
          className="hidden"
        />
      </label>
      {msg && <p className="mt-2 text-xs text-slate-500">{msg}</p>}
    </div>
  );
}
