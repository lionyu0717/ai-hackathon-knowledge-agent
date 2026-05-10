# AI 全栈极速黑客松 · 5h 最佳得分实现方案

## Context

**赛题**：浙江大学未来学习中心 · AI 生态 2026.5 主办的「学科知识整合智能体」开发，5 小时内交付一个 Web 应用：解析 7 本教材 → 构建可视化知识图谱 → 跨教材去重压缩到 ≤30% → 带引用的 RAG 问答 → 多轮对话迭代 → 完整文档 → 公网部署。

**评分**：100 分（满分）+ P2 附加分。六个维度：A 文档(15) / B 功能(25) / C 可视化(13) / D Agent 架构(20) / E 代码质量(17) / F 创新(10)。

**目标**：在 5 小时内拿到 80–88 分，把时间投在评分权重最高（B 功能 + D 架构 + E 代码）且最容易踩分点的路径上。本计划同时回答你提出的四个核心难点：知识颗粒度、重复判定、30% 压缩、RAG 排序。

---

## 一、赛题任务拆解（10 项 P0 必做）

| # | 任务 | 评分大头 | 难度 | 核心交付 |
|---|------|---------|-----|---------|
| 1 | 多格式解析（PDF/MD/TXT/DOCX） | B(2+1) | 低 | 统一 schema 的 Textbook JSON |
| 2 | 单本知识图谱抽取 | B(4+1) | 中 | LLM few-shot + 节点/边 schema |
| 3 | 图谱可视化交互 | C(13) | 中 | ECharts 力导向图 + 频次映射 |
| 4 | **跨教材整合（核心难点）** | B(5+1) | **高** | 双重对齐 + Union-Find 聚类 + 压缩控制 |
| 5 | **RAG 问答 pipeline** | B(4+1) | **高** | 混合检索 + 引用约束 prompt |
| 6 | Agent 架构说明文档 | D(20) | 中 | **本场最大分项**，必须深度论证 |
| 7 | 多轮对话迭代整合 | B(2+1) | 中 | Function calling 改决策 |
| 8 | Web SPA 界面 | C 间接 | 中 | 三栏布局 + Tab 切换 |
| 9 | 整合报告（基于 7 本教材） | A(2+1) | 低 | 跑出真实数据填模板 |
| 10 | 完整开发文档（README + 需求 + 设计 + Agent） | A(15) | 低 | 模板化输出 |

---

## 二、四个核心难点的判断

### 难点 1：知识点颗粒度如何定义

**判断**：采用「原子概念」标准，而非「话题」或「段落」。

| 维度 | 标准 |
|------|------|
| 名称 | 单一名词短语（2–10 字），可被「什么是 X？」独立提问 |
| 定义 | 1–3 句话，可独立成段 |
| 数量约束 | 每章 5–15 个（在 prompt 里强制） |
| 反例 | ❌「排序算法」（太大）✅「快速排序」「归并排序」 |
| 反例 | ❌「2.3 节内容」（不是概念）✅「动作电位的产生机制」 |

**理由**：
- 颗粒度太粗 → 跨教材去重失败（每本都"全有"）
- 颗粒度太细 → 节点爆炸 + LLM 抽取不稳定
- 5–15/章 × 平均 20 章 × 7 本 ≈ 700–2100 节点，可视化和聚类都可控

**Prompt 强约束**：
```
每个知识点必须满足：
1. 名称是 2-10 字的名词短语
2. 可独立回答"什么是X？"
3. 每章产出 5-15 个，按重要度排序
拒绝输出："本章简介"、"复习题"、章节号本身
```

---

### 难点 2：重复判定标准

**判断**：双阶段对齐，embedding 召回 + LLM 精判，用 Union-Find 做传递聚类。

| 阶段 | 方法 | 阈值 | 目的 |
|------|------|------|------|
| Stage 1 召回 | BGE-small-zh embed(name+definition) 余弦相似度 | ≥ 0.82 | 快速圈出候选对，剔除 99% 无关组合 |
| Stage 2 精判 | LLM 批判（5 对/次），输出 {同一概念/相关/无关} | confidence ≥ 0.8 才合并 | 防止「白细胞 vs 红细胞」这种高 sim 但语义相反的误合 |
| Stage 3 聚类 | Union-Find 把所有判定为「同一」的节点并入同一簇 | — | 处理传递性：A=B 且 B=C → A=C |

