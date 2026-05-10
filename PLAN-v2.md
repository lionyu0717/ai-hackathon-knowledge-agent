# 学科知识整合智能体 · 4h 作战手册（PLAN-v2）

> 本文档整合：① 赛题原文要求摘要；② v2 关键架构决策；③ 4 小时分阶段执行步骤；④ 文件清单 / 风险降级 / 评分预测。
> **比赛剩余 4 小时（240 分钟）**。所有时间表已按 4h 重新分配。

---

## 第 0 部分 · 赛题原文要求（不可遗忘的硬约束）

来源：`赛题文档.pdf`，浙江大学未来学习中心 AI 生态 2026.5。

### 0.1 任务与产物

> 「用 AI 帮教师把 7 本教材变成不到 2.1 本的精华，而且变完之后教学效果不打折。」

智能体必须能：
1. 自动加载多本教材（多格式支持）
2. 为每本教材构建知识图谱并可视化
3. 跨教材识别知识点的重叠、互补与缺失
4. 将多本教材的内容整合压缩到不超过原始体量 **30%** 的精华版本
5. 基于整合后的知识库进行 **RAG 精准问答**（必须引用原文来源）
6. 自主设计 Agent 架构并提交架构说明文档
7. 通过与学科教师的多轮对话，迭代优化整合方案

### 0.2 P0 必做功能（10 项 + 验收标准）

每项的**验收标准**直接来自赛题文档，必须在交付前逐条核对。

| # | 功能 | 关键硬约束 | ✅ 验收标准（赛题原文） |
|---|------|-----------|------------------------|
| 1 | 多格式解析 | PDF/MD/TXT 必须，DOCX 建议，Excel 可选；逐页解析；输出统一 JSON schema；PDF 需识别章节标题、过滤页眉页脚、跳过图表区 | **上传一本 PDF 教材后，系统能正确识别出章节结构并显示在前端** |
| 2 | 单本知识图谱构建 | 每章 LLM 抽取节点；节点 schema 含 id/name/definition/category/chapter/page；关系类型 ≥ 3 种；prompt 用 JSON + few-shot | **选择一本教材后，系统能生成该教材的知识图谱数据（JSON 格式的节点和边列表），并在前端以可视化形式展示** |
| 3 | 图谱交互可视化 | 点击节点查详情；节点大小/颜色映射频次；不同教材不同色；缩放+拖拽 | **知识图谱能在浏览器中渲染，点击节点能看到详细信息，能通过视觉元素区分不同教材和频次** |
| 4 | 跨教材整合 | 语义对齐 ≥ 1 种；输出决策（merge/keep/remove + reason + confidence）；**压缩比 ≤ 30%**；前端展示压缩比 | **加载 2 本以上教材后，系统能自动识别重复知识点，执行整合，输出整合决策列表，压缩比不超过 30%** |
| 5 | RAG 问答 | chunk 500–800 字 + 50–100 overlap；元数据（教材/章节/页码）；向量库；top-5；回答必须引用原文 [教材, 第X章, 第X页]；找不到时拒答 | **上传教材 → 建立索引 → 输入问题 → 获得带引用来源的回答，引用的教材和章节与问题内容相关** |
| 6 | Agent 架构说明文档 | 含架构总览（mermaid）/设计决策论证/数据流/取舍权衡 | 评分项，无独立验收，但**没有提交此文档 D 维度 0–3 分** |
| 7 | 多轮对话迭代 | 教师可用自然语言改决策；历史持久化；图谱实时更新 | **教师能通过对话修改至少一项整合决策，系统调整后在图谱或整合结果中反映出变化** |
| 8 | Web SPA 界面 | 单页应用；建议三栏；1920×1080 正常 | **打开浏览器能看到完整的功能界面，所有功能模块可操作** |
| 9 | 整合报告 | 整合概览 / 决策摘要 / 图谱统计 / 3-5 典型案例 / 教学完整性说明 | **报告完整涵盖以上五项内容，数据与系统实际运行结果一致** |
| 10 | 开发文档 | README + 需求分析 + 系统设计 + Agent 架构说明 | **另一个开发者拿到你的仓库，按照 README 操作，能在本地成功运行系统** |

