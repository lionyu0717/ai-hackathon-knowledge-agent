"""知识图谱路由

POST /api/graph/build/{textbook_id}     触发抽取（后台任务）
GET  /api/graph/{textbook_id}           查图（节点+边）
GET  /api/graph                         查全部教材的合并图（用于跨教材整合后展示）
GET  /api/graph/{textbook_id}/progress  查抽取进度
"""
from __future__ import annotations

import logging
import re
from threading import Lock
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException

from ..services import store
from ..services.extractor import extract_textbook

router = APIRouter(prefix="/api/graph", tags=["graph"])
logger = logging.getLogger(__name__)

# 内存中的抽取进度（多 worker 不安全，但单进程 FastAPI 够用）
_progress: dict[str, dict[str, Any]] = {}
_progress_lock = Lock()


def _set_progress(textbook_id: str, **kw) -> None:
    with _progress_lock:
        cur = _progress.setdefault(textbook_id, {})
        cur.update(kw)


def _get_progress(textbook_id: str) -> dict[str, Any]:
    with _progress_lock:
        return dict(_progress.get(textbook_id, {}))


def _do_extract(textbook_id: str) -> None:
    tb = store.get_textbook(textbook_id)
    if not tb:
        _set_progress(textbook_id, status="failed", error="textbook not found")
        return
    if not tb.chapters:
        _set_progress(textbook_id, status="failed", error="textbook has no chapters")
        return

    _set_progress(textbook_id, status="extracting", total=len(tb.chapters), done=0,
                   nodes=0, edges=0, textbook_title=tb.title)

    nodes_total = 0

    def on_progress(done: int, total: int, ch_id: str, n_nodes: int) -> None:
        nonlocal nodes_total
        nodes_total += n_nodes
        _set_progress(textbook_id, done=done, current_chapter=ch_id, nodes=nodes_total)

    try:
        nodes, edges = extract_textbook(textbook_id, tb.chapters, on_progress=on_progress)
        store.upsert_nodes(nodes)
        store.upsert_edges(edges)
        _set_progress(textbook_id, status="done", nodes=len(nodes), edges=len(edges))
        logger.info(f"[graph] {textbook_id} done: {len(nodes)} nodes, {len(edges)} edges")
    except Exception as e:
        logger.exception(f"[graph] extract failed for {textbook_id}")
        _set_progress(textbook_id, status="failed", error=str(e)[:300])


@router.post("/build/{textbook_id}")
def build_graph(textbook_id: str, background_tasks: BackgroundTasks) -> dict:
    tb = store.get_textbook(textbook_id)
    if not tb:
        raise HTTPException(404, "textbook not found")
    if tb.parse_status.value != "done":
        raise HTTPException(400, f"textbook parse not done (status={tb.parse_status.value})")

    cur = _get_progress(textbook_id)
    if cur.get("status") == "extracting":
        return {"started": False, "reason": "already in progress", "progress": cur}

    _set_progress(textbook_id, status="queued", total=len(tb.chapters), done=0, nodes=0)
    background_tasks.add_task(_do_extract, textbook_id)
    return {"started": True, "textbook_id": textbook_id, "chapters": len(tb.chapters)}


@router.get("/{textbook_id}/progress")
def get_progress(textbook_id: str) -> dict:
    return _get_progress(textbook_id)