**判定四要素**（写入 Stage 2 prompt）：
1. **指称同一对象**（如 "leukocyte" / "白细胞" / "白血球"）
2. **核心定义重叠 ≥ 70%**
3. **学科范畴一致**（同在「细胞免疫」而非一个在「化学」一个在「生理」）
4. **抽象层级一致**（"免疫系统" ≠ "T细胞"，前者 contains 后者）

**为什么不只用 embedding**：单纯 cos_sim 高的常见误判：
- 反义词（"激活" vs "抑制"）
- 上下位（"细胞" vs "神经细胞"）
- 共现概念（"动作电位" vs "静息电位"）

LLM 精判能解决以上三类错误，且每次比赛实际候选对预计 < 2000 对，批 5 对/次 = 400 次 LLM 调用，DeepSeek 价格可控。

---

### 难点 3：30% 压缩比怎么实现

**判断**：不是删原文 70%，而是「按知识点产出精华条目 + 严格预算控制」。

**计算口径**（写入需求分析文档）：
```
原始总字数 = Σ (每本教材的正文 char_count)
压缩后总字数 = Σ (每个保留的精华条目正文字数 + 引用元数据)
压缩比 = 压缩后 / 原始 × 100%
目标：≤ 30%（实际预算 28%，留 2% 缓冲）
```

**两步压缩流程**：

**第一步：决策层（删除 + 合并）**
- merge：同一簇内 N 个节点 → 1 个 canonical 节点
- keep：簇大小=1 的独有知识点 → 保留
- remove：低重要度 + 全文出现频次 < 2 + 不被任何其他节点 prerequisite/contains → 直接删除

**第二步：内容层（精华改写）**
对每个保留节点，让 LLM 基于该节点对应的所有原文 chunk 生成「精华条目」：
```
输入：N 段来自不同教材的相关原文（合计可能 3000+ 字）
输出：300-500 字的精华条目，包含：
  - 名称
  - 综合定义（融合各教材最准确的表述）
  - 关键性质 / 公式 / 例子（最多 3 条）
  - 引用：[教材名, 章节, 页码] × 2-3
```

**预算控制算法**（关键）：
```python
budget = original_total * 0.28
items = sorted(merged_nodes, key=importance_score, reverse=True)
result = []
used = 0
for item in items:
    essence = llm_compress(item)  # ~400 chars
    if used + len(essence) <= budget:
        result.append(essence); used += len(essence)
    else:
        item.action = "remove"; item.reason = "压缩预算溢出，按重要度截断"
```

**重要度打分**：`freq_across_books × 0.4 + degree_in_graph × 0.3 + (1 if has_definition else 0) × 0.3`

---

### 难点 4：RAG 整合与排序方案

**判断**：分块 600/100 + 混合检索（向量 + BM25）+ RRF 融合 + 严格引用约束 prompt。可选 rerank。

**Pipeline 设计**：

```
查询 q
  ├─ 向量检索（BGE-small-zh + ChromaDB）→ top-20
  └─ BM25（jieba 分词 + rank_bm25）→ top-20
       ↓ RRF 融合（k=60）
       top-10
       ↓ （可选）BGE-reranker-base cross-encoder
       top-5
       ↓ 注入 prompt + 严格引用约束
       LLM 生成回答 + citations
```

**分块策略**（写需求分析）：

| 参数 | 选择 | 理由 |
|------|------|------|
| chunk_size | 600 字 | BGE-zh 在 300-1000 字效果最佳；600 平衡上下文与语义聚焦 |
| overlap | 100 字 | 防止跨块知识截断（一段定义 + 例子常 100+ 字） |
| 切分边界 | 中文句号/问号/感叹号优先，其次换行，最后强切 | 避免句子被劈成两半 |
| 元数据 | textbook_id, chapter_id, chapter_title, page_start, page_end | 引用必备 |

**为什么混合检索**：
- 纯向量：对专有名词、缩写、化学式、罕见术语召回差
- 纯 BM25：对同义改写、概念性提问召回差
- RRF 融合：免参数（不需调权重），鲁棒，常见 RAG 论文 baseline

**生成 prompt 关键约束**（防幻觉）：
```
你只能基于以下上下文回答。
每个事实陈述后必须附 [教材名, 第X章, 第X页]。
如上下文不足以回答：必须回复"当前知识库中未找到相关信息"。
不要使用你的内部知识补全。
```

