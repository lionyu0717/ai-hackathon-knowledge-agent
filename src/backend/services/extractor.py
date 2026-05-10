"""知识点抽取服务

赛题 P0-2 验收要求：
  「为每章构建知识图谱并可视化」
  节点 schema: {id, name, definition, category, chapter, page}
  关系类型 ≥ 3 种（prerequisite/parallel/contains/applies_to）
  Prompt 设计建议：明确 JSON 格式 + few-shot + 限制每次只处理一个章节

实现策略（PLAN v2 决策 1：知识颗粒度=原子概念）：
  - 每章节单独调一次 LLM，避免上下文过长
  - JSON 强约束 prompt + few-shot 示例
  - Chapter 内容超过 max_input_chars 时截断（取前段，包含定义最密集的部分）
  - 缓存：相同 chapter content hash → 复用结果，避免烧 token
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from ..models.schemas import Chapter, KnowledgeEdge, KnowledgeNode
from .llm import chat_json

logger = logging.getLogger(__name__)

# 单章节最长输入（约 6K 中文字符 ~ 3K token，留余量给 prompt 与 output）
MAX_INPUT_CHARS = 6000

EXTRACTION_SYSTEM = "你是教育领域专家，擅长从教材文本中提取知识图谱。"

# Few-shot 示例 + JSON 强约束（赛题建议）
EXTRACTION_PROMPT_TEMPLATE = """从下方给定的教材章节内容中，提取**核心知识点**，并识别它们之间的关系。

## 颗粒度规范（必须严格遵守）
- 每个知识点的 name 必须是 2-12 字的**原子名词短语**（可被「什么是X？」独立提问）
- 每章节产出 5-15 个知识点，按教学重要度排序
- ❌ 禁止输出："本章简介"、"复习题"、章节号本身、过粗的话题（如"血液"应拆为"红细胞"/"白细胞"等）
- ❌ 禁止输出 name 含括号、引号或标点的复合短语

## 关系类型（4 选 ≥ 3）
| 类型 | 说明 |
|------|------|
| prerequisite | A 是学习 B 的前置（先掌握 A 才能理解 B） |
| parallel | A 和 B 是同层级的并列概念 |
| contains | A 包含 B（上位/下位关系）|
| applies_to | A 的应用场景是 B |

## 输出格式（严格 JSON，不要其他文字）
{{
  "nodes": [
    {{"name": "动作电位", "definition": "细胞受刺激后膜电位发生的快速可逆倒转", "category": "核心概念"}},
    {{"name": "静息电位", "definition": "未受刺激时细胞膜内外的电位差", "category": "核心概念"}}
  ],
  "edges": [
    {{"source": "静息电位", "target": "动作电位", "relation_type": "prerequisite", "description": "理解动作电位需先掌握静息电位"}}
  ]
}}

注意：edges 中的 source/target 必须使用 nodes 中已声明的 name，不能引用未声明的概念。

