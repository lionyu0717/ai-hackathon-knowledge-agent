"""跨教材知识图谱整合服务。

Phase 3 的目标是把已构建的多本教材图谱做语义对齐，输出可审核的
merge / keep / remove 决策，并用原文摘录控制压缩比不超过 30%。
"""
from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass

from ..models.schemas import IntegrationStats, KnowledgeEdge, KnowledgeNode, Textbook
from . import store
from .aligner import AlignmentResult, Judgment, align_nodes

logger = logging.getLogger(__name__)

BUDGET_RATIO = 0.28
EXCERPT_LIMIT = 900


@dataclass
class IntegrationOutput:
    run_id: str
    stats: IntegrationStats
    decisions: list[dict]
    summary_markdown: str
    alignment: AlignmentResult


def run_integration(run_id: str, textbook_ids: list[str] | None = None) -> IntegrationOutput:
    textbooks = _resolve_textbooks(textbook_ids)
    if len(textbooks) < 2:
        raise ValueError("Phase 3 至少需要 2 本已解析教材")

    selected_ids = [tb.textbook_id for tb in textbooks]
    nodes = [n for n in store.list_nodes() if n.textbook_id in selected_ids]
    node_book_count = len({n.textbook_id for n in nodes})
    if node_book_count < 2:
        raise ValueError("至少需要 2 本教材已经完成知识图谱抽取，才能执行跨教材整合")

    edges = store.list_edges()
    degree = _degree_map(edges)
    original_chars = sum(tb.total_chars for tb in textbooks)
    budget = max(1, int(original_chars * BUDGET_RATIO))

    alignment = _align_with_fallback(nodes)
    clusters = _merge_cluster_sources(nodes, alignment.clusters)

    node_by_id = {n.id: n for n in nodes}
    clustered_ids = {node_id for cluster in clusters for node_id in cluster}
    decisions: list[dict] = []
    merged_chars = 0
    kept_node_ids: set[str] = set()

    for idx, cluster in enumerate(clusters, start=1):
        cluster_nodes = [node_by_id[nid] for nid in cluster if nid in node_by_id]
        if len(cluster_nodes) < 2:
            continue
        canonical = _best_node(cluster_nodes, degree)
        excerpt = _source_excerpt(canonical)
        merged_chars += len(excerpt)
        kept_node_ids.add(canonical.id)
        decisions.append({
            "decision_id": _decision_id(run_id, "merge", idx),
            "action": "merge",
            "affected_nodes": [n.id for n in cluster_nodes],
            "result_node": canonical.id,
            "result_chunks": [_source_ref(canonical)],
            "source_refs": [_source_ref(n) for n in cluster_nodes],
            "source_excerpt": excerpt,
            "reason": _merge_reason(cluster_nodes, canonical),
            "confidence": _cluster_confidence(cluster_nodes, alignment.judgments),
        })

    unique_nodes = [n for n in nodes if n.id not in clustered_ids]
    unique_nodes.sort(key=lambda n: _importance(n, degree), reverse=True)

    keep_index = 1
    remove_index = 1
    for node in unique_nodes:
        excerpt = _source_excerpt(node, limit=650)
        projected = merged_chars + len(excerpt)
        if projected <= budget:
            merged_chars = projected
            kept_node_ids.add(node.id)
            decisions.append({
                "decision_id": _decision_id(run_id, "keep", keep_index),
                "action": "keep",
                "affected_nodes": [node.id],
                "result_node": node.id,
                "result_chunks": [_source_ref(node)],
                "source_refs": [_source_ref(node)],
                "source_excerpt": excerpt,
                "reason": f"[[{node.name}]] 暂未发现跨教材等价节点，作为独有知识点保留原文摘录。",
                "confidence": 0.82,
            })
            keep_index += 1
        else:
            decisions.append({
                "decision_id": _decision_id(run_id, "remove", remove_index),
                "action": "remove",
                "affected_nodes": [node.id],
                "result_node": None,
                "result_chunks": [],
                "source_refs": [_source_ref(node)],
                "source_excerpt": "",
                "reason": f"[[{node.name}]] 当前重要度低于已保留节点，为满足 30% 压缩预算暂不纳入精华版本。",
                "confidence": 0.74,
            })
            remove_index += 1

    stats = IntegrationStats(
        original_textbooks=len(textbooks),
        original_chars=original_chars,
        merged_chars=merged_chars,
        compression_ratio=merged_chars / original_chars if original_chars else 0.0,
        original_nodes=len(nodes),
        merged_nodes=len(kept_node_ids),
        decisions_merge=sum(1 for d in decisions if d["action"] == "merge"),
        decisions_keep=sum(1 for d in decisions if d["action"] == "keep"),
        decisions_remove=sum(1 for d in decisions if d["action"] == "remove"),
    )
    summary = _summary_markdown(textbooks, decisions, stats)
    return IntegrationOutput(run_id, stats, decisions, summary, alignment)


def _resolve_textbooks(textbook_ids: list[str] | None) -> list[Textbook]:
    wanted = set(textbook_ids or [])
    summaries = store.list_textbooks()
    out: list[Textbook] = []
    for item in summaries:
        if item.parse_status.value != "done":
            continue
        if wanted and item.textbook_id not in wanted:
            continue
        tb = store.get_textbook(item.textbook_id)
        if tb:
            out.append(tb)
    return out


def _decision_id(run_id: str, action: str, index: int) -> str:
    return f"{run_id}_{action}_{index:04d}"