**自建 Benchmark（P2 加分高 ROI）**：
若有时间，让 LLM 基于 7 本教材生成 30 道测试题（事实/比较/推理/跨教材各 7-8 题），跑 chunk_size ∈ {300, 600, 1000} × {纯向量, 混合} × {有/无 rerank} 的 6 组对比，写入 P2 报告。

---

## 三、技术选型判断

| 层级 | 选型 | 替代 | 选择理由 |
|------|------|------|----------|
| 后端 | **FastAPI + uvicorn** | Flask | 自动 OpenAPI doc（系统设计文档可直接截图）、async 原生、5h 内成熟 |
| 前端 | **React + Vite + TypeScript + TailwindCSS + shadcn/ui** | Vue3 | shadcn 组件复制即用，AI 编码工具支持最好 |
| 图谱可视化 | **ECharts relation graph** | D3.js / G6 | 配置式 API，免学习曲线；力导向 + 缩放 + 拖拽 + 点击全开箱 |
| LLM | **DeepSeek-V3 API**（OpenAI 兼容） | Qwen / Claude | 中文最佳价格比；JSON mode 稳定；rate limit 宽松 |
| Embedding | **BGE-small-zh-v1.5（本地 sentence-transformers）** | OpenAI / BGE-large | 100MB 模型，CPU 几百 ms/句，免 API 延迟和费用 |
| 向量库 | **ChromaDB（持久化磁盘）** | FAISS / Qdrant | 内嵌 Python，零部署，支持 metadata 过滤 |
| 分词（BM25） | **jieba + rank_bm25** | — | 中文分词标准答案 |
| Rerank（可选） | **BGE-reranker-base** | — | 仅在剩 30+ min 时启用 |
| Agent 框架 | **不用**，手动编排 | LangGraph / CrewAI | 5h 内学习成本 > 收益；模块化函数调用更可控；论证为主动设计决策 |
| PDF 解析 | **PyMuPDF (fitz)** | PyPDF2 / pdfplumber | 速度最快、布局信息最全（字号识别章节标题） |
| DOCX/MD | **python-docx + markdown-it-py** | — | 标准库 |
| 数据库 | **SQLite（标准库）** | Postgres | 零配置，单文件，足够 |
| 部署 | **HuggingFace Spaces（Docker SDK）** 或 **魔搭创空间** | Vercel+Railway | 单容器跑 FastAPI（前端 build 后 mount static），免费、稳定、公网域名 |
| 容器化 | **单 Dockerfile** | docker-compose | 单服务无需 compose；E 维度进阶分仍能拿到 |

**关键反向选型**（写入 Agent 架构文档「取舍与权衡」章节）：
- ❌ **不用 LangChain/LangGraph**：抽象层学习成本高，5h 内调试 callback/state 不划算
- ❌ **不用 GraphRAG / Neo4j**：图谱仅用于可视化展示，RAG 走传统向量检索
- ❌ **不用 OpenAI Embedding**：国内网络 + 计费 + 延迟，本地 BGE 完全够用
- ❌ **前后端不分离部署**：FastAPI 直接 serve 前端 build 产物，单容器部署

---

## 四、5h 最佳得分时间分配

总预算 300 分钟。**策略**：先把所有 P0 跑通（即使简陋），再迭代补深度。**严禁**在某一项上过度投入导致最后没部署。

```
时间轴：
0:00 ─── 0:25  Phase 0  脚手架与部署回路    (25min)
0:25 ─── 1:00  Phase 1  解析 + 数据模型      (35min)
1:00 ─── 1:50  Phase 2  抽取 + 单本图谱      (50min)
1:50 ─── 2:50  Phase 3  跨教材整合           (60min)  ★ 核心
2:50 ─── 3:40  Phase 4  RAG pipeline         (50min)  ★ 核心
3:40 ─── 4:10  Phase 5  对话迭代 + UI 收尾   (30min)
4:10 ─── 4:40  Phase 6  四份文档 + 整合报告  (30min)  ★ 高 ROI
4:40 ─── 5:00  Phase 7  部署 + 端到端验证   (20min)
```

---

## 五、Phase 拆解（每一步可独立执行）

### Phase 0（0:00–0:25）脚手架 + 部署回路

**关键原则**：先打通「本地代码 → 部署平台 → 公网访问」回路，避免最后 30 分钟踩坑。

