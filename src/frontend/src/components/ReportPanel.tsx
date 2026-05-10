import { useCallback, useEffect, useState } from "react";

type ReportMeta = {
  id: string;
  title: string;
  available: boolean;
};

export function ReportPanel() {
  const [reports, setReports] = useState<ReportMeta[]>([]);
  const [selected, setSelected] = useState("integration");
  const [markdown, setMarkdown] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/reports")
      .then((r) => (r.ok ? r.json() : Promise.reject(`HTTP ${r.status}`)))
      .then((data) => setReports(data.reports ?? []))
      .catch((e) => setError(String(e)));
  }, []);

  const load = useCallback(async (id: string) => {
    setSelected(id);
    setError(null);
    const r = await fetch(`/api/reports/${id}`);
    if (!r.ok) {
      setError(await r.text());
      return;
    }
    const data = await r.json();
    setMarkdown(data.markdown ?? "");
  }, []);

  useEffect(() => {
    load(selected).catch((e) => setError(String(e)));
  }, [load, selected]);

  const highlighted = markdown.split(/(\[\[[^\]]+\]\])/g).map((part, idx) => {
    const match = part.match(/^\[\[([^\]]+)\]\]$/);
    if (!match) return <span key={idx}>{part}</span>;
    return (
      <span key={idx} style={{
        color: "#2563eb",
        fontWeight: 700,
        background: "#eff6ff",
        border: "1px solid #bfdbfe",
        borderRadius: 4,
        padding: "0 3px",
      }}>
        {match[1]}
      </span>
    );
  });

  return (
    <div>
      <h3 style={{ margin: 0, fontSize: 15 }}>报告与文档</h3>
      <select
        value={selected}
        onChange={(e) => load(e.target.value).catch((err) => setError(String(err)))}
        style={{ width: "100%", marginTop: 10, padding: "6px 8px", border: "1px solid #cbd5e1", borderRadius: 6 }}
      >
        {reports.map((r) => (
          <option key={r.id} value={r.id} disabled={!r.available}>
            {r.title}{r.available ? "" : "（缺失）"}
          </option>
        ))}
      </select>
      {error && (
        <div style={{ marginTop: 10, padding: 8, borderRadius: 6, fontSize: 12, color: "#991b1b", background: "#fee2e2" }}>
          {error}
        </div>
      )}
      <div style={{
        marginTop: 10,
        padding: 10,
        border: "1px solid #e5e7eb",
        borderRadius: 6,
        background: "#fff",
        maxHeight: 690,
        overflowY: "auto",
        whiteSpace: "pre-wrap",
        fontSize: 12,
        lineHeight: 1.6,
      }}>
        {highlighted || "加载中..."}
      </div>
    </div>
  );
}
