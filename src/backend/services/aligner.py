"""跨教材对齐：双重对齐 + Union-Find 聚类

PLAN v2 决策 2 — 重复判定四要素（Stage 2 prompt）:
  1. 指称同一对象
  2. 核心定义重叠 ≥ 70%
  3. 学科范畴一致
  4. 抽象层级一致

流程：
  Stage 1 召回（embedding）— cos_sim ≥ THRESHOLD → 候选对
  Stage 2 LLM 精判（5 对/批，并发）— verdict ∈ {same, related, different}
  Stage 3 Union-Find 聚类传递性（A=B 且 B=C → A=C）

返回：clusters（每簇是一个 node_id 列表）+ pairwise judgments
"""
from __future__ import annotations

import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

import numpy as np

from ..models.schemas import KnowledgeNode
from .embedder import encode
from .llm import chat_json

logger = logging.getLogger(__name__)

SIM_THRESHOLD = 0.82
LLM_BATCH_SIZE = 5
MAX_WORKERS = 5

JUDGE_SYSTEM = "你是一个严谨的学科知识审核专家，擅长判断不同教材中知识点是否实质相同。"

JUDGE_PROMPT = """判断以下知识点对是否指代**同一个核心概念**。

## 判定四要素（必须全部满足才是 same）
1. 指称同一对象（无论中英文/同义词/缩写）
2. 核心定义重叠 ≥ 70%
3. 学科范畴一致
4. 抽象层级一致（避免把上位概念和下位概念误判为相同，如"细胞" vs "神经细胞"）

## verdict 取值
- same: 满足全部 4 要素，应该合并
- related: 紧密相关但抽象层级不同 / 内涵不完全重合，不应合并
- different: 无关或反义

## 输出格式（严格 JSON 数组，每个 pair 一条记录，不要其他文字）
[
  {{"pair_id": "p0", "verdict": "same", "confidence": 0.95, "reason": "都是细胞内的化学储能分子"}},
  ...
]

## 待判定的知识点对
{pairs}
"""


@dataclass
class Judgment:
    pair_id: str
    verdict: str  # same / related / different
    confidence: float
    reason: str


@dataclass
class AlignmentResult:
    clusters: list[list[str]] = field(default_factory=list)  # 每簇是 node_id 列表（仅含 ≥2 节点的簇）
    judgments: list[Judgment] = field(default_factory=list)
    candidate_pair_count: int = 0
    same_pair_count: int = 0


# ---- Union-Find ----

