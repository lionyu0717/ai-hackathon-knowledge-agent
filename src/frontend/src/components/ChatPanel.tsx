import { useCallback, useEffect, useState } from "react";

type ChatMessage = {
  role: "user" | "assistant" | "tool";
  content: string;
  tool_name?: string | null;
  timestamp: string;
};

export function ChatPanel() {
  const [sessionId, setSessionId] = useState(() => localStorage.getItem("teacher-chat-session") || "");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("为什么合并 [[炎症]]？");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!sessionId) return;
    fetch(`/api/chat/${sessionId}`)
      .then((r) => r.ok ? r.json() : null)
      .then((data) => data?.history && setMessages(data.history))
      .catch(() => {});
  }, [sessionId]);

  const send = useCallback(async () => {
    const text = input.trim();
    if (!text) return;
    setLoading(true);
    setInput("");
    setMessages((cur) => [...cur, { role: "user", content: text, timestamp: new Date().toISOString() }]);
    try {
      const r = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, session_id: sessionId || null }),
      });
      const data = await r.json();
      if (data.session_id) {
        setSessionId(data.session_id);
        localStorage.setItem("teacher-chat-session", data.session_id);
      }
      setMessages(data.history || []);
    } finally {
      setLoading(false);
    }
  }, [input, sessionId]);

  return (
    <div>
      <h3 style={{ margin: 0, fontSize: 15 }}>教师对话 Agent</h3>
      <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 8, maxHeight: 430, overflowY: "auto" }}>
        {messages.length === 0 && (
          <div style={{ fontSize: 12, color: "#94a3b8", padding: 10, border: "1px solid #e5e7eb", borderRadius: 6 }}>
            可询问整合理由，或说“不要合并 [[A]] 和 [[B]]”“请保留 [[某知识点]]”。
          </div>
        )}
        {messages.map((m, idx) => (
          <div key={idx} style={{
            alignSelf: m.role === "user" ? "flex-end" : "flex-start",
            maxWidth: "92%", padding: 9, borderRadius: 7,
            background: m.role === "user" ? "#2563eb" : "#f8fafc",
            color: m.role === "user" ? "#fff" : "#1e293b",
            border: m.role === "user" ? "none" : "1px solid #e5e7eb",
            fontSize: 12, lineHeight: 1.55, whiteSpace: "pre-wrap",
          }}>
            {m.tool_name && m.role !== "user" && (
              <div style={{ color: "#64748b", fontSize: 10, marginBottom: 4 }}>{m.tool_name}</div>
            )}
            {m.content}
          </div>
        ))}
      </div>
      <textarea
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) send();
        }}
        style={{
          width: "100%", boxSizing: "border-box", marginTop: 12, minHeight: 74,
          border: "1px solid #cbd5e1", borderRadius: 6, padding: 8,
          fontSize: 12, fontFamily: "inherit", resize: "vertical",
        }}
      />
      <button onClick={send} disabled={loading} style={{
        width: "100%", marginTop: 8, padding: "6px 10px", border: 0,
        borderRadius: 5, background: loading ? "#cbd5e1" : "#2563eb",
        color: "#fff", cursor: loading ? "not-allowed" : "pointer", fontSize: 12,
      }}>
        {loading ? "处理中..." : "发送"}
      </button>
    </div>
  );
}