> **本计划每个 Phase 完成后必须对照「✅ 验收标准」列勾选**，未达标不进入下一 Phase。

### 0.3 评分维度（满分 100 + P2 附加）

| 维度 | 基础分 | 进阶分 | 我们的目标 |
|------|--------|--------|-----------|
| A 文档完整性与可复现性 | 11 | 15 | 14 |
| B 功能实现完整度 | 20 | 25 | 22 |
| C 知识图谱可视化创新 | 6 | 13 | 10 |
| D **Agent 架构设计** | 15 | 20 | **18** |
| E 代码质量与工程规范 | 10 | 17 | 14 |
| F 创新与自由发挥 | — | 10 | 6 |
| **小计** | **62** | **100** | **84 ± 4** |
| P2 技术报告附加 | — | +15 | **+5~8** |

### 0.4 提交要求

- **必交**：① 公开 GitHub 仓库链接 ② 公网部署链接（魔搭创空间）
- 缺一不可，否则视为未完成
- `.gitignore` 必须排除 `*.pdf`（教材文件 826MB 无法推送）
- P2 技术报告（飞书文档链接）选交，可在比赛结束后 24h 内补交

### 0.5 资源

- 赛方提供 7 本教材文件（已下载，`textbooks.zip`，800MB）
- 整合报告必须基于这 7 本教材实测数据

---

## 第 1 部分 · v2 关键架构决策（5 项已与用户确认）

### 决策 1：Hybrid Function-Agent 架构

不为「拆 Agent 而拆」，按**任务语义**精确选型：

| 阶段 | 性质 | 实现 |
|------|------|------|
| 文档解析 / 嵌入 / 向量索引 | 确定性函数 | 纯 function |
| 知识点抽取 | 单步 LLM 调用 | 纯 function（一次 prompt → 一次 JSON） |
| **整合决策** | 多步推理 + 工具调用 | **整合 Agent**（自主选择 merge/keep/remove） |
| **多轮对话** | 多步推理 + 工具调用 | **对话 Agent**（function calling: explain/modify/query） |
| RAG 问答 | 单步检索 + 生成 | 纯 function（默认）；时间允许升级 Agentic RAG（query rewrite + 拒答判断） |

**论证落点**（写入 `docs/Agent架构说明.md` 与 P2 报告）：
> 「我们用 Agent 抽象在自主决策与多工具协调的环节，用纯函数在确定性环节。这比『为拆而拆』更符合工程现实，且每个 Agent 都能独立测试与重放。」

### 决策 2：30% 压缩 = 原文精选 + 元数据导览（不重写）

**v1 错误**：让 LLM 把每个节点重写为「精华条目」 → token 爆炸 + 引用失真。

**v2 修正**：

```
30% 整合产物（report/精华教材.md）：
  对每个知识簇 → 选 1 个最佳代表 chunk（原文）+ 1-2 个补充 chunk（原文）
                + LLM 生成 1-2 行「整合元数据」导览
  对独有知识点 → 保留 1-2 个原始 chunk
  
  ≤ 0.28 × original_total_chars（留 2% 缓冲）
  按 importance（freq×0.4 + degree×0.3 + has_def×0.3）排序截断
```

每个条目示例：
```markdown
## 知识点 #001：动作电位
> [整合元数据] 综合自《生理学》第2章 p.35-37 与《神经科学基础》第3章 p.48-50。
> 主版本来源：《生理学》（结构最完整）；补充：《神经科学基础》补充髓鞘传导细节。

**[原文摘录·主版本]** 来源：《生理学》第2章 p.35-37
动作电位是细胞受到刺激后……（**100% 原文**）

**[补充原文]** 来源：《神经科学基础》第3章 p.48
在有髓神经纤维中……（**100% 原文**）
```

只有 `[整合元数据]` 两行是 LLM 生成。token 成本估算：~700 节点 × 800 tokens = 0.56M（v1 是 2.8M，**降 5x**）。

