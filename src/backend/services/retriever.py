"""Hybrid retrieval: vector + BM25 + RRF."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

import jieba
import numpy as np
from rank_bm25 import BM25Okapi

from . import store
from .embedder import encode


@dataclass
class RetrievedChunk:
    chunk: dict
    score: float
    vector_score: float = 0.0
    bm25_score: float = 0.0


def retrieve(question: str, top_k: int = 5) -> list[RetrievedChunk]:
    chunks = store.list_rag_chunks()
    if not chunks:
        return []

    vector_rank, vector_scores = _vector_rank(question, chunks)
    bm25_rank, bm25_scores = _bm25_rank(question, chunks)

    rrf: dict[int, float] = {}
    for rank, idx in enumerate(vector_rank[:30], start=1):
        rrf[idx] = rrf.get(idx, 0.0) + 1.0 / (60 + rank)
    for rank, idx in enumerate(bm25_rank[:30], start=1):
        rrf[idx] = rrf.get(idx, 0.0) + 1.0 / (60 + rank)

    if not rrf:
        return []
    ordered = sorted(rrf, key=rrf.get, reverse=True)[:top_k]
    return [
        RetrievedChunk(
            chunk=chunks[idx],
            score=rrf[idx],
            vector_score=vector_scores.get(idx, 0.0),
            bm25_score=bm25_scores.get(idx, 0.0),
        )
        for idx in ordered
    ]


def _vector_rank(question: str, chunks: list[dict]) -> tuple[list[int], dict[int, float]]:
    emb_rows: list[np.ndarray] = []
    indices: list[int] = []
    for idx, chunk in enumerate(chunks):
        raw = chunk.get("embedding")
        if raw:
            emb_rows.append(np.frombuffer(raw, dtype=np.float32))
            indices.append(idx)
    if not emb_rows:
        return [], {}
    try:
        q = encode([question])[0]
    except Exception:
        return [], {}
    matrix = np.vstack(emb_rows)
    scores = matrix @ q
    order = np.argsort(-scores)
    score_map = {indices[i]: float(scores[i]) for i in range(len(indices))}
    return [indices[i] for i in order], score_map


def _bm25_rank(question: str, chunks: list[dict]) -> tuple[list[int], dict[int, float]]:
    corpus = [_tokenize(f"{c['textbook_title']} {c['chapter_title']} {c.get('section_title') or ''} {c['text']}") for c in chunks]
    query = _tokenize(question)
    if not query:
        return [], {}
    bm25 = BM25Okapi(corpus)
    scores = bm25.get_scores(query)
    order = np.argsort(-scores)
    score_map = {int(i): float(scores[i]) for i in order if not math.isclose(float(scores[i]), 0.0)}
    return [int(i) for i in order if scores[i] > 0], score_map


def _tokenize(text: str) -> list[str]:
    text = re.sub(r"[^\u4e00-\u9fa5A-Za-z0-9]+", " ", text)
    return [t.strip().lower() for t in jieba.lcut(text) if len(t.strip()) > 1]
