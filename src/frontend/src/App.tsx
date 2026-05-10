import { useEffect, useState } from "react";
import { UploadPanel, type TextbookSummary } from "./components/UploadPanel";
import { GraphView } from "./components/GraphView";
import { ChatPanel } from "./components/ChatPanel";
import { IntegratePanel } from "./components/IntegratePanel";
import { RagPanel } from "./components/RagPanel";
import "./App.css";

type CenterView = "global" | "graph" | "chapters";
type SideView = "integrate" | "rag" | "chat";

export default function App() {
  const [selected, setSelected] = useState<TextbookSummary | null>(null);
  const [view, setView] = useState<CenterView>("global");
  const [sideView, setSideView] = useState<SideView>("integrate");

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "320px 1fr 380px",
        gridTemplateRows: "48px 1fr",
        height: "100vh",
        fontFamily:
          'system-ui, -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif',
        color: "#1e293b",
      }}
    >
      {/* Header */}
      <header
        style={{
          gridColumn: "1 / span 3",
          background: "#1e293b",
          color: "#fff",
          padding: "0 1rem",
          display: "flex",
          alignItems: "center",
          gap: "0.75rem",
        }}
      >
        <div style={{ fontWeight: 700, fontSize: 16 }}>📚 学科知识整合智能体</div>
        <div style={{ fontSize: 12, color: "#cbd5e1" }}>
          AI 全栈极速黑客松 · Phase 3
        </div>
      </header>

      {/* Left: upload */}
      <UploadPanel
        onSelect={(tb) => {
          setSelected(tb);
          setView("graph");
        }}
        selectedId={selected?.textbook_id || null}
      />

      {/* Center: graph (默认) / chapters */}
      <main style={{ background: "#f8fafc", display: "flex", flexDirection: "column", overflow: "hidden" }}>
        {view === "global" ? (
          <>
            <div style={{ padding: "0.6rem 1rem", borderBottom: "1px solid #e5e7eb",
              background: "#fff", display: "flex", alignItems: "center", gap: 16 }}>
              <h2 style={{ margin: 0, fontSize: 16 }}>跨教材知识图谱</h2>
              <div style={{ color: "#64748b", fontSize: 12 }}>
                节点按教材来源上色，大小综合出现频次、连接度与点击频次
              </div>
              <div style={{ marginLeft: "auto", display: "flex", gap: 4 }}>
                <ViewBtn active={true} onClick={() => setView("global")}>🌐 全局图谱</ViewBtn>
                <ViewBtn active={false} disabled={!selected} onClick={() => selected && setView("graph")}>📊 单本图谱</ViewBtn>
                <ViewBtn active={false} disabled={!selected} onClick={() => selected && setView("chapters")}>📖 章节</ViewBtn>
              </div>
            </div>
            <div style={{ flex: 1, overflow: "hidden" }}>
              <GraphView textbookId="all" />
            </div>
          </>
        ) : selected ? (
          <>
            <div style={{ padding: "0.6rem 1rem", borderBottom: "1px solid #e5e7eb",
              background: "#fff", display: "flex", alignItems: "center", gap: 16 }}>
              <h2 style={{ margin: 0, fontSize: 16 }}>{selected.title}</h2>
              <div style={{ color: "#64748b", fontSize: 12 }}>
                {selected.total_pages} 页 · {selected.chapter_count} 章 ·{" "}
                {selected.total_chars.toLocaleString()} 字
              </div>
              <div style={{ marginLeft: "auto", display: "flex", gap: 4 }}>
                <ViewBtn active={false} onClick={() => setView("global")}>🌐 全局图谱</ViewBtn>
                <ViewBtn active={view === "graph"} onClick={() => setView("graph")}>📊 图谱</ViewBtn>
                <ViewBtn active={view === "chapters"} onClick={() => setView("chapters")}>📖 章节</ViewBtn>
              </div>
            </div>
            <div style={{ flex: 1, overflow: "hidden" }}>
              {view === "graph" ? (
                <GraphView key={selected.textbook_id} textbookId={selected.textbook_id} />
              ) : (
                <div style={{ height: "100%", overflowY: "auto", padding: "1rem" }}>
                  <ChapterList textbookId={selected.textbook_id} />
                </div>
              )}
            </div>
          </>
        ) : (
          <EmptyCenter />
        )}
      </main>

      {/* Right: features panel placeholder */}
      <aside style={{ borderLeft: "1px solid #e5e7eb", padding: "1rem", overflowY: "auto" }}>
        <div style={{ display: "flex", gap: 4, marginBottom: 12 }}>
          <ViewBtn active={sideView === "integrate"} onClick={() => setSideView("integrate")}>整合</ViewBtn>
          <ViewBtn active={sideView === "rag"} onClick={() => setSideView("rag")}>RAG</ViewBtn>
          <ViewBtn active={sideView === "chat"} onClick={() => setSideView("chat")}>对话</ViewBtn>
        </div>
        {sideView === "integrate" && <IntegratePanel />}
        {sideView === "rag" && <RagPanel />}
        {sideView === "chat" && <ChatPanel />}
      </aside>
    </div>
  );
}

