import type { Citation } from "@/lib/api";

export default function CitationList({ citations }: { citations: Citation[] }) {
  if (citations.length === 0) return null;
  return (
    <div className="mt-3 border-t border-slate-200 pt-2">
      <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">
        Fonti
      </p>
      <ul className="space-y-1">
        {citations.map((c, i) => (
          <li key={i} className="text-xs text-slate-600">
            <span className="font-medium">{c.filename ?? "documento"}</span>
            {c.page != null && <span> · p. {c.page}</span>}
            {c.cited_text && (
              <span className="block italic text-slate-400">“{c.cited_text}”</span>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