### 决策 3：RAG 永远检索 corpus_raw（原始 chunk）

**两个语料库严格分离**：

```
原始 7 本教材 → 解析为 Markdown → 切块
                                    ↓
                      corpus_raw（永远是 RAG 检索源）
                                    ↓
                          知识点抽取 + 对齐
                                    ↓
            ┌────────────┬─────────────┐
            ↓            ↓             ↓
      [知识图谱]   [整合产物]      [RAG 检索库]
      节点+边     ≤30% 精选         = corpus_raw
      
      面向人              面向 LLM
      （学生/教师）        （引用必须真）
```

引用 100% 真实可跳页。整合产物只是给学生/教师阅读的下游精炼版本。

### 决策 4：PDF → Markdown 中间格式（PyMuPDF4LLM）

| 工具 | 输出 | 5h 风险 | 选用 |
|------|------|---------|------|
| **PyMuPDF4LLM** | 直出 Markdown | 低 | ✅ 主用 |
| MinerU | Markdown 优 + 公式/表格 OCR | 中（GPU 依赖重） | 备选（仅当某本教材公式严重丢失） |
| 原版 PyMuPDF | 纯文本 | 低但下游成本高 | ❌ 弃 |

**为什么 Markdown 而不是 TXT**：
- 保留 H1/H2 章节层级 → 切块时天然带 chapter+section 元数据
- 切块边界优先 `\n##` → `\n\n` → 句号 → 字符截断
- BGE 嵌入在结构化 Markdown 上召回比 TXT 高 5-10%

### 决策 5：自建 Benchmark 提前到 Phase 4 之前

- **题数 25 题**（事实 8 / 比较 6 / 推理 6 / 跨教材 5）
- 由 LLM 基于已解析章节自动生成 → 人工 spot-check 5 分钟
- 评测脚本一键运行（`python -m benchmark.run`，5 分钟跑完一组对比）
- 指标：**引用 Hit@3** + **Answer Faithfulness（LLM-judge 0-5）** + token/latency
- 对比矩阵：chunk_size {400,600,1000} × retriever {vec, vec+bm25(RRF)} × rerank {off, on}
- **同时**做整合策略对比：「精华改写库」vs「原文选择库」的引用准确率 → 直接证明决策 2 正确

---

## 第 2 部分 · 技术栈（确定版）

| 层级 | 选型 | 备注 |
|------|------|------|
| 后端 | FastAPI + uvicorn | 自动 OpenAPI doc 可截图入文档 |
| 前端 | React + Vite + TypeScript + TailwindCSS | shadcn/ui 按需 |
| 图谱可视化 | ECharts relation graph | 力导向 + 缩放 + 拖拽 + 点击全开箱 |
| **LLM** | **ModelScope API Inference**（OpenAI 兼容，`MODELSCOPE_ACCESS_TOKEN` 鉴权） | 优先免费额度模型；额度/限流时使用 `模型ID:外部提供方`，如 `deepseek-ai/DeepSeek-V3.2:DeepSeek` |
| Embedding | BGE-small-zh-v1.5（sentence-transformers 本地） | 100MB，魔搭有 GPU 加速 |
| 向量库 | ChromaDB（持久化磁盘） | 内嵌 Python 零部署 |
| BM25 | jieba + rank_bm25 | 中文分词 |
| Rerank（可选） | BGE-reranker-base | 仅当时间剩 30+min |
| Agent 框架 | **不引入**，用 OpenAI SDK function calling 手动编排 | 整合 Agent + 对话 Agent |
| PDF 解析 | **PyMuPDF4LLM**（直出 Markdown） | MinerU 备选 |
| MD/DOCX 解析 | markdown-it-py / python-docx | 标准 |
| 数据库 | SQLite（标准库 sqlite3） | 单文件零配置 |
| **部署** | **魔搭创空间（ModelScope Studio，Docker SDK）** | 单容器 FastAPI + 静态前端 |
| 容器化 | 单 Dockerfile（multi-stage） | 不用 docker-compose |
| 仓库 | GitHub Public Repo | 必交项 |

