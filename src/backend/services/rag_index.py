"""RAG index build: chunks + optional local embeddings."""
from __future__ import annotations

import logging
import os

import numpy as np

from . import store
from .chunker import build_chunks
from .embedder import encode

logger = logging.getLogger(__name__)


def rebuild_index(textbook_ids: list[str] | None = None) -> dict:
    chunks = build_chunks(textbook_ids)
    embeddings: dict[str, bytes] = {}
    use_embeddings = os.getenv("RAG_USE_EMBEDDINGS", "1").lower() not in {"0", "false", "no"}

    if chunks and use_embeddings:
        try:
            texts = [f"{c.textbook_title} {c.chapter_title} {c.section_title}\n{c.text}" for c in chunks]
            matrix = encode(texts, batch_size=24)
            for chunk, vec in zip(chunks, matrix):
                embeddings[chunk.chunk_id] = np.asarray(vec, dtype=np.float32).tobytes()
        except Exception as exc:
            logger.warning("[rag] embedding build failed, using lexical retrieval only: %s", exc)
            embeddings = {}

    store.replace_rag_chunks([c.model_dump() for c in chunks], embeddings)
    status = store.get_rag_status()
    status["embedding_enabled"] = bool(embeddings)
    return status