1. `mkdir hackathon && cd hackathon && git init`
2. 创建目录结构：
   ```
   src/backend/   # FastAPI app
     main.py
     routers/{parse,graph,integrate,rag,chat}.py
     services/{llm,embed,store}.py
     models/schemas.py
   src/frontend/  # Vite + React + TS
     src/components/{UploadPanel,GraphView,RagPanel,ChatPanel}.tsx
   docs/
   report/
   data/{textbooks,db,index}/  # gitignore
   .gitignore  Dockerfile  README.md  requirements.txt
   ```
3. `.gitignore` 排除 `*.pdf data/ .env node_modules/ __pycache__/`
4. `requirements.txt`：fastapi, uvicorn, pydantic, pymupdf, python-docx, markdown-it-py, sentence-transformers, chromadb, rank-bm25, jieba, openai (DeepSeek-compatible), python-multipart
5. 写最简 main.py：3 个 stub 接口（`/api/health`, `/api/upload`, `/api/query`），CORS 全开
6. `npm create vite@latest frontend -- --template react-ts`，装 tailwind + shadcn/ui
7. **打通部署**：写 Dockerfile（multi-stage：build 前端 → copy 到 backend/static → uvicorn serve），push 到 HuggingFace Spaces，确认公网链接能打开 health check
8. **验证**：浏览器访问公网 URL 能看到 React 默认页和 `/api/health` 返回 200

**得分映射**：E 部署配置基础分锁定（+2），A README 框架就位

---

### Phase 1（0:25–1:00）解析 + 数据模型

1. `models/schemas.py`：定义 `Textbook`, `Chapter`, `KnowledgeNode`, `KnowledgeEdge`, `Chunk` 的 Pydantic 模型
2. `services/parser.py`：
   - `parse_pdf(path)`：PyMuPDF 逐页提取文本 + 字号信息；正则 `r'第[一二三四五六七八九十百\d]+章'` 识别章节起始；过滤页眉页脚（首尾 50px y 区域）
   - `parse_md(path)`：markdown-it 按 H1/H2 切章节
   - `parse_txt(path)`：按 `\n第X章` 分割
   - `parse_docx(path)`：python-docx 按 Heading 1 切
3. `routers/parse.py`：
   - `POST /api/upload`（multipart 多文件）→ 异步任务，返回 task_id
   - `GET /api/textbooks` → 列表
   - `GET /api/textbooks/{id}/chapters` → 章节
4. SQLite 持久化（`sqlite3` 标准库 + 一个 init.sql）
5. 前端 `UploadPanel.tsx`：拖拽上传（react-dropzone）+ 文件列表 + 解析状态 polling
6. **本地验证**：上传 1 本教材，看到章节列表正确

**得分映射**：B(1)(2/1) 基础分

---

### Phase 2（1:00–1:50）知识抽取 + 单本图谱

1. `services/llm.py`：DeepSeek client（OpenAI SDK 改 base_url），封装 `chat_json(prompt, system, temperature=0.1)` 强制 JSON
2. `services/extractor.py`：
   ```
   prompt = """
   你是教育领域专家。从下面章节内容中提取 5-15 个核心知识点。
   每个知识点是 2-10 字的原子名词短语。
   同时识别知识点之间的关系（prerequisite/parallel/contains/applies_to）。
   严格输出 JSON：{"nodes":[{"name","definition","category"}], "edges":[{"source","target","relation_type","description"}]}
   章节：{chapter.content}
   """
   ```
   附 1 个 few-shot 示例
3. `asyncio.gather` 并发抽取所有章节（限速 5 并发）
4. 节点 ID 生成：`f"{textbook_id}_{chapter_id}_{md5(name)[:6]}"`
5. 入库 + 缓存（key = chapter content hash，避免重跑烧 token）
6. 前端 `GraphView.tsx`：ECharts relation graph
   - `categories` = 教材列表（颜色区分）
   - `symbolSize` = 节点频次（初始 = 1，整合后会更新）
   - `force.repulsion` = 100，`edgeLength` = 80
   - 点击事件 → 右侧 drawer 显示节点详情（来自 API）
7. 添加缩放、拖拽、节点移动（ECharts 默认即支持，开启 `roam: true, draggable: true`）
8. **本地验证**：上传 1 本教材 → 看到节点+边的力导向图

**得分映射**：B(2/4)(3/3) 基础 + C(3+3) 基础

---

