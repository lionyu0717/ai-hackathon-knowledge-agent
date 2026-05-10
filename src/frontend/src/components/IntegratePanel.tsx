import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import * as echarts from "echarts";

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
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
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

  const updateDecision = useCallback(async (
    decisionId: string,
    action: IntegrationDecision["action"],
    reason: string,
  ) => {
    setSaveMessage(null);
    const r = await fetch(`/api/integrate/decisions/${decisionId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, reason, confidence: 0.97 }),
    });
    if (!r.ok) {
      throw new Error(await r.text());
    }
    setSaveMessage(`已保存 ${decisionId} → ${ACTION_LABEL[action]}`);
    await refresh();
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
      {saveMessage && <Notice tone="info">{saveMessage}</Notice>}

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

      <DecisionSankey stats={status.stats} decisions={decisions} />

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
            <DecisionCard key={d.decision_id} decision={d} onSave={updateDecision} />
          ))}
          {decisions.length > 80 && (
            <div style={{ color: "#94a3b8", fontSize: 12 }}>仅展示前 80 条，完整列表可通过 API 获取。</div>
          )}
        </div>
      </div>
    </div>
  );
}

function DecisionSankey({ stats, decisions }: {
  stats?: IntegrationStats;
  decisions: IntegrationDecision[];
}) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    if (!ref.current || !stats || stats.original_nodes <= 0) return;
    if (!chartRef.current) chartRef.current = echarts.init(ref.current);
    const counts = decisions.reduce(
      (acc, item) => ({ ...acc, [item.action]: (acc[item.action] || 0) + 1 }),
      { merge: stats.decisions_merge, keep: stats.decisions_keep, remove: stats.decisions_remove },
    );
    chartRef.current.setOption({
      tooltip: { trigger: "item" },
      series: [{
        type: "sankey",
        top: 8,
        bottom: 8,
        left: 4,
        right: 12,
        nodeGap: 8,
        nodeWidth: 10,
        data: [
          { name: "原始知识点" },
          { name: "merge" },
          { name: "keep" },
          { name: "remove" },
          { name: "整合保留" },
          { name: "预算移除" },
        ],
        links: [
          { source: "原始知识点", target: "merge", value: Math.max(1, counts.merge) },
          { source: "原始知识点", target: "keep", value: Math.max(1, counts.keep) },
          { source: "原始知识点", target: "remove", value: Math.max(1, counts.remove) },
          { source: "merge", target: "整合保留", value: Math.max(1, counts.merge) },
          { source: "keep", target: "整合保留", value: Math.max(1, counts.keep) },
          { source: "remove", target: "预算移除", value: Math.max(1, counts.remove) },
        ],
        label: { fontSize: 11, color: "#475569" },
        lineStyle: { color: "gradient", opacity: 0.35 },
        itemStyle: { borderWidth: 0 },
      }],
    }, true);
    const onResize = () => chartRef.current?.resize();
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      chartRef.current?.dispose();
      chartRef.current = null;
    };
  }, [stats, decisions]);

  if (!stats || stats.original_nodes <= 0) return null;
  return (
    <div style={{ marginTop: 12 }}>
      <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 6 }}>整合前后流向图</div>
      <div ref={ref} style={{ height: 150, border: "1px solid #e5e7eb", borderRadius: 6, background: "#fff" }} />
    </div>
  );
}

function DecisionCard({ decision, onSave }: {
  decision: IntegrationDecision;
  onSave: (decisionId: string, action: IntegrationDecision["action"], reason: string) => Promise<void>;
}) {
  const [action, setAction] = useState<IntegrationDecision["action"]>(decision.action);
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setAction(decision.action);
    setReason("");
  }, [decision.action, decision.reason]);

  const save = useCallback(async () => {
    setSaving(true);
    try {
      await onSave(decision.decision_id, action, reason.trim() || `教师手动调整为 ${ACTION_LABEL[action]}`);
    } finally {
      setSaving(false);
    }
  }, [action, decision.decision_id, onSave, reason]);

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
      <div style={{ display: "grid", gridTemplateColumns: "92px 1fr 54px", gap: 6, marginTop: 8 }}>
        <select
          value={action}
          onChange={(e) => setAction(e.target.value as IntegrationDecision["action"])}
          style={{ border: "1px solid #cbd5e1", borderRadius: 5, fontSize: 11, padding: "4px 5px" }}
        >
          <option value="merge">合并</option>
          <option value="keep">保留</option>
          <option value="remove">移除</option>
        </select>
        <input
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="教师覆盖理由"
          style={{ border: "1px solid #cbd5e1", borderRadius: 5, fontSize: 11, padding: "4px 6px" }}
        />
        <button onClick={save} disabled={saving} style={smallButtonStyle(saving)}>
          {saving ? "..." : "保存"}
        </button>
      </div>
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

function smallButtonStyle(disabled: boolean): React.CSSProperties {
  return {
    border: 0,
    borderRadius: 5,
    background: disabled ? "#cbd5e1" : "#2563eb",
    color: "#fff",
    fontSize: 11,
    cursor: disabled ? "not-allowed" : "pointer",
  };
}
