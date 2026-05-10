import { useEffect, useState } from "react";
import "./App.css";

type HealthResp = {
  ok: boolean;
  service: string;
  version: string;
  llm_key_configured: boolean;
};

function App() {
  const [health, setHealth] = useState<HealthResp | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // 同源请求：开发期由 vite proxy 转发，生产期由 FastAPI StaticFiles 同源 serve
    fetch("/api/health")
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(setHealth)
      .catch((e) => setError(String(e)));
  }, []);

  return (
    <div
      style={{
        fontFamily: "system-ui, -apple-system, sans-serif",
        padding: "2rem",
        maxWidth: 720,
        margin: "0 auto",
      }}
    >
      <h1>学科知识整合智能体</h1>
      <p style={{ color: "#666" }}>
        AI 全栈极速黑客松 · Phase 0 部署回路验证
      </p>

      <div
        style={{
          marginTop: "1.5rem",
          padding: "1rem 1.25rem",
          border: "1px solid #ddd",
          borderRadius: 8,
          background: "#fafafa",
        }}
      >
        <h3 style={{ margin: "0 0 0.5rem" }}>后端连通性</h3>
        {error && (
          <div style={{ color: "#c33" }}>
            ❌ 调用 <code>/api/health</code> 失败：{error}
          </div>
        )}
        {!error && !health && <div>⏳ 加载中...</div>}
        {health && (
          <div>
            <div>✅ 服务：{health.service} v{health.version}</div>
            <div>
              🔑 DeepSeek API key：
              {health.llm_key_configured ? "已配置" : "未配置（部署后需在魔搭 Secrets 中设置）"}
            </div>
          </div>
        )}
      </div>

      <div style={{ marginTop: "1.5rem", color: "#888", fontSize: "0.9rem" }}>
        <strong>下一步</strong>：进入 Phase 1，加上传组件、知识图谱、RAG 面板、对话面板。
      </div>
    </div>
  );
}

export default App;