### Phase 3（1:50–2:50）跨教材整合 ★

**这是评分最重的功能模块（B 5+1，且决定 D 架构论证质量）**

1. `services/embedder.py`：sentence-transformers 加载 BGE-small-zh-v1.5（首次启动下载 ~100MB，缓存到 `data/models/`）
2. `services/aligner.py`：
   - **Stage 1 召回**：对所有节点 embed `name + " " + definition[:200]`，构建 sim 矩阵（节点数 < 2000，纯 numpy 即可）；提取 cos_sim ≥ 0.82 的对
   - **Stage 2 LLM 精判**：
     ```
     prompt = """
     判断下列知识点对是否指代同一个概念。
     四要素：指称对象/定义重叠/学科范畴/抽象层级。
     输出 JSON：[{"pair_id":..., "verdict":"same|related|different", "confidence":0-1, "reason":"..."}]
     """
     ```
     批 5 对/次调用，并发
   - **Stage 3 Union-Find**：把所有 verdict=same & confidence≥0.8 的对合并成簇
3. `services/integrator.py`：
   - 对每簇生成 canonical 节点：
     ```
     prompt = """
     以下是来自多本教材的关于同一概念的描述。
     综合生成一个 300-500 字的精华条目，包含：综合定义、关键性质（最多3条）、引用列表。
     必须保留来源标注 [教材名, 章节, 页码]。
     """
     ```
   - 簇大小=1：直接保留
   - 计算 importance：`freq × 0.4 + graph_degree × 0.3 + has_definition × 0.3`
   - **预算截断**：按 importance 排序，累加 essence 字数 ≤ `0.28 × original_total`，超出部分标 remove
4. 输出决策列表：`[{decision_id, action, affected_nodes, result_node, reason, confidence}]`
5. `routers/integrate.py`：
   - `POST /api/integrate/run` → 触发整合
   - `GET /api/integrate/decisions` → 决策列表
   - `GET /api/integrate/stats` → {original_chars, merged_chars, ratio}
6. 前端：
   - 整合后图谱：节点 size 用 frequency 重新映射；不同来源用 categories
   - Tab「整合操作」面板：显示压缩比统计 + 决策列表（每条带 reason 和 confidence）
   - 「视图切换」按钮：原图 / 整合后图（加分项预备）
7. **本地验证**：上传 2 本以上教材 → 触发整合 → 压缩比 ≤ 30%

**得分映射**：B(4/5+1) 基础 + 进阶（双重对齐 + 可视化对比）

---

### Phase 4（2:50–3:40）RAG Pipeline ★

1. `services/chunker.py`：
   - 按句号切句 → 拼成 ≤600 字块 → 块间 100 字 overlap
   - 每个 chunk 元数据：`{chunk_id, textbook_id, textbook_title, chapter_id, chapter_title, page_start, page_end}`
2. `services/index.py`：
   - 全部 chunks → BGE 向量化 → 写入 ChromaDB（持久化到 `data/index/chroma/`）
   - 同时构建 BM25 索引：`tokens = jieba.lcut(chunk.text)`，`BM25Okapi(corpus_tokens)`，pickle 持久化
3. `services/retriever.py`：
   - `vector_search(q, k=20)` → ChromaDB
   - `bm25_search(q, k=20)` → rank_bm25
   - `rrf_fuse(results_a, results_b, k=60)` → top-10
   - （可选）`rerank(q, top10) → top-5`，用 BGE-reranker-base
4. `services/answerer.py`：
   ```
   system = """你只能基于上下文回答。每个事实陈述后必须附 [教材, 章, 页]。
   如上下文不足，必须回复'当前知识库中未找到相关信息'。"""
   user = "上下文：\n[1] ...\n[2] ...\n\n问题：{q}"
   → DeepSeek，temperature=0.1
   ```
   返回 `{answer, citations[], source_chunks[]}`
5. `routers/rag.py`：
   - `POST /api/rag/index` → 构建索引（异步，返回进度）
   - `POST /api/rag/query` → {answer, citations, source_chunks}
   - `GET /api/rag/status` → {indexed_books, chunk_count, last_indexed_at}
6. 前端 `RagPanel.tsx`：
   - 顶部状态条「已索引 X 本教材，共 Y 个块」
   - 输入框 + 提交
   - 回答区：正文 + 引用卡片（教材名、章节、页码、relevance_score）+ 点击展开原文