class UnionFind:
    def __init__(self, items: list[str]):
        self.parent = {x: x for x in items}

    def find(self, x: str) -> str:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb

    def clusters(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for x in self.parent:
            out.setdefault(self.find(x), []).append(x)
        return out


# ---- Stage 1: 候选召回 ----

def _stage1_recall(
    nodes: list[KnowledgeNode], threshold: float = SIM_THRESHOLD,
) -> list[tuple[int, int, float]]:
    """返回 (i, j, sim) 候选对，按 sim 降序"""
    if len(nodes) < 2:
        return []
    texts = [f"{n.name}：{n.definition[:200]}" for n in nodes]
    embs = encode(texts)  # (N, D)
    sim = embs @ embs.T  # (N, N)
    np.fill_diagonal(sim, 0.0)

    # 仅取上三角，避免重复
    n = len(nodes)
    candidates: list[tuple[int, int, float]] = []
    for i in range(n):
        # 同教材同章节内的高相似实际是抽取冗余，跨教材才是去重目标
        for j in range(i + 1, n):
            if sim[i, j] >= threshold:
                # 跳过同教材内的（同教材抽出来的同名概念已在 extractor 里去重）
                if nodes[i].textbook_id == nodes[j].textbook_id:
                    continue
                candidates.append((i, j, float(sim[i, j])))
    candidates.sort(key=lambda x: -x[2])
    return candidates


# ---- Stage 2: LLM 精判 ----

def _format_pair(idx: int, n1: KnowledgeNode, n2: KnowledgeNode, sim: float) -> str:
    return (
        f"pair_id=p{idx} (sim={sim:.2f})\n"
        f"  A: 「{n1.name}」 来源=《{n1.chapter_title or n1.textbook_id}》\n"
        f"     定义: {n1.definition[:180]}\n"
        f"  B: 「{n2.name}」 来源=《{n2.chapter_title or n2.textbook_id}》\n"
        f"     定义: {n2.definition[:180]}"
    )


def _stage2_judge_batch(
    nodes: list[KnowledgeNode], batch: list[tuple[int, int, float]],
    *, batch_offset: int,
) -> list[Judgment]:
    """对一批候选对调一次 LLM"""
    pairs_text = "\n\n".join(
        _format_pair(batch_offset + k, nodes[i], nodes[j], s)
        for k, (i, j, s) in enumerate(batch)
    )
    prompt = JUDGE_PROMPT.format(pairs=pairs_text)
    try:
        raw = chat_json(prompt, JUDGE_SYSTEM, max_tokens=1500, temperature=0.05)
    except Exception as e:
        logger.warning(f"[align] LLM batch failed: {e}")
        return []

    if not isinstance(raw, list):
        logger.warning(f"[align] LLM returned non-list: {type(raw)}")
        return []

    out: list[Judgment] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        pid = str(item.get("pair_id", "")).strip()
        verdict = str(item.get("verdict", "")).strip().lower()
        if verdict not in ("same", "related", "different"):
            continue
        try:
            conf = float(item.get("confidence", 0.0))
        except Exception:
            conf = 0.0
        out.append(Judgment(
            pair_id=pid, verdict=verdict, confidence=conf,
            reason=str(item.get("reason", ""))[:200],
        ))
    return out


# ---- Stage 3: 聚类（U-F） ----

def align_nodes(
    nodes: list[KnowledgeNode],
    *, threshold: float = SIM_THRESHOLD, conf_threshold: float = 0.7,
) -> AlignmentResult:
    """全流程：召回 → LLM 精判 → 聚类"""
    if len(nodes) < 2:
        return AlignmentResult()

    candidates = _stage1_recall(nodes, threshold)
    logger.info(f"[align] stage1 recall: {len(candidates)} pairs from {len(nodes)} nodes")

    if not candidates:
        return AlignmentResult(candidate_pair_count=0)

    judge_mode = os.getenv("INTEGRATION_USE_LLM_JUDGE", "0").lower()
    llm_enabled = judge_mode in {"1", "true", "yes"} or (
        judge_mode == "auto" and bool(os.getenv("MODELSCOPE_ACCESS_TOKEN"))
    )
    if not llm_enabled:
        logger.info("[align] skip LLM judge (INTEGRATION_USE_LLM_JUDGE=%s)", judge_mode)
        auto_merge_sim = float(os.getenv("INTEGRATION_AUTO_MERGE_SIM", "0.92"))
        uf = UnionFind([n.id for n in nodes])
        same_count = 0
        for i, j, sim_score in candidates:
            if sim_score >= auto_merge_sim:
                uf.union(nodes[i].id, nodes[j].id)
                same_count += 1
        multi_clusters = [v for v in uf.clusters().values() if len(v) >= 2]
        return AlignmentResult(
            clusters=multi_clusters,
            candidate_pair_count=len(candidates),
            same_pair_count=same_count,
        )

    # 对候选对分批
    batches: list[list[tuple[int, int, float]]] = []
    for i in range(0, len(candidates), LLM_BATCH_SIZE):
        batches.append(candidates[i: i + LLM_BATCH_SIZE])

    all_judgments: list[Judgment] = []
    pair_to_indices: dict[str, tuple[int, int]] = {}
    for batch_idx, batch in enumerate(batches):
        offset = batch_idx * LLM_BATCH_SIZE
        for k, (i, j, _s) in enumerate(batch):
            pair_to_indices[f"p{offset + k}"] = (i, j)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {
            ex.submit(_stage2_judge_batch, nodes, batch, batch_offset=batch_idx * LLM_BATCH_SIZE): batch_idx
            for batch_idx, batch in enumerate(batches)
        }
        for fut in as_completed(futures):
            try:
                all_judgments.extend(fut.result())
            except Exception as e:
                logger.error(f"[align] batch {futures[fut]} crashed: {e}")

    # Union-Find
    uf = UnionFind([n.id for n in nodes])
    same_count = 0
    for j in all_judgments:
        if j.verdict != "same" or j.confidence < conf_threshold:
            continue
        idx_pair = pair_to_indices.get(j.pair_id)
        if not idx_pair:
            continue
        ia, ib = idx_pair
        uf.union(nodes[ia].id, nodes[ib].id)
        same_count += 1

    raw_clusters = uf.clusters()
    multi_clusters = [v for v in raw_clusters.values() if len(v) >= 2]

    logger.info(f"[align] stage3: {same_count} same-pairs → {len(multi_clusters)} clusters with ≥2 nodes")

    return AlignmentResult(
        clusters=multi_clusters,
        judgments=all_judgments,
        candidate_pair_count=len(candidates),
        same_pair_count=same_count,
    )
