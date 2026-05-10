# ==========================================================================
# Stage 1: 构建前端（Vite + React）
# ==========================================================================
FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend

# 复制依赖清单并安装（利用 docker layer cache）
COPY src/frontend/package*.json ./
RUN npm ci --no-audit --no-fund --loglevel=error

# 复制源码并构建
COPY src/frontend/ ./
# Vite 配置中 outDir 指向 ../backend/static，但 Docker 内独立路径，先在本地构建到 dist/
# 通过 --outDir 覆盖
RUN npx vite build --outDir dist --emptyOutDir

# ==========================================================================
# Stage 2: Python 后端（FastAPI + uvicorn）+ 静态前端
# ==========================================================================
FROM python:3.11-slim AS runtime

# 关键环境变量
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/app/data/models \
    SENTENCE_TRANSFORMERS_HOME=/app/data/models \
    TRANSFORMERS_OFFLINE=0 \
    PORT=7860

WORKDIR /app

# 系统依赖（PyMuPDF 需要的最小集合）
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Python 依赖
# 关键优化：先装 CPU-only torch（~200MB vs CUDA 版 ~2GB），再装其他
COPY requirements.txt ./
RUN pip install --no-cache-dir \
        --index-url https://download.pytorch.org/whl/cpu \
        --extra-index-url https://pypi.org/simple \
        torch==2.5.1 \
    && pip install --no-cache-dir -r requirements.txt \
    && pip cache purge \
    && find /usr/local/lib/python3.11/site-packages -name "tests" -type d -exec rm -rf {} + 2>/dev/null || true \
    && find /usr/local/lib/python3.11/site-packages -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

# 后端代码
COPY src/backend/ ./src/backend/

# 把前端 build 产物拷进 backend/static（FastAPI mount）
COPY --from=frontend-builder /app/frontend/dist ./src/backend/static

# 数据目录（持久化卷可挂在这里）
RUN mkdir -p /app/data/db /app/data/index/chroma /app/data/textbooks /app/data/models

# 魔搭创空间默认监听 7860 端口
EXPOSE 7860

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:${PORT}/api/health || exit 1

# 启动命令
CMD ["sh", "-c", "uvicorn src.backend.main:app --host 0.0.0.0 --port ${PORT:-7860}"]