@router.get("/{textbook_id}")
def get_graph(textbook_id: str) -> dict:
    """返回 ECharts 可直接消费的 nodes/edges 结构。
    nodes: [{id, name, definition, category, chapter, page, value(=size hint)}]
    edges: [{source, target, relation_type, description}]
    """
    tb = store.get_textbook(textbook_id)
    if not tb:
        raise HTTPException(404, "textbook not found")

    raw_nodes = store.list_nodes(textbook_id)
    edges = store.list_edges()

    # 同名知识点去重：保留定义最长的那个，其余的 id 映射到保留的 id
    dedup_map: dict[str, str] = {}  # old_id → canonical_id
    by_name: dict[str, list] = {}
    for n in raw_nodes:
        key = re.sub(r"\s+", "", n.name).lower()
        by_name.setdefault(key, []).append(n)
    nodes = []
    for group in by_name.values():
        best = max(group, key=lambda n: len(n.definition or ""))
        nodes.append(best)
        for n in group:
            dedup_map[n.id] = best.id

    node_ids = {n.id for n in nodes}
    deduped_edges = []
    seen_edges = set()
    for e in edges:
        src = dedup_map.get(e.source, e.source)
        tgt = dedup_map.get(e.target, e.target)
        if src not in node_ids or tgt not in node_ids or src == tgt:
            continue
        edge_key = (src, tgt, e.relation_type)
        if edge_key in seen_edges:
            continue
        seen_edges.add(edge_key)
        deduped_edges.append((src, tgt, e.relation_type, e.description))
    edges = deduped_edges

    degree: dict[str, int] = {n.id: 0 for n in nodes}
    for src, tgt, _, _ in edges:
        degree[src] = degree.get(src, 0) + 1
        degree[tgt] = degree.get(tgt, 0) + 1

    return {
        "textbook": {"id": tb.textbook_id, "title": tb.title, "filename": tb.filename},
        "nodes": [
            {
                "id": n.id,
                "name": n.name,
                "definition": n.definition,
                "category": n.category,
                "chapter": n.chapter_title,
                "chapter_id": n.chapter_id,
                "page": n.page,
                "textbook_id": n.textbook_id,
                "value": degree.get(n.id, 0) + 1,
            } for n in nodes
        ],
        "edges": [
            {
                "source": src,
                "target": tgt,
                "relation_type": rel,
                "description": desc,
            } for src, tgt, rel, desc in edges
        ],
        "stats": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "categories": sorted({n.category for n in nodes}),
        },
    }


@router.get("")
def get_full_graph() -> dict:
    """合并所有教材的图（用于整合后展示）。
    每个节点带 textbook_id，前端按 textbook 上色。
    """
    raw_nodes = store.list_nodes()
    raw_edges = store.list_edges()

    # 同教材内同名去重
    dedup_map: dict[str, str] = {}
    by_key: dict[str, list] = {}
    for n in raw_nodes:
        key = f"{n.textbook_id}:{re.sub(r'\s+', '', n.name).lower()}"
        by_key.setdefault(key, []).append(n)
    nodes = []
    for group in by_key.values():
        best = max(group, key=lambda n: len(n.definition or ""))
        nodes.append(best)
        for n in group:
            dedup_map[n.id] = best.id

    node_ids = {n.id for n in nodes}
    seen_edges = set()
    edges = []
    for e in raw_edges:
        src = dedup_map.get(e.source, e.source)
        tgt = dedup_map.get(e.target, e.target)
        if src not in node_ids or tgt not in node_ids or src == tgt:
            continue
        edge_key = (src, tgt, e.relation_type)
        if edge_key in seen_edges:
            continue
        seen_edges.add(edge_key)
        edges.append({"source": src, "target": tgt, "relation_type": e.relation_type, "description": e.description})

    degree: dict[str, int] = {n.id: 0 for n in nodes}
    for e in edges:
        degree[e["source"]] = degree.get(e["source"], 0) + 1
        degree[e["target"]] = degree.get(e["target"], 0) + 1

    textbooks = store.list_textbooks()
    tb_titles = {t.textbook_id: t.title for t in textbooks}
    freq_by_name: dict[str, int] = {}
    for n in nodes:
        key = re.sub(r"\s+", "", n.name).lower()
        freq_by_name[key] = freq_by_name.get(key, 0) + 1

    return {
        "nodes": [
            {
                "id": n.id, "name": n.name, "definition": n.definition,
                "category": n.category, "chapter": n.chapter_title,
                "page": n.page, "textbook_id": n.textbook_id,
                "textbook_title": tb_titles.get(n.textbook_id, ""),
                "frequency": freq_by_name.get(re.sub(r"\s+", "", n.name).lower(), 1),
                "value": max(degree.get(n.id, 0) + 1,
                             freq_by_name.get(re.sub(r"\s+", "", n.name).lower(), 1) * 3),
            } for n in nodes
        ],
        "edges": edges,
        "stats": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "textbook_count": len(textbooks),
        },
    }
