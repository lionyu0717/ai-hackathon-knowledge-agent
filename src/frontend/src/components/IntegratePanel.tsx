import { useCallback, useEffect, useMemo, useState } from "react";

type IntegrationStats = {
  original_textbooks: number;
  original_chars: number;
  merged_chars: number;
  compression_ratio: number;
  original_nodes: number;
  merged_nodes: number;
  decisions_merge: number;
  decisions_keep: number;
  decisions_remove: number;
};

type IntegrationStatus = {
  run_id?: string;
  status: "idle" | "queued" | "running" | "done" | "failed";
  stats?: IntegrationStats;
  error_message?: string | null;
};

type IntegrationDecision = {
  decision_id: string;
  action: "merge" | "keep" | "remove";
  affected_nodes: string[];
  result_node: string | null;
  result_chunks: string[];
  reason: string;
  confidence: number;
  source_excerpt?: string;
  source_refs?: string[];
};

const ACTION_LABEL: Record<IntegrationDecision["action"], string> = {
  merge: "合并",
  keep: "保留",
  remove: "移除",
};

const ACTION_COLOR: Record<IntegrationDecision["action"], string> = {
  merge: "#2563eb",
  keep: "#16a34a",
  remove: "#dc2626",
};

export function IntegratePanel() {
  const [status, setStatus] = useState<IntegrationStatus>({ status: "idle" });
  const [decisions, setDecisions] = useState<IntegrationDecision[]>([]);
  const [summary, setSummary] = useState("");
  const [memo, setMemo] = useState("");
  const [error, setError] = useState<string | null>(null);
  const running = status.status === "queued" || status.status === "running";

  const refresh = useCallback(async () => {
    const r = await fetch("/api/integrate/status");
    const data = (await r.json()) as IntegrationStatus;
    setStatus(data);
    if (data.status === "done") {
      const [d, s] = await Promise.all([
        fetch("/api/integrate/decisions").then((x) => x.json()),
        fetch("/api/integrate/summary").then((x) => x.json()),
      ]);
      setDecisions(d.decisions ?? []);
      setSummary(s.summary_markdown ?? "");
      setMemo((cur) => cur || s.summary_markdown || "");
    }
  }, []);

  useEffect(() => {
    refresh().catch(() => {});
  }, [refresh]);

  useEffect(() => {
    if (!running) return;
    const t = setInterval(() => refresh().catch(() => {}), 2500);
    return () => clearInterval(t);
  }, [running, refresh]);

  const start = useCallback(async () => {
    setError(null);
    setDecisions([]);
    setSummary("");
    setMemo("");
    const r = await fetch("/api/integrate/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ textbook_ids: [] }),
    });
    if (!r.ok) {
      setError(await r.text());
      return;
    }
    const data = await r.json();
    setStatus({ status: "queued", run_id: data.run_id });
    setTimeout(() => refresh().catch(() => {}), 500);
  }, [refresh]);

  const linkedPreview = useMemo(() => {
    const text = memo || summary;
    return text.split(/(\[\[[^\]]+\]\])/g).map((part, idx) => {
      const m = part.match(/^\[\[([^\]]+)\]\]$/);
      if (!m) return <span key={idx}>{part}</span>;
      return (
        <span key={idx} title="Obsidian 双链知识点" style={{
          color: "#2563eb", fontWeight: 700, background: "#eff6ff",
          border: "1px solid #bfdbfe", borderRadius: 4, padding: "0 3px",
        }}>
          {m[1]}
        </span>
      );
    });
  }, [memo, summary]);

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <h3 style={{ margin: 0, fontSize: 15 }}>跨教材整合</h3>
        <button onClick={start} disabled={running} style={buttonStyle(running)}>
          {running ? "整合中..." : "运行 Phase 3"}
        </button>
      </div>

      {error && <Notice tone="error">{error}</Notice>}
      {status.error_message && <Notice tone="error">{status.error_message}</Notice>}

      {status.stats && status.stats.original_textbooks > 0 ? (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginTop: 12 }}>
          <Metric label="教材" value={`${status.stats.original_textbooks} 本`} />
          <Metric label="压缩比" value={`${(status.stats.compression_ratio * 100).toFixed(1)}%`} />
          <Metric label="原始字数" value={status.stats.original_chars.toLocaleString()} />
          <Metric label="精华字数" value={status.stats.merged_chars.toLocaleString()} />
          <Metric label="原始节点" value={status.stats.original_nodes.toLocaleString()} />
          <Metric label="整合节点" value={status.stats.merged_nodes.toLocaleString()} />
        </div>
      ) : (
        <Notice tone="info">需要至少 2 本教材完成图谱抽取后，才能执行跨教材整合。</Notice>
      )}

      {status.stats && (
        <div style={{ marginTop: 10, fontSize: 12, color: "#64748b" }}>
          merge {status.stats.decisions_merge} · keep {status.stats.decisions_keep} · remove {status.stats.decisions_remove}
        </div>
      )}

      <div style={{ marginTop: 14 }}>
        <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 6 }}>知识点进化总结</div>
        <textarea
          value={memo}
          onChange={(e) => setMemo(e.target.value)}
          placeholder="运行整合后会生成带 [[双链]] 的总结，可临时编辑用于答辩。"
          style={{
            width: "100%", minHeight: 120, resize: "vertical", boxSizing: "border-box",
            border: "1px solid #cbd5e1", borderRadius: 6, padding: 8,
            fontSize: 12, lineHeight: 1.55, fontFamily: "inherit",
          }}
        />
        {(memo || summary) && (
          <div style={{
            marginTop: 8, padding: 8, border: "1px solid #e5e7eb",
            borderRadius: 6, background: "#fff", whiteSpace: "pre-wrap",
            fontSize: 12, lineHeight: 1.55, maxHeight: 130, overflowY: "auto",
          }}>
            {linkedPreview}
          </div>
        )}
      </div>

      <div style={{ marginTop: 14 }}>
        <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 6 }}>
          整合决策列表（{decisions.length}）
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 8, maxHeight: 420, overflowY: "auto" }}>
          {decisions.slice(0, 80).map((d) => (
            <DecisionCard key={d.decision_id} decision={d} />
          ))}
          {decisions.length > 80 && (
            <div style={{ color: "#94a3b8", fontSize: 12 }}>仅展示前 80 条，完整列表可通过 API 获取。</div>
          )}
        </div>
      </div>
    </div>
  );
}