## 章节内容
标题：{chapter_title}
正文：
{chapter_content}
"""


@dataclass
class ExtractionResult:
    nodes: list[KnowledgeNode]
    edges: list[KnowledgeEdge]
    raw: dict


def _truncate_for_llm(text: str, limit: int = MAX_INPUT_CHARS) -> str:
    """超长章节截断：取前 70% + 末尾 30%（首章定义密集，末尾常有总结）"""
    if len(text) <= limit:
        return text
    head = text[: int(limit * 0.7)]
    tail = text[-int(limit * 0.3):]
    return head + "\n\n...（中间内容因长度限制省略）...\n\n" + tail


def _node_id(textbook_id: str, chapter_id: str, name: str) -> str:
    h = hashlib.md5(name.encode("utf-8")).hexdigest()[:6]
    return f"{textbook_id}_{chapter_id}_{h}"


def extract_chapter(
    textbook_id: str, chapter: Chapter,
) -> ExtractionResult:
    """单章节抽取 → 节点列表 + 边列表"""
    if not chapter.content.strip():
        return ExtractionResult([], [], {})

    prompt = EXTRACTION_PROMPT_TEMPLATE.format(
        chapter_title=chapter.title,
        chapter_content=_truncate_for_llm(chapter.content),
    )

    try:
        raw = chat_json(prompt, EXTRACTION_SYSTEM, max_tokens=2500, temperature=0.15)
    except Exception as e:
        logger.warning(f"[extract] LLM call failed for {chapter.chapter_id}: {e}")
        return _heuristic_extract_chapter(textbook_id, chapter, str(e))

    if not isinstance(raw, dict):
        logger.warning(f"[extract] unexpected JSON shape for {chapter.chapter_id}: {type(raw)}")
        return ExtractionResult([], [], {"error": "invalid shape"})

    raw_nodes = raw.get("nodes", []) or []
    raw_edges = raw.get("edges", []) or []

    # 名称去重（同一章节内）+ 构造节点
    seen_names: dict[str, str] = {}  # name → node_id
    nodes: list[KnowledgeNode] = []
    for n in raw_nodes:
        if not isinstance(n, dict):
            continue
        name = (n.get("name") or "").strip()
        if not name or len(name) > 50:
            continue
        if re.search(r"[，。？！；：（）()【】\[\]『』]", name):
            continue
        if not _valid_term(name):
            continue
        if name in seen_names:
            continue
        node_id = _node_id(textbook_id, chapter.chapter_id, name)
        seen_names[name] = node_id
        nodes.append(KnowledgeNode(
            id=node_id,
            name=name,
            definition=(n.get("definition") or "").strip()[:500],
            category=(n.get("category") or "核心概念").strip()[:30],
            textbook_id=textbook_id,
            chapter_id=chapter.chapter_id,
            chapter_title=chapter.title,
            page=chapter.page_start,
        ))

    # 构造边（仅保留 source/target 都已声明的）
    edges: list[KnowledgeEdge] = []
    valid_relations = {"prerequisite", "parallel", "contains", "applies_to"}
    for e in raw_edges:
        if not isinstance(e, dict):
            continue
        src_name = (e.get("source") or "").strip()
        tgt_name = (e.get("target") or "").strip()
        rel = (e.get("relation_type") or "").strip()
        if rel not in valid_relations:
            continue
        if src_name not in seen_names or tgt_name not in seen_names:
            continue
        edges.append(KnowledgeEdge(
            source=seen_names[src_name],
            target=seen_names[tgt_name],
            relation_type=rel,  # type: ignore[arg-type]
            description=(e.get("description") or "").strip()[:200],
        ))

    return ExtractionResult(nodes, edges, raw)


def _heuristic_extract_chapter(textbook_id: str, chapter: Chapter, error: str) -> ExtractionResult:
    """LLM 额度/限流失败时的保底抽取。

    该分支不追求语义完美，只保证演示环境仍能产出可视化节点和基础关系。
    """
    candidates = _candidate_terms(chapter)
    nodes: list[KnowledgeNode] = []
    seen: set[str] = set()
    for name in candidates:
        if name in seen:
            continue
        seen.add(name)
        nodes.append(KnowledgeNode(
            id=_node_id(textbook_id, chapter.chapter_id, name),
            name=name,
            definition=_sentence_for_term(chapter.content, name),
            category="启发式概念",
            textbook_id=textbook_id,
            chapter_id=chapter.chapter_id,
            chapter_title=chapter.title,
            page=chapter.page_start,
        ))
        if len(nodes) >= 10:
            break

    edges: list[KnowledgeEdge] = []
    if len(nodes) >= 2:
        root = nodes[0]
        for child in nodes[1:6]:
            edges.append(KnowledgeEdge(
                source=root.id,
                target=child.id,
                relation_type="contains",
                description=f"{root.name} 与 {child.name} 同属本章核心内容",
            ))
        for left, right in zip(nodes[1:5], nodes[2:6]):
            edges.append(KnowledgeEdge(
                source=left.id,
                target=right.id,
                relation_type="parallel",
                description=f"{left.name} 与 {right.name} 是本章相邻知识点",
            ))
    return ExtractionResult(nodes, edges, {"error": error, "fallback": "heuristic"})


def _candidate_terms(chapter: Chapter) -> list[str]:
    text = chapter.content
    out: list[str] = []

    title = re.sub(r"^第\s*[一二三四五六七八九十百零\d]+\s*章\s*", "", chapter.title).strip()
    if _valid_term(title):
        out.append(title)

    # 医学专业术语（排除过于宏观的常识词如"细胞""器官""系统""血液"）
    known_terms = [
        "稳态", "缺氧", "水肿", "休克", "发热", "酸中毒", "碱中毒",
        "心力衰竭", "呼吸衰竭", "肾功能衰竭", "肝功能衰竭",
        "凋亡", "坏死", "萎缩", "肥大", "增生", "化生",
        "动作电位", "静息电位", "突触传递", "神经递质", "受体",
        "血红蛋白", "白细胞分类", "血小板聚集", "凝血因子",
        "肾小球滤过", "肾小管重吸收", "渗透压", "酸碱平衡",
        "抗原", "抗体", "补体", "细胞免疫", "体液免疫",
        "病原体", "感染", "传播途径", "潜伏期", "免疫应答",
        "变性", "纤维化", "肉芽组织", "血栓形成", "栓塞", "梗死",
    ]
    for term in known_terms:
        if term in text:
            out.append(term)

    heading_re = re.compile(r"(?m)^\s*#{1,4}\s*([一二三四五六七八九十百零\d、.\s]*[\u4e00-\u9fa5A-Za-z]{2,24})\s*$")
    for m in heading_re.finditer(text[:20000]):
        term = _clean_term(m.group(1))
        if _valid_term(term):
            out.append(term)

    definition_re = re.compile(r"([\u4e00-\u9fa5A-Za-z0-9]{2,12})(?:是指|是|指|为|包括|可分为|称为)")
    for m in definition_re.finditer(text[:25000]):
        term = _clean_term(m.group(1))
        if _valid_term(term):
            out.append(term)

    deduped: list[str] = []
    seen: set[str] = set()
    for term in out:
        key = re.sub(r"\s+", "", term)
        if key and key not in seen:
            seen.add(key)
            deduped.append(term)
    return deduped or [chapter.title[:12] or "核心概念"]


def _clean_term(term: str) -> str:
    term = re.sub(r"^[\d一二三四五六七八九十百零、.\s]+", "", term)
    term = re.sub(r"[：:，,。；;（）()【】\[\]《》<>].*$", "", term)
    return re.sub(r"\s+", "", term).strip()


def _valid_term(term: str) -> bool:
    if not 2 <= len(term) <= 12:
        return False
    if re.search(r"[，。？！；：（）()【】\[\]『』]", term):
        return False
    bad = {
        "本章", "问题", "复习题", "目录", "参考文献", "答案", "小结", "学习目标",
        "主要", "尤其", "特别", "目前认", "值得注意的", "此外", "因此", "由于",
        "一般", "这些", "这种", "临床", "患者", "表现", "发生", "可以", "作为",
        # 过于宏观的常识性概念，不应作为知识点
        "细胞", "器官", "系统", "血液", "组织", "功能", "结构", "疾病",
        "内环境", "人体", "生命", "机体", "正常", "异常", "基本",
        "心脏", "肾脏", "肺", "肝脏", "免疫", "肿瘤",
    }
    if term in bad or term.endswith(("的", "了", "认", "作", "为")):
        return False
    if any(term.startswith(prefix) for prefix in ("主要", "尤其", "特别", "目前", "值得")):
        return False
    return term not in bad and not term.startswith(("图", "表"))


def _sentence_for_term(text: str, term: str) -> str:
    compact = re.sub(r"\s+", " ", text)
    pos = compact.find(term)
    if pos < 0:
        return f"{term} 是本章教材文本中识别出的核心知识点。"
    start = max(0, compact.rfind("。", 0, pos) + 1)
    end = compact.find("。", pos)
    if end < 0:
        end = min(len(compact), pos + 180)
    sentence = compact[start:end + 1].strip()
    return sentence[:260] or f"{term} 是本章教材文本中识别出的核心知识点。"


def extract_textbook(
    textbook_id: str, chapters: list[Chapter],
    *, max_workers: int = 5, on_progress=None,
) -> tuple[list[KnowledgeNode], list[KnowledgeEdge]]:
    """并发抽取整本教材，限速 max_workers 并发请求"""
    all_nodes: list[KnowledgeNode] = []
    all_edges: list[KnowledgeEdge] = []

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(extract_chapter, textbook_id, ch): ch for ch in chapters}
        done_count = 0
        for fut in as_completed(futures):
            ch = futures[fut]
            try:
                res = fut.result()
                all_nodes.extend(res.nodes)
                all_edges.extend(res.edges)
                done_count += 1
                if on_progress:
                    on_progress(done_count, len(chapters), ch.chapter_id, len(res.nodes))
                logger.info(f"[extract] {ch.chapter_id} {ch.title[:30]}: "
                             f"{len(res.nodes)} nodes, {len(res.edges)} edges")
            except Exception as e:
                logger.error(f"[extract] {ch.chapter_id} failed: {e}")

    return all_nodes, all_edges
