import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // 开发期把 /api/* 代理到本地 FastAPI（避免 CORS 与端口切换）
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    // 构建产物输出到后端的 static 目录，FastAPI 直接 serve
    outDir: "../backend/static",
    emptyOutDir: true,
  },
});
