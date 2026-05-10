"""嵌入服务：sentence-transformers + BGE-small-zh-v1.5

特点：
- 单例模式（首次调用加载，后续复用，~100MB 模型）
- normalize_embeddings=True 避免每次手算 L2 norm
- 支持批量编码
"""
from __future__ import annotations

import logging
import os
from functools import lru_cache

import numpy as np

logger = logging.getLogger(__name__)

DEFAULT_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")
EMBED_DIM = 512  # bge-small-zh 维度


@lru_cache(maxsize=1)
def get_model():
    from sentence_transformers import SentenceTransformer
    cache = os.getenv("SENTENCE_TRANSFORMERS_HOME") or os.getenv("HF_HOME") or "data/models"
    logger.info(f"[embedder] loading {DEFAULT_MODEL} (cache={cache})")
    m = SentenceTransformer(DEFAULT_MODEL, cache_folder=cache)
    logger.info(f"[embedder] loaded, dim={m.get_sentence_embedding_dimension()}")
    return m


def encode(texts: list[str], *, batch_size: int = 32) -> np.ndarray:
    """批量编码文本，返回 (N, D) numpy 数组（已 L2 归一化）"""
    if not texts:
        return np.zeros((0, EMBED_DIM), dtype=np.float32)
    m = get_model()
    embs = m.encode(
        texts, batch_size=batch_size, normalize_embeddings=True,
        show_progress_bar=False, convert_to_numpy=True,
    )
    return embs.astype(np.float32)


def cosine_sim_matrix(a: np.ndarray, b: np.ndarray | None = None) -> np.ndarray:
    """因为已经 L2 归一化，余弦相似度 = 点积"""
    if b is None:
        b = a
    return a @ b.T