**主动反向选型**（写入架构文档「取舍与权衡」）：
- ❌ LangChain / LangGraph（5h 调试 callback 不划算）
- ❌ GraphRAG / Neo4j（图谱仅用于可视化）
- ❌ OpenAI Embedding（国内网络 + 计费）
- ❌ 前后端分离部署（单容器 FastAPI 直接 mount static 前端）

---

## 第 3 部分 · 4h Phase 拆解（240 分钟）

```
0:00 ─── 0:25  Phase 0  脚手架 + 部署回路打通       (25 min)  ← 现在执行
0:25 ─── 0:55  Phase 1  解析（PDF→Markdown）+ 数据模型 (30 min)
0:55 ─── 1:35  Phase 2  知识抽取 + 单本图谱可视化   (40 min)
1:35 ─── 2:15  Phase 3  跨教材整合（双重对齐+选择式压缩） (40 min)  ★
2:15 ─── 3:00  Phase 4  RAG pipeline + benchmark    (45 min)  ★
3:00 ─── 3:25  Phase 5  对话 Agent + UI 收尾        (25 min)
3:25 ─── 3:50  Phase 6  四份文档 + 整合报告         (25 min)  ★ 高 ROI
3:50 ─── 4:00  Phase 7  部署 + 端到端验证 + 提交    (10 min)
```

### Phase 0（0:00–0:25）脚手架 + 部署回路 ★ 关键

**核心原则**：先打通「本地 → GitHub → 魔搭公网」回路，再做功能。否则最后 30 分钟必踩坑。

1. 验证本地环境：python/node/git/gh
2. 创建项目目录结构（已有 `ai-hackathon-knowledge-agent/`）
3. 后端：FastAPI 最简 app（`/api/health` 返回 `{ok:true}`）
4. 前端：Vite + React + TS（默认页 + 一个调用 `/api/health` 的 fetch 验证 CORS）
5. 写 `.gitignore`（排除 `*.pdf`、`*.zip`、`data/`、`node_modules/`、`.env`）
6. 写 `Dockerfile`（multi-stage：build 前端 → copy 静态文件 → uvicorn serve）
7. `git init` + 首次 commit
8. 创建 GitHub Public 仓库 → push
9. 在魔搭创空间创建 Studio（Docker SDK）→ 关联仓库 / push 镜像
10. **验证**：浏览器访问公网 URL 看到默认页 + `/api/health` 返回 200

**得分锁定**：E 部署 +2，A README +1

### Phase 1（0:25–0:55）解析 + 数据模型

1. `requirements.txt` 加：pymupdf4llm, python-docx, markdown-it-py
2. `src/backend/services/parser.py`：
   - `parse_pdf(path) → markdown`（PyMuPDF4LLM）
   - `parse_md/parse_txt/parse_docx` → markdown
   - 章节结构识别：在 Markdown 上按 `^# ` 与 `^## ` + 正则 `第[一二三四五六七八九十百\d]+章` 双重识别
3. `src/backend/models/schemas.py`：Textbook / Chapter / KnowledgeNode / KnowledgeEdge / Chunk Pydantic 模型
4. SQLite + `init.sql`
5. 接口：`POST /api/upload`（multipart）、`GET /api/textbooks`、`GET /api/textbooks/{id}/chapters`
6. 前端 `UploadPanel.tsx`（react-dropzone）
7. **本地验证**：解压 textbooks.zip 取 1 本，上传 → 章节列表正确

### Phase 2（0:55–1:35）知识抽取 + 图谱

1. `services/llm.py`：DeepSeek client（OpenAI SDK + base_url）
2. `services/extractor.py`：抽取 prompt
   ```
   你是教育领域专家。从下面章节内容中提取 5-15 个核心知识点。
   每个知识点必须是 2-10 字的原子名词短语，可独立回答"什么是X？"。
   同时识别关系（prerequisite/parallel/contains/applies_to）。
   严格输出 JSON：{"nodes":[{"name","definition","category"}], "edges":[{"source","target","relation_type","description"}]}
   拒绝输出："本章简介"、"复习题"、章节号本身。
   章节：{chapter.content[:6000]}
   ```
   附 1 个 few-shot 示例