function DecisionCard({ decision }: { decision: IntegrationDecision }) {
  return (
    <div style={{ border: "1px solid #e5e7eb", borderRadius: 6, padding: 9, background: "#fff" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{
          fontSize: 11, color: ACTION_COLOR[decision.action],
          background: ACTION_COLOR[decision.action] + "18",
          borderRadius: 999, padding: "2px 7px", fontWeight: 700,
        }}>
          {ACTION_LABEL[decision.action]}
        </span>
        <span style={{ fontSize: 11, color: "#94a3b8" }}>{decision.decision_id}</span>
        <span style={{ marginLeft: "auto", fontSize: 11, color: "#64748b" }}>
          {(decision.confidence * 100).toFixed(0)}%
        </span>
      </div>
      <div style={{ marginTop: 7, fontSize: 12, lineHeight: 1.45 }}>{decision.reason}</div>
      {decision.source_refs && decision.source_refs.length > 0 && (
        <div style={{ marginTop: 6, fontSize: 11, color: "#64748b", wordBreak: "break-all" }}>
          {decision.source_refs.slice(0, 3).join(" · ")}
        </div>
      )}
      {decision.source_excerpt && (
        <details style={{ marginTop: 6 }}>
          <summary style={{ cursor: "pointer", fontSize: 11, color: "#2563eb" }}>原文摘录</summary>
          <div style={{ marginTop: 5, fontSize: 11, lineHeight: 1.5, color: "#475569" }}>
            {decision.source_excerpt}
          </div>
        </details>
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

function Notice({ children, tone }: { children: React.ReactNode; tone: "info" | "error" }) {
  return (
    <div style={{
      marginTop: 10, padding: 8, borderRadius: 6, fontSize: 12,
      color: tone === "error" ? "#991b1b" : "#475569",
      background: tone === "error" ? "#fee2e2" : "#f8fafc",
      border: `1px solid ${tone === "error" ? "#fecaca" : "#e5e7eb"}`,
    }}>
      {children}
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
