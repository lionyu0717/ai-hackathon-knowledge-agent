"""RAG answer generation with source citations."""
from __future__ import annotations

import time

from ..models.schemas import Citation, RagAnswer
from .llm import chat_text
from .retriever import RetrievedChunk, retrieve

ANSWER_SYSTEM = """你是教材知识库问答助手。你只能基于给定上下文回答。
每个关键事实后必须附引用，格式为 [教材, 章节, 第X页]。
如果上下文不足，回复“当前知识库中未找到相关信息”。"""


def answer_question(question: str, top_k: int = 5) -> RagAnswer:
    started = time.perf_counter()
    hits = retrieve(question, top_k=top_k)
    if not hits:
        return RagAnswer(
            answer="当前知识库中未找到相关信息。",
            citations=[],
            source_chunks=[],
            latency_ms=_elapsed_ms(started),
        )

    context = _format_context(hits)
    prompt = f"上下文：\n{context}\n\n问题：{question}\n\n请给出简洁、可核查的中文回答。"
    try:
        text = chat_text(prompt, ANSWER_SYSTEM, temperature=0.1, max_tokens=900)
    except Exception:
        text = _extractive_answer(question, hits)

    return RagAnswer(
        answer=text,
        citations=_citations(hits),
        source_chunks=[h.chunk["chunk_id"] for h in hits],
        latency_ms=_elapsed_ms(started),
    )


def _format_context(hits: list[RetrievedChunk]) -> str:
    parts: list[str] = []
    for idx, hit in enumerate(hits, start=1):
        c = hit.chunk
        parts.append(
            f"[{idx}] 来源：{c['textbook_title']}，{c['chapter_title']}，第{c['page_start']}页\n"
            f"{c['text'][:1100]}"
        )
    return "\n\n".join(parts)


def _citations(hits: list[RetrievedChunk]) -> list[Citation]:
    out: list[Citation] = []
    seen: set[tuple[str, str, int]] = set()
    for hit in hits:
        c = hit.chunk
        key = (c["textbook_title"], c["chapter_title"], int(c["page_start"] or 0))
        if key in seen:
            continue
        seen.add(key)
        out.append(Citation(
            textbook=c["textbook_title"],
            chapter=c["chapter_title"],
            page=int(c["page_start"] or 0),
            relevance_score=round(hit.score, 4),
        ))
    return out


def _extractive_answer(question: str, hits: list[RetrievedChunk]) -> str:
    lines = ["基于当前检索到的教材原文，相关信息如下："]
    for hit in hits[:3]:
        c = hit.chunk
        snippet = c["text"].replace("\n", " ")[:180]
        lines.append(f"- {snippet} [{c['textbook_title']}, {c['chapter_title']}, 第{c['page_start']}页]")
    return "\n".join(lines)


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