3. `asyncio.gather` 并发（5 并发限速）
4. 缓存（key = chapter content md5）避免重跑烧 token
5. 入库 + ID 规范：`f"{book_id}_{ch_id}_{md5(name)[:6]}"`
6. 前端 `GraphView.tsx`：ECharts relation graph
   - categories=教材；symbolSize=节点频次；roam+draggable 开启
   - 点击 → 右侧 drawer 详情

### Phase 3（1:35–2:15）跨教材整合 ★

1. `services/embedder.py`：BGE-small-zh-v1.5 加载（缓存到 `data/models/`）
2. `services/aligner.py`：
   - **Stage 1 召回**：embed `name + definition[:200]` → cos_sim ≥ 0.82 候选对
   - **Stage 2 LLM 精判**（5 对/批，并发）：四要素 prompt（指称对象/定义重叠/学科范畴/抽象层级）→ {same/related/different} + confidence
   - **Stage 3 Union-Find** 聚类
3. `services/integrator.py`（**整合 Agent**，function calling）：
   - 工具：`get_chunk(chunk_id)`, `score_chunks(cluster)`, `compute_importance(node)`
   - 流程：对每簇 → 调 score_chunks 选最佳代表 chunk → 选 1-2 补充 chunk → 输出 decision
   - 决策结构：`{decision_id, action, affected_nodes, result_chunks[], reason, confidence}`
   - **预算控制**：累加 chunk 字数 ≤ `0.28 × original_total`，超出按 importance 截断 → action=remove
4. 接口：`POST /api/integrate/run`、`GET /api/integrate/decisions`、`GET /api/integrate/stats`
5. 前端：「整合操作」Tab 显示压缩比 + 决策列表
6. **本地验证**：上传 ≥ 2 本教材 → 整合 → 压缩比 ≤ 30%；最终 Phase 7 必须基于 7 本教材重跑整合统计

### Phase 4（2:15–3:00）RAG + Benchmark ★

1. `services/chunker.py`：在 Markdown 上层级切块
   - 按 `\n##` → `\n\n` → 句号；目标 600 字 + 100 overlap
   - 元数据：`chunk_id, textbook_id, chapter_id, section_title, page_start, page_end`
2. `services/index.py`：
   - 全部 chunks → BGE embed → ChromaDB 持久化（`data/index/chroma/`）
   - BM25 索引：jieba 分词 + rank_bm25 → pickle 持久化
3. `services/retriever.py`：
   - vec_top20 + bm25_top20 → RRF 融合（k=60）→ top-10
   - （可选）BGE-reranker → top-5
4. `services/answerer.py`：
   ```
   system = """你只能基于上下文回答。每个事实陈述后必须附 [教材, 第X章, 第X页]。
   如上下文不足，必须回复'当前知识库中未找到相关信息'。"""
   user = "上下文：\n[1] {chunk1}...\n\n问题：{q}"
   ```
   返回 `{answer, citations[], source_chunks[]}`
5. 接口：`POST /api/rag/index`、`POST /api/rag/query`、`GET /api/rag/status`
6. 前端 `RagPanel.tsx`：状态条 + 输入框 + 引用卡片
7. **Benchmark**（10-15 min）：
   - `services/benchmark.py`：让 LLM 基于已抽取知识点生成 25 题（事实 8/比较 6/推理 6/跨教材 5）
   - 标注 ground-truth 教材+章节+预期答案要点
   - `python -m backend.benchmark.run` 跑对比矩阵 → 输出 `benchmark/results.md`
   - **额外对比**：从 corpus_raw 检索 vs 从精华改写库检索 的引用准确率（验证决策 2/3）

### Phase 5（3:00–3:25）对话 Agent + UI 收尾

