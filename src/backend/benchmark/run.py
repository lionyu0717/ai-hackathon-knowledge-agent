"""Run a lightweight RAG retrieval benchmark."""
from __future__ import annotations

import json
import time
from pathlib import Path

from ..services import store
from ..services.rag_index import rebuild_index
from ..services.retriever import retrieve

EVAL_PATH = Path(__file__).with_name("eval_set.jsonl")


def load_eval_set() -> list[dict]:
    return [json.loads(line) for line in EVAL_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]


def run() -> dict:
    store.init_db()
    status = store.get_rag_status()
    if status["chunk_count"] == 0:
        status = rebuild_index()

    cases = load_eval_set()
    rows: list[dict] = []
    started = time.perf_counter()
    for case in cases:
        hits = retrieve(case["question"], top_k=5)
        joined = "\n".join(h.chunk["text"] for h in hits)
        books = {h.chunk["textbook_title"] for h in hits}
        keyword_hit = any(k in joined for k in case["expected_keywords"])
        book_hit = any(any(expected in book for book in books) for expected in case["expected_textbooks"])
        rows.append({
            "id": case["id"],
            "type": case["type"],
            "keyword_hit": keyword_hit,
            "book_hit": book_hit,
            "top1": hits[0].chunk["textbook_title"] if hits else "",
            "top1_chapter": hits[0].chunk["chapter_title"] if hits else "",
        })

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    keyword_hit_at5 = sum(1 for r in rows if r["keyword_hit"]) / len(rows) if rows else 0.0
    book_hit_at5 = sum(1 for r in rows if r["book_hit"]) / len(rows) if rows else 0.0
    return {
        "cases": len(rows),
        "chunk_count": store.get_rag_status()["chunk_count"],
        "keyword_hit_at5": round(keyword_hit_at5, 3),
        "book_hit_at5": round(book_hit_at5, 3),
        "elapsed_ms": elapsed_ms,
        "rows": rows,
    }


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