def _align_with_fallback(nodes: list[KnowledgeNode]) -> AlignmentResult:
    lexical = _lexical_clusters(nodes)
    try:
        alignment = align_nodes(nodes)
    except Exception as exc:
        logger.warning("[integrate] semantic alignment failed, fallback to lexical clusters: %s", exc)
        return AlignmentResult(clusters=lexical, candidate_pair_count=0, same_pair_count=sum(len(c) - 1 for c in lexical))

    if lexical:
        alignment.clusters = _merge_cluster_sources(nodes, alignment.clusters + lexical)
    return alignment


def _norm_name(name: str) -> str:
    return re.sub(r"[\s\-_/（）()【】\[\]《》,，.。:：;；]+", "", name).lower()


def _lexical_clusters(nodes: list[KnowledgeNode]) -> list[list[str]]:
    by_name: dict[str, list[KnowledgeNode]] = {}
    for node in nodes:
        key = _norm_name(node.name)
        if len(key) < 2:
            continue
        by_name.setdefault(key, []).append(node)

    clusters: list[list[str]] = []
    for group in by_name.values():
        if len({n.textbook_id for n in group}) >= 2:
            clusters.append([n.id for n in group])
    return clusters


def _merge_cluster_sources(nodes: list[KnowledgeNode], clusters: list[list[str]]) -> list[list[str]]:
    if not clusters:
        return []
    all_ids = {n.id for n in nodes}
    parent = {node_id: node_id for node_id in all_ids}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for cluster in clusters:
        clean = [node_id for node_id in cluster if node_id in all_ids]
        for node_id in clean[1:]:
            union(clean[0], node_id)

    out: dict[str, list[str]] = {}
    for node_id in all_ids:
        out.setdefault(find(node_id), []).append(node_id)
    return [sorted(ids) for ids in out.values() if len(ids) >= 2]


def _degree_map(edges: list[KnowledgeEdge]) -> dict[str, int]:
    degree: dict[str, int] = {}
    for edge in edges:
        degree[edge.source] = degree.get(edge.source, 0) + 1
        degree[edge.target] = degree.get(edge.target, 0) + 1
    return degree


def _importance(node: KnowledgeNode, degree: dict[str, int]) -> float:
    has_def = 1.0 if len(node.definition.strip()) >= 12 else 0.0
    return degree.get(node.id, 0) * 0.45 + min(len(node.definition), 220) / 220 * 0.35 + has_def * 0.2


def _best_node(nodes: list[KnowledgeNode], degree: dict[str, int]) -> KnowledgeNode:
    return max(nodes, key=lambda n: _importance(n, degree))


def _source_ref(node: KnowledgeNode) -> str:
    return f"{node.textbook_id}:{node.chapter_id}:p{node.page or 0}:{node.name}"


def _source_excerpt(node: KnowledgeNode, limit: int = EXCERPT_LIMIT) -> str:
    ch = store.get_chapter(node.textbook_id, node.chapter_id)
    text = (ch.content if ch else node.definition).strip()
    text = re.sub(r"\s+", " ", text)
    if not text:
        return node.definition[:limit]
    pos = text.find(node.name)
    if pos < 0 and node.definition:
        pos = text.find(node.definition[:20])
    if pos < 0:
        return text[:limit]
    start = max(0, pos - limit // 3)
    end = min(len(text), start + limit)
    return text[start:end]


def _merge_reason(nodes: list[KnowledgeNode], canonical: KnowledgeNode) -> str:
    books = []
    seen = set()
    for node in nodes:
        tb = store.get_textbook(node.textbook_id)
        label = tb.title if tb else node.textbook_id
        if label not in seen:
            books.append(f"《{label}》")
            seen.add(label)
    names = sorted({f"[[{n.name}]]" for n in nodes})
    return (
        f"{'、'.join(books)} 中的 {' / '.join(names)} 被判定为同一或高度等价概念；"
        f"保留 [[{canonical.name}]] 所在原文，因为其定义更完整、图谱连接度更高。"
    )


def _cluster_confidence(nodes: list[KnowledgeNode], judgments: list[Judgment]) -> float:
    names = {_norm_name(n.name) for n in nodes}
    exact_bonus = 0.86 if len(names) == 1 else 0.78
    same_conf = [j.confidence for j in judgments if j.verdict == "same"]
    if same_conf:
        return round(max(exact_bonus, sum(same_conf) / len(same_conf)), 3)
    return exact_bonus


def _summary_markdown(textbooks: list[Textbook], decisions: list[dict], stats: IntegrationStats) -> str:
    digest = hashlib.md5("|".join(tb.textbook_id for tb in textbooks).encode("utf-8")).hexdigest()[:8]
    lines = [
        f"# 知识点进化总结 {digest}",
        "",
        f"本次整合覆盖 {stats.original_textbooks} 本教材、{stats.original_nodes} 个知识点；",
        f"保留原文摘录 {stats.merged_chars} 字，压缩比 {stats.compression_ratio:.1%}。",
        "",
        "## 双链概览",
    ]
    for d in decisions[:30]:
        if d["action"] == "merge":
            label = _node_name(d.get("result_node"))
            lines.append(f"- [[{label}]]：{d['reason']}")
    if not any(d["action"] == "merge" for d in decisions):
        keep_names = [_node_name(d.get("result_node")) for d in decisions if d["action"] == "keep"][:12]
        if keep_names:
            lines.append("- 当前样本中重复概念较少，优先保留：" + "、".join(f"[[{n}]]" for n in keep_names))
    lines.extend(["", "## 下一轮教师可反馈", "- 可以要求“保留 [[某知识点]]”或“拆开 [[A]] 和 [[B]]”，后续对话 Agent 将把反馈写回决策。"])
    return "\n".join(lines)


def _node_name(node_id: str | None) -> str:
    if not node_id:
        return "未命名知识点"
    for node in store.list_nodes():
        if node.id == node_id:
            return node.name
    return node_id