1. `services/dialog_agent.py`（**对话 Agent**，function calling）：
   - 工具：`explain_decision(id)`, `modify_decision(id, new_action, reason)`, `query_rag(question)`
   - DeepSeek function calling，多轮上下文
2. 会话历史持久化（SQLite: session_id, role, content, tool_calls, ts）
3. 前端 `ChatPanel.tsx`：聊天泡泡 + localStorage 兜底
4. 三栏布局：左 UploadPanel | 中 GraphView（最大）| 右 Tabs(整合/RAG/对话/报告)
5. 顶部搜索框：高亮节点（ECharts dispatchAction）
6. **本地验证**：教师说「不要合并 X 和 Y」→ 决策更新 → 图刷新

### Phase 6（3:25–3:50）文档 + 整合报告 ★ 高 ROI

并行写：

1. **`docs/Agent架构说明.md`**（D 维度核心）：
   - 架构总览（mermaid 图）
   - **Hybrid Function-Agent 设计决策论证**（核心卖点）
   - 数据流与调用链路
   - RAG Pipeline 设计（含分块/混合检索/RRF/prompt 约束）
   - Prompt 工程（4 类模板 + few-shot）
   - 已知局限与改进
   - 创新点（对应 F 维度）

2. **`docs/需求分析.md`**：颗粒度 / 重复判定四要素 / 30% 压缩计算口径 / RAG 分块依据 / 教学完整性

3. **`docs/系统设计.md`**：分层架构图 + 技术选型表 + API 一览（FastAPI `/docs` 截图）

4. **`README.md`**：依赖 / 安装 / 配置 / 启动 / 部署 / 截图

5. **`report/整合报告.md`**：跑完 7 本教材后填真实数据

6. **`docs/P2-技术报告.md`** 或飞书文档（如有时间）：4 组对比实验结果

### Phase 7（3:50–4:00）部署验证 + 提交

1. 前端 `npm run build` → `src/backend/static/`
2. push 到 GitHub → 触发魔搭重 build
3. 端到端冒烟测试：
   - [ ] 公网 URL 可打开
   - [ ] 上传 / 解析 7 本教材成功（02 体积最大时至少完成冒烟解析）
   - [ ] 为 7 本教材构建图谱；若 API 限流，启用 ModelScope 外部 provider 或启发式兜底抽取
   - [ ] 图谱渲染、点击有详情，并能区分 7 本教材来源
   - [ ] 触发 7 本教材整合，压缩比 ≤ 30%
   - [ ] RAG 提问获得带引用回答
   - [ ] 对话能改决策
4. README 加部署链接 + 截图
5. `git commit -am "final" && git push`

---

## 第 4 部分 · 文件结构

```
ai-hackathon-knowledge-agent/
├── 赛题文档.pdf               # 不上传 GitHub
├── textbooks.zip              # 不上传 GitHub
├── PLAN-v2.md                 # 本文件，作为开发参考
├── README.md                  # 项目说明（必交）
├── .gitignore
├── .env.example               # DEEPSEEK_API_KEY=...
├── Dockerfile                 # multi-stage build
├── requirements.txt
├── src/
│   ├── backend/
│   │   ├── main.py            # FastAPI app + StaticFiles mount
│   │   ├── init.sql
│   │   ├── models/schemas.py
│   │   ├── routers/{parse,graph,integrate,rag,chat}.py
│   │   ├── services/
│   │   │   ├── parser.py      # PDF/MD/TXT/DOCX → Markdown
│   │   │   ├── llm.py         # DeepSeek client
│   │   │   ├── embedder.py    # BGE-small-zh
│   │   │   ├── extractor.py   # 知识点抽取
│   │   │   ├── aligner.py     # 双重对齐
│   │   │   ├── integrator.py  # 整合 Agent
│   │   │   ├── chunker.py     # Markdown-aware 切块
│   │   │   ├── index.py       # Chroma + BM25
│   │   │   ├── retriever.py   # 混合检索 + RRF
│   │   │   ├── answerer.py    # RAG 生成
│   │   │   └── dialog_agent.py # 对话 Agent
│   │   ├── benchmark/
│   │   │   ├── eval_set.jsonl
│   │   │   └── run.py
│   │   └── static/            # 前端 build 产物
│   └── frontend/
│       ├── package.json
│       ├── vite.config.ts
│       └── src/
│           ├── App.tsx
│           └── components/{UploadPanel,GraphView,RagPanel,ChatPanel,IntegratePanel}.tsx
├── docs/
│   ├── 需求分析.md
│   ├── 系统设计.md
│   ├── Agent架构说明.md       # ★ 评分核心
│   └── P2-技术报告.md         # 选做
├── report/
│   ├── 整合报告.md
│   └── 精华教材.md            # 30% 压缩产物
└── data/                      # gitignore
    ├── textbooks/
    ├── db/
    ├── index/
    └── models/
```

