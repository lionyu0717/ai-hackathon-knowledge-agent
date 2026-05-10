import { useCallback, useEffect, useState } from "react";

type RagStatus = {
  status: string;
  chunk_count: number;
  embedded_count: number;
  textbook_count: number;
  updated_at?: string | null;
  error?: string;
};

type RagAnswer = {
  answer: string;
  citations: { textbook: string; chapter: string; page: number; relevance_score: number }[];
  source_chunks: string[];
  latency_ms: number;
};

export function RagPanel() {
  const [status, setStatus] = useState<RagStatus | null>(null);
  const [question, setQuestion] = useState("什么是内环境？");
  const [answer, setAnswer] = useState<RagAnswer | null>(null);
  const [loading, setLoading] = useState(false);
  const [indexing, setIndexing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const data = await fetch("/api/rag/status").then((r) => r.json());
    setStatus(data);
    setIndexing(data.status === "queued" || data.status === "running");
  }, []);

  useEffect(() => {
    refresh().catch(() => {});
  }, [refresh]);

  useEffect(() => {
    if (!indexing) return;
    const t = setInterval(() => refresh().catch(() => {}), 2500);
    return () => clearInterval(t);
  }, [indexing, refresh]);

  const buildIndex = useCallback(async () => {
    setError(null);
    setIndexing(true);
    const r = await fetch("/api/rag/index", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ textbook_ids: [] }),
    });
    if (!r.ok) {
      setError(await r.text());
      setIndexing(false);
    }
  }, []);

  const ask = useCallback(async () => {
    if (!question.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const r = await fetch("/api/rag/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, top_k: 5 }),
      });
      if (!r.ok) throw new Error(await r.text());
      setAnswer(await r.json());
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, [question]);

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <h3 style={{ margin: 0, fontSize: 15 }}>RAG 问答</h3>
        <button onClick={buildIndex} disabled={indexing} style={buttonStyle(indexing)}>
          {indexing ? "索引中..." : "建立索引"}
        </button>
      </div>

      <div style={{ marginTop: 10, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
        <Metric label="状态" value={status?.status || "unknown"} />
        <Metric label="Chunks" value={(status?.chunk_count || 0).toLocaleString()} />
        <Metric label="向量" value={(status?.embedded_count || 0).toLocaleString()} />
        <Metric label="教材" value={`${status?.textbook_count || 0} 本`} />
      </div>

      {error && <div style={errorStyle}>{error}</div>}
      {status?.error && <div style={errorStyle}>{status.error}</div>}

      <textarea
        value={question}
        onChange={(e) => setQuestion(e.target.value)}
        placeholder="输入教材问题"
        style={{
          width: "100%", boxSizing: "border-box", marginTop: 12, minHeight: 68,
          border: "1px solid #cbd5e1", borderRadius: 6, padding: 8,
          fontSize: 12, fontFamily: "inherit", resize: "vertical",
        }}
      />
      <button onClick={ask} disabled={loading} style={{ ...buttonStyle(loading), width: "100%", marginTop: 8 }}>
        {loading ? "检索生成中..." : "提问"}
      </button>

      {answer && (
        <div style={{ marginTop: 12 }}>
          <div style={{ fontSize: 12, color: "#64748b", marginBottom: 6 }}>
            latency {answer.latency_ms}ms · sources {answer.source_chunks.length}
          </div>
          <div style={{
            padding: 10, border: "1px solid #e5e7eb", borderRadius: 6,
            background: "#fff", fontSize: 12, lineHeight: 1.6, whiteSpace: "pre-wrap",
          }}>
            {answer.answer}
          </div>
          <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 6 }}>
            {answer.citations.map((c, idx) => (
              <div key={`${c.textbook}-${c.chapter}-${idx}`} style={{
                padding: 8, border: "1px solid #e5e7eb", borderRadius: 6,
                background: "#f8fafc", fontSize: 11, color: "#475569",
              }}>
                《{c.textbook}》 · {c.chapter} · 第 {c.page} 页 · score {c.relevance_score}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ border: "1px solid #e5e7eb", borderRadius: 6, background: "#f8fafc", padding: 8 }}>
      <div style={{ color: "#94a3b8", fontSize: 11 }}>{label}</div>
      <div style={{ fontWeight: 700, fontSize: 14, marginTop: 2 }}>{value}</div>
    </div>
  );
}

function buttonStyle(disabled: boolean): React.CSSProperties {
  return {
    marginLeft: "auto", padding: "5px 10px", border: 0, borderRadius: 5,
    background: disabled ? "#cbd5e1" : "#2563eb", color: "#fff",
    cursor: disabled ? "not-allowed" : "pointer", fontSize: 12,
  };
}

const errorStyle: React.CSSProperties = {
  marginTop: 10, padding: 8, borderRadius: 6, fontSize: 12,
  color: "#991b1b", background: "#fee2e2", border: "1px solid #fecaca",
};