7. **本地验证**：问 3 个不同类型的问题，检查引用准确

**得分映射**：B(5/4+1) 基础 + 进阶（混合检索）；为 P2 报告打底

---

### Phase 5（3:40–4:10）多轮对话 + UI 收尾

1. `routers/chat.py`：
   - `POST /api/chat` → {session_id, message, history}
   - LLM 函数调用，工具列表：
     - `explain_decision(decision_id)` → 返回理由
     - `modify_decision(decision_id, new_action, reason)` → 改决策 + 通知前端刷新图
     - `query_rag(question)` → 内部走 RAG
2. 会话历史存 SQLite（session_id, role, content, ts）
3. 前端 `ChatPanel.tsx`：聊天泡泡 UI + 输入框 + 历史持久化（localStorage 兜底）
4. 决策修改后通过 SSE / 简单轮询刷新图谱
5. **三栏布局收尾**：左 UploadPanel | 中 GraphView（最大）| 右 Tabs（整合/RAG/对话/报告）
6. 顶部加搜索框：输入关键词高亮匹配节点（ECharts 自带 `dispatchAction({type:'highlight'})`）
7. **本地验证**：教师提问 → 改决策 → 图谱更新

**得分映射**：B(2/2+1) 进阶 + C(1/1) 进阶（搜索）

---

### Phase 6（4:10–4:40）文档 + 整合报告 ★ 高 ROI

**这是 5h 比赛中性价比最高的 30 分钟，能稳拿 A(15) + 大部分 D(20)。**

并行写四份：

1. **`docs/Agent架构说明.md`（最关键，对应 D 维度 20 分）**
   - § 架构总览：mermaid 图（解析→抽取→整合→RAG→对话）
   - § 设计决策论证：
     - 为什么单 Agent + 模块化函数（vs 多 Agent 框架）
     - 为什么手动编排（vs LangGraph）
     - 为什么 BGE 本地 + DeepSeek 云端混合
   - § 数据流与调用链路：完整一次「上传 → 问答」trace
   - § RAG Pipeline 设计：分块依据、混合检索、RRF 公式、prompt 约束
   - § Prompt 工程：抽取/对齐/精华/回答四类 prompt 模板 + few-shot
   - § 已知局限与改进：列 5 条具体局限 + 每条改进方向
   - § 创新点说明（对应 F 维度）

2. **`docs/需求分析.md`**：知识颗粒度 / 重复判定四要素 / 30% 压缩计算口径 / RAG 分块依据 / 教学完整性保障

3. **`docs/系统设计.md`**：分层架构图 + 技术选型表 + API 一览（直接 copy FastAPI `/docs` 的 OpenAPI）+ 请求示例

4. **`README.md`**：环境依赖 / 安装 / 配置（.env.example）/ 启动 / 部署 / 截图

5. **`report/整合报告.md`**：跑完 7 本教材后填真实数据：原始字数 / 压缩后字数 / 压缩比 / 决策摘要 / 节点变化 / 5 个典型整合案例 / 教学完整性分析

**模板化技巧**：本文件本身可作为框架，开赛后直接复制粘贴到对应文档，把数字补上即可。

---

### Phase 7（4:40–5:00）部署 + 端到端验证

1. 前端 `npm run build` → 输出到 `src/backend/static/`
2. FastAPI 加 `app.mount("/", StaticFiles(directory="static", html=True))`
3. Dockerfile 重新 build & push HF Spaces
4. 等 Spaces 重启完成
5. **端到端冒烟测试**：
   - [ ] 公网 URL 可打开
   - [ ] 上传 2 本教材成功
   - [ ] 图谱可视化渲染、点击有详情
   - [ ] 触发整合，看到压缩比
   - [ ] RAG 提问获得带引用回答
   - [ ] 多轮对话能改决策
6. README 最终更新部署链接
7. `git commit -am "final" && git push`，确认最后一次 commit 时间在截止前

---

## 六、风险与降级策略

按时间紧张程度依次砍：

| 优先级 | 模块 | 降级方案 |
|--------|------|----------|
| 1 | DOCX/Excel 解析 | 只支持 PDF/MD/TXT，文档说明「时间限制下未实现」 |
| 2 | BGE Reranker | 跳过，保留 RRF 融合即可 |
| 3 | Function calling 改决策 | 降级为前端「编辑/删除决策」按钮直接调 API |
| 4 | 双图对比可视化 | 单图 + 频次映射 |
| 5 | SSE 实时推送 | 改用前端 5s polling |
| 6 | Docker 部署 | 直接用 HF Spaces 的原生 Python SDK |
| 7 | P2 技术报告 | 不做（不影响 100 分基线） |