---

## 第 5 部分 · 风险与降级（按时间紧张度依次砍）

| 优先级 | 模块 | 降级方案 |
|--------|------|----------|
| 1 | DOCX/Excel 解析 | 只支持 PDF/MD/TXT |
| 2 | BGE Reranker | 跳过，保留 RRF |
| 3 | Agentic RAG | 退化为普通 RAG |
| 4 | 双图对比可视化 | 单图 + 频次映射 |
| 5 | SSE 实时推送 | 改 5s polling |
| 6 | P2 飞书报告 | 不做（不影响 100 分基线） |
| 7 | 对话 Agent function calling | 退化为前端按钮直接 PATCH 决策 |

**绝对不可砍**：
- ❌ 任何 P0 完全缺失
- ❌ `docs/Agent架构说明.md`（D 维度 20 分）
- ❌ 公网部署链接（缺失 = 未完成）
- ❌ GitHub 公开仓库链接

---

## 第 6 部分 · Phase 0 执行清单（即将开始）

按用户需求顺序：

1. **本地脚手架**：
   - [ ] 验证 python3.10+/node18+/git/gh
   - [ ] requirements.txt
   - [ ] FastAPI minimal `main.py`（`/api/health`）
   - [ ] Vite + React + TS（`npm create`）
   - [ ] Tailwind 配好
   - [ ] `.gitignore`
   - [ ] 本地双端跑通（前端 dev server fetch 后端 health）

2. **本地 → 公网回路**：
   - [ ] Dockerfile（前端 build + 后端 + StaticFiles mount）
   - [ ] 本地 `docker build && docker run` 验证

3. **GitHub 仓库**：
   - [ ] `git init` + 首次 commit
   - [ ] `gh repo create` Public
   - [ ] push

4. **魔搭部署**：
   - [ ] 用户在 modelscope.cn 创建 Studio（Docker SDK）
   - [ ] README 头部加 ModelScope YAML metadata（sdk: docker）
   - [ ] 关联 GitHub 仓库或 push 到 ModelScope Git
   - [ ] 配置 Secrets（DEEPSEEK_API_KEY）
   - [ ] 等待构建完成 → 公网 URL 可访问

---

## 第 7 部分 · 评分预测（v2 修订）

| 维度 | 满分 | v1 预期 | **v2 预期** | 改善点 |
|------|------|---------|------------|--------|
| A 文档 | 15 | 13–14 | **14** | 同 |
| B 功能 | 25 | 21–23 | **22–24** | 整合方案更扎实 + benchmark 数据 |
| C 可视化 | 13 | 9–11 | **10–11** | 同 |
| D 架构 | 20 | 16–18 | **18–19** | Hybrid Function-Agent 论证更深 + 实验数据 |
| E 代码 | 17 | 13–15 | **14–15** | 同 |
| F 创新 | 10 | 5–7 | **6–8** | benchmark + 选择式压缩 + 引用真实可点击 |
| **小计** | 100 | 77–88 | **84–91** | — |
| P2 附加 | +15 | 0–3 | **+5~8** | 多组对比实验背书 |
| **总计** | 115 | 77–91 | **89–99** | — |

---

**END · 开始 Phase 0**
