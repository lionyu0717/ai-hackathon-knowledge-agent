"""学科知识整合智能体 · FastAPI 入口

阶段：Phase 0 脚手架，仅提供 /api/health 与静态前端 mount。
后续 Phase 会按 routers/* 拆分接口注册。
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse

from .routers import parse as parse_router
from .services import store

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(
    title="学科知识整合智能体 API",
    version="0.1.0",
    description="AI 全栈极速黑客松 · 知识图谱构建 + 跨教材整合 + RAG 问答",
)


@app.on_event("startup")
def _on_startup() -> None:
    store.init_db()

# 开发期允许全部跨域；上线时（前端被打包到 static/）实际同源，CORS 不生效也无影响
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(parse_router.router)


@app.get("/api/health")
def health() -> dict:
    """部署回路探针：返回 ok + 版本 + 是否检测到 LLM key"""
    return {
        "ok": True,
        "service": "knowledge-agent",
        "version": app.version,
        "llm_provider": "modelscope",
        "llm_model": os.getenv("LLM_MODEL", "deepseek-ai/DeepSeek-V3.2"),
        "llm_key_configured": bool(os.getenv("MODELSCOPE_ACCESS_TOKEN")),
    }


# 静态前端：当 src/backend/static/index.html 存在时挂载（生产构建后）
# 本地开发时前端走 vite dev server (5173)，此处目录可能为空，跳过 mount
if (STATIC_DIR / "index.html").exists():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
else:
    @app.get("/")
    def root() -> JSONResponse:
        return JSONResponse(
            {
                "message": "前端尚未构建。开发期请访问 vite dev server (默认 http://localhost:5173)",
                "api_docs": "/docs",
                "health": "/api/health",
            }
        )