function ViewBtn({ active, disabled = false, onClick, children }: {
  active: boolean; disabled?: boolean; onClick: () => void; children: React.ReactNode;
}) {
  return (
    <button disabled={disabled} onClick={onClick} style={{
      padding: "4px 10px", fontSize: 12, border: "1px solid",
      borderColor: active ? "#2563eb" : "#cbd5e1",
      background: disabled ? "#f1f5f9" : active ? "#2563eb" : "#fff",
      color: disabled ? "#94a3b8" : active ? "#fff" : "#475569",
      borderRadius: 4, cursor: disabled ? "not-allowed" : "pointer",
    }}>{children}</button>
  );
}

function EmptyCenter() {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        height: "100%",
        color: "#94a3b8",
      }}
    >
      <div style={{ fontSize: 48 }}>👈</div>
      <div style={{ marginTop: 8 }}>左侧上传一本教材开始</div>
    </div>
  );
}

type Chapter = {
  chapter_id: string;
  title: string;
  page_start: number;
  page_end: number;
  char_count: number;
};

function ChapterList({ textbookId }: { textbookId: string }) {
  const [chapters, setChapters] = useState<Chapter[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  // 关键：textbookId 变化时清空旧数据并重新拉取
  useEffect(() => {
    let cancelled = false;
    setChapters(null);
    setError(null);
    fetch(`/api/textbooks/${textbookId}/chapters`)
      .then((r) => (r.ok ? r.json() : Promise.reject(`HTTP ${r.status}`)))
      .then((data: Chapter[]) => {
        if (!cancelled) setChapters(data);
      })
      .catch((e) => {
        if (!cancelled) setError(String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [textbookId]);

  if (error) return <div style={{ color: "#c33" }}>加载章节失败：{error}</div>;
  if (!chapters) return <div>加载章节中...</div>;

  return (
    <div>
      <h3>章节结构（{chapters.length}）</h3>
      <table
        style={{
          width: "100%",
          fontSize: 13,
          background: "#fff",
          border: "1px solid #e5e7eb",
          borderCollapse: "collapse",
        }}
      >
        <thead>
          <tr style={{ background: "#f8fafc", textAlign: "left" }}>
            <th style={{ padding: "8px 12px", borderBottom: "1px solid #e5e7eb" }}>编号</th>
            <th style={{ padding: "8px 12px", borderBottom: "1px solid #e5e7eb" }}>标题</th>
            <th style={{ padding: "8px 12px", borderBottom: "1px solid #e5e7eb" }}>页码</th>
            <th style={{ padding: "8px 12px", borderBottom: "1px solid #e5e7eb", textAlign: "right" }}>
              字数
            </th>
          </tr>
        </thead>
        <tbody>
          {chapters.map((c) => (
            <tr key={c.chapter_id}>
              <td style={{ padding: "6px 12px", borderBottom: "1px solid #f1f5f9", color: "#64748b" }}>
                {c.chapter_id}
              </td>
              <td style={{ padding: "6px 12px", borderBottom: "1px solid #f1f5f9" }}>{c.title}</td>
              <td style={{ padding: "6px 12px", borderBottom: "1px solid #f1f5f9", color: "#64748b" }}>
                {c.page_start}-{c.page_end}
              </td>
              <td
                style={{
                  padding: "6px 12px",
                  borderBottom: "1px solid #f1f5f9",
                  textAlign: "right",
                  color: "#64748b",
                  fontVariantNumeric: "tabular-nums",
                }}
              >
                {c.char_count.toLocaleString()}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