**绝对不可砍**：
- 任意一项 P0 完全缺失（直接影响 B 维度多分）
- Agent 架构说明文档（D 维度 20 分）
- 公网部署链接（缺失 = 未完成 = 不进评审）

---

## 七、得分预测

| 维度 | 满分 | 预期 | 关键动作 |
|------|------|------|----------|
| A 文档 | 15 | 13–14 | Phase 6 模板化输出，所有进阶分（Docker / RAG 依据 / API 示例 / 教学完整性）锁定 |
| B 功能 | 25 | 21–23 | 全 P0 完成 + 双重对齐 + 混合检索两个进阶 |
| C 可视化 | 13 | 9–11 | 力导向 + 频次 + 颜色 + 缩放拖拽 + 搜索；多视图切换若有时间 +5 |
| D 架构 | 20 | 16–18 | Agent 文档深度论证，含 mermaid + 取舍分析 + 已知局限 |
| E 代码 | 17 | 13–15 | 模块化清晰 + 类型注解 + .env.example + Dockerfile |
| F 创新 | 10 | 5–7 | Token 统计 + 自建 mini benchmark + 决策可解释 UI |
| **合计** | **100** | **77–88** | — |

P2 附加分若有 30+ 分钟可写一份 RAG 分块对比迷你实验，再 +3~5。

---

## 八、待对齐的关键问题

在开始动手前，需要你确认或提供：

1. **LLM API 凭证**：DeepSeek API key 已就绪？（无 key 需替换 prompt 至 Qwen / 通义）
2. **教材语料类型**：是否已知是哪个学科？（生理/病理类教材正则识别章节最稳，CS 教材可能是 markdown）
3. **部署平台**：HuggingFace Spaces vs 魔搭创空间，是否已注册账号？
4. **是否需要 P2 技术报告**：愿意加 30 分钟做迷你 RAG benchmark 吗？

---

## 九、关键文件清单（实施时直接照抄路径）

需要新建的文件（共 ~30 个）：
- `Dockerfile`, `requirements.txt`, `.gitignore`, `.env.example`, `README.md`
- `src/backend/main.py`, `src/backend/init.sql`
- `src/backend/models/schemas.py`
- `src/backend/services/{parser,llm,embedder,extractor,aligner,integrator,chunker,index,retriever,answerer}.py`
- `src/backend/routers/{parse,graph,integrate,rag,chat}.py`
- `src/frontend/src/App.tsx`, `src/frontend/src/components/{UploadPanel,GraphView,RagPanel,ChatPanel,IntegratePanel}.tsx`
- `docs/{需求分析,系统设计,Agent架构说明}.md`
- `report/整合报告.md`

参考实现可复用：
- ECharts 关系图官方示例：https://echarts.apache.org/examples/zh/editor.html?c=graph-force
- BGE-small-zh：sentence-transformers `BAAI/bge-small-zh-v1.5`
- DeepSeek OpenAI 兼容 base_url：`https://api.deepseek.com/v1`
- HF Spaces Docker 模板：直接 push Dockerfile 即可

---

## 十、验证计划

**功能验证**（每个 Phase 末尾）：参见各 Phase 内的「本地验证」清单。

**端到端验证**（Phase 7）：上传 2 本教材 → 等抽取完成 → 触发整合 → 看压缩比 ≤30% → RAG 提 1 个跨教材问题 → 检查引用 → 在对话里说「不要合并 X 和 Y」→ 看图更新。

**评审视角自检**：
- 评委拉仓库 → README → `docker compose up` 或 `pip install -r && uvicorn` → 能起服务
- 公网链接 → 浏览器全功能可用
- `docs/Agent架构说明.md` 单独打开可读，逻辑自洽
- `report/整合报告.md` 数据真实

---

**总结**：本方案的核心逻辑是「**先打通端到端最小回路（Phase 0+1+2 跑出 1 本教材的图）→ 再深挖核心难点（Phase 3+4 整合与 RAG）→ 最后用文档把 D/A 维度的分稳稳锁住**」。每个 Phase 都有明确的本地验证checkpoint，避免最后整合时炸雷。
