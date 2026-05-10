import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import * as echarts from "echarts";

type GraphNode = {
  id: string;
  name: string;
  definition: string;
  category: string;
  chapter: string;
  chapter_id?: string;
  page: number;
  textbook_id: string;
  textbook_title?: string;
  value: number;
};
type GraphEdge = {
  source: string;
  target: string;
  relation_type: string;
  description: string;
};
type GraphPayload = {
  textbook?: { id: string; title: string; filename: string };
  nodes: GraphNode[];
  edges: GraphEdge[];
  stats: { node_count: number; edge_count: number; categories?: string[]; textbook_count?: number };
};

type Progress = {
  status?: "queued" | "extracting" | "done" | "failed";
  total?: number;
  done?: number;
  nodes?: number;
  edges?: number;
  error?: string;
  current_chapter?: string;
};

const RELATION_COLOR: Record<string, string> = {
  prerequisite: "#dc2626",
  parallel: "#0ea5e9",
  contains: "#16a34a",
  applies_to: "#a855f7",
};

const RELATION_LABEL: Record<string, string> = {
  prerequisite: "前置依赖",
  parallel: "并列",
  contains: "包含",
  applies_to: "应用于",
};

export function GraphView({ textbookId }: { textbookId: string }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);
  const [graph, setGraph] = useState<GraphPayload | null>(null);
  const [progress, setProgress] = useState<Progress>({});
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<GraphNode | null>(null);

  // 拉图
  const fetchGraph = useCallback(async () => {
    try {
      const r = await fetch(`/api/graph/${textbookId}`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = (await r.json()) as GraphPayload;
      setGraph(data);
    } catch (e) {
      setError(String(e));
    }
  }, [textbookId]);

  // 拉进度（用于 polling）
  const fetchProgress = useCallback(async () => {
    try {
      const r = await fetch(`/api/graph/${textbookId}/progress`);
      const data = (await r.json()) as Progress;
      setProgress(data);
      return data.status;
    } catch {
      return undefined;
    }
  }, [textbookId]);

  // textbookId 变化：重置 + 拉图
  useEffect(() => {
    setGraph(null);
    setProgress({});
    setError(null);
    setSelected(null);
    fetchGraph();
    fetchProgress();
  }, [textbookId, fetchGraph, fetchProgress]);

  // 抽取过程中轮询
  useEffect(() => {
    if (progress.status !== "queued" && progress.status !== "extracting") return;
    const t = setInterval(async () => {
      const s = await fetchProgress();
      if (s === "done") {
        clearInterval(t);
        fetchGraph();
      } else if (s === "failed") {
        clearInterval(t);
      }
    }, 2500);
    return () => clearInterval(t);
  }, [progress.status, fetchGraph, fetchProgress]);

  // 触发抽取
  const triggerBuild = useCallback(async () => {
    setProgress({ status: "queued" });
    const r = await fetch(`/api/graph/build/${textbookId}`, { method: "POST" });
    if (!r.ok) {
      setError(`build failed: ${await r.text()}`);
      return;
    }
    fetchProgress();
  }, [textbookId, fetchProgress]);

  // 渲染 ECharts
  useEffect(() => {
    if (!containerRef.current) return;
    if (!chartRef.current) {
      chartRef.current = echarts.init(containerRef.current);
      chartRef.current.on("click", (params: any) => {
        if (params.dataType === "node") {
          setSelected(params.data as GraphNode);
        }
      });
      const onResize = () => chartRef.current?.resize();
      window.addEventListener("resize", onResize);
      return () => {
        window.removeEventListener("resize", onResize);
        chartRef.current?.dispose();
        chartRef.current = null;
      };
    }
  }, []);

  const option = useMemo(() => {
    if (!graph) return null;
    const categories = (graph.stats.categories ?? Array.from(new Set(graph.nodes.map((n) => n.category))));
    const catIdx = new Map(categories.map((c, i) => [c, i]));

    return {
      tooltip: {
        trigger: "item",
        formatter: (p: any) => {
          if (p.dataType === "edge") {
            return `<b>${RELATION_LABEL[p.data.relation_type] || p.data.relation_type}</b><br/>${p.data.description || ""}`;
          }
          return `<b>${p.data.name}</b><br/><span style="color:#94a3b8">${p.data.category} · ${p.data.chapter}</span><br/>${(p.data.definition || "").slice(0, 100)}`;
        },
      },
      legend: [{ data: categories, top: 8, textStyle: { fontSize: 11 } }],
      animation: true,
      series: [{
        type: "graph",
        layout: "force",
        roam: true,
        draggable: true,
        focusNodeAdjacency: true,
        force: { repulsion: 220, edgeLength: [60, 140], gravity: 0.06 },
        label: {
          show: true,
          position: "right",
          fontSize: 11,
          formatter: (p: any) => p.data.name,
        },
        edgeSymbol: ["none", "arrow"],
        edgeSymbolSize: [0, 6],
        lineStyle: { width: 1.2, opacity: 0.65, curveness: 0.05 },
        emphasis: {
          focus: "adjacency",
          lineStyle: { width: 2.5, opacity: 1 },
          label: { fontWeight: "bold" },
        },
        categories: categories.map((c) => ({ name: c })),
        nodes: graph.nodes.map((n) => ({
          ...n,
          symbolSize: Math.min(60, 16 + n.value * 4),
          category: catIdx.get(n.category) ?? 0,
        })),
        links: graph.edges.map((e) => ({
          ...e,
          lineStyle: { color: RELATION_COLOR[e.relation_type] || "#94a3b8" },
        })),
      }],
    };
  }, [graph]);

  useEffect(() => {
    if (chartRef.current && option) chartRef.current.setOption(option, true);
  }, [option]);

  // 渲染态机
  const isExtracting = progress.status === "queued" || progress.status === "extracting";
  const hasGraph = graph && graph.nodes.length > 0;

  return (
    <div style={{ position: "relative", height: "100%", display: "flex", flexDirection: "column" }}>
      {/* 顶部状态条 */}
      <div
        style={{
          display: "flex", alignItems: "center", gap: 12,
          padding: "0.6rem 1rem", borderBottom: "1px solid #e5e7eb", background: "#fff",
        }}
      >
        {hasGraph ? (
          <>
            <div style={{ fontSize: 13, color: "#475569" }}>
              📊 节点 <b>{graph.stats.node_count}</b> · 关系 <b>{graph.stats.edge_count}</b>
              {graph.stats.categories && (
                <> · 类别 {graph.stats.categories.length}</>
              )}
            </div>
            <button onClick={triggerBuild} disabled={isExtracting}
              style={btnStyle(isExtracting)}>
              {isExtracting ? "抽取中..." : "重新抽取"}
            </button>
          </>
        ) : (
          <button onClick={triggerBuild} disabled={isExtracting} style={btnStyle(isExtracting)}>
            {isExtracting ? "抽取中..." : "🧠 抽取知识图谱"}
          </button>
        )}

        {isExtracting && (
          <div style={{ fontSize: 12, color: "#d97706" }}>
            进度 {progress.done || 0}/{progress.total || "?"} 章 · 已抽 {progress.nodes || 0} 节点
            {progress.current_chapter && <> · 当前 {progress.current_chapter}</>}
          </div>
        )}
        {error && <div style={{ color: "#c33", fontSize: 12 }}>{error}</div>}
      </div>

      {/* 图谱画布 */}
      <div style={{ position: "relative", flex: 1, background: "#f8fafc" }}>
        <div ref={containerRef} style={{ position: "absolute", inset: 0 }} />
        {!hasGraph && !isExtracting && (
          <div style={{ position: "absolute", inset: 0, display: "flex",
            alignItems: "center", justifyContent: "center",
            color: "#94a3b8", fontSize: 14, pointerEvents: "none" }}>
            点击上方「🧠 抽取知识图谱」按钮开始构建
          </div>
        )}
        {progress.status === "failed" && (
          <div style={{ position: "absolute", top: 16, right: 16,
            padding: "8px 12px", background: "#fef2f2", border: "1px solid #fecaca",
            borderRadius: 6, color: "#b91c1c", fontSize: 12 }}>
            抽取失败：{progress.error || "未知错误"}
          </div>
        )}

        {/* 节点详情侧抽屉 */}
        {selected && (
          <div style={{ position: "absolute", top: 16, right: 16,
            width: 320, padding: 14, background: "#fff",
            border: "1px solid #e5e7eb", borderRadius: 8,
            boxShadow: "0 6px 20px rgba(15,23,42,0.08)", fontSize: 13 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div style={{ fontWeight: 700, fontSize: 15 }}>{selected.name}</div>
              <button onClick={() => setSelected(null)}
                style={{ border: 0, background: "transparent", cursor: "pointer", color: "#94a3b8" }}>✕</button>
            </div>
            <div style={{ color: "#64748b", fontSize: 11, marginTop: 4 }}>
              {selected.category} · {selected.chapter} · 第 {selected.page} 页
            </div>
            <div style={{ marginTop: 10, lineHeight: 1.5 }}>{selected.definition}</div>
          </div>
        )}
      </div>
    </div>
  );
}

function btnStyle(disabled: boolean): React.CSSProperties {
  return {
    padding: "5px 12px",
    fontSize: 12,
    border: 0,
    borderRadius: 5,
    background: disabled ? "#cbd5e1" : "#2563eb",
    color: "#fff",
    cursor: disabled ? "not-allowed" : "pointer",
  };
}
