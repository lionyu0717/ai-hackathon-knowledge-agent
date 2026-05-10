"""统一数据模型

所有上下游模块共用这些 schema：
- Textbook → Chapter → (Chunk | KnowledgeNode | KnowledgeEdge)
- 上传/解析后存 SQLite，整合阶段读出来跑对齐与压缩
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


# ============== 解析阶段 ==============

class ParseStatus(str, Enum):
    PENDING = "pending"
    PARSING = "parsing"
    DONE = "done"
    FAILED = "failed"


class Chapter(BaseModel):
    chapter_id: str
    title: str
    page_start: int = 0
    page_end: int = 0
    char_count: int = 0
    content: str = ""  # Markdown 格式正文


class Textbook(BaseModel):
    textbook_id: str
    filename: str
    title: str
    file_format: Literal["pdf", "md", "txt", "docx"] = "pdf"
    total_pages: int = 0
    total_chars: int = 0
    chapters: list[Chapter] = []
    parse_status: ParseStatus = ParseStatus.PENDING
    error_message: str | None = None
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)


class TextbookSummary(BaseModel):
    """前端列表用的精简版（不含 chapter content）"""
    textbook_id: str
    filename: str
    title: str
    file_format: str
    total_pages: int
    total_chars: int
    chapter_count: int
    parse_status: ParseStatus
    error_message: str | None = None
    uploaded_at: datetime


# ============== 知识图谱阶段 ==============

RelationType = Literal["prerequisite", "parallel", "contains", "applies_to"]


class KnowledgeNode(BaseModel):
    id: str
    name: str
    definition: str
    category: str = "核心概念"  # 核心概念/方法/定理/现象/...
    textbook_id: str
    chapter_id: str
    chapter_title: str = ""
    page: int = 0


class KnowledgeEdge(BaseModel):
    source: str
    target: str
    relation_type: RelationType
    description: str = ""


# ============== RAG 阶段 ==============

class Chunk(BaseModel):
    chunk_id: str
    textbook_id: str
    textbook_title: str
    chapter_id: str
    chapter_title: str
    section_title: str = ""  # Markdown 二级/三级标题
    page_start: int = 0
    page_end: int = 0
    text: str
    char_count: int = 0


class Citation(BaseModel):
    textbook: str
    chapter: str
    page: int
    relevance_score: float = 0.0


class RagAnswer(BaseModel):
    answer: str
    citations: list[Citation] = []
    source_chunks: list[str] = []
    latency_ms: int = 0
    tokens: int = 0


# ============== 整合阶段 ==============

class IntegrationDecision(BaseModel):
    decision_id: str
    action: Literal["merge", "keep", "remove"]
    affected_nodes: list[str]
    result_node: str | None = None  # canonical 节点 id
    result_chunks: list[str] = []   # 选中的原文 chunk_id 列表
    reason: str
    confidence: float = 0.0


class IntegrationStats(BaseModel):
    original_textbooks: int
    original_chars: int
    merged_chars: int
    compression_ratio: float
    original_nodes: int
    merged_nodes: int
    decisions_merge: int
    decisions_keep: int
    decisions_remove: int


# ============== 对话阶段 ==============

class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "tool"]
    content: str
    tool_name: str | None = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ChatSession(BaseModel):
    session_id: str
    history: list[ChatMessage] = []
