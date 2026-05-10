"""SQLite 持久化层

只用 sqlite3 标准库，无 ORM。所有写入用 with 语句保证 commit/rollback。
"""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from ..models.schemas import (
    Chapter, ChatMessage, IntegrationDecision, IntegrationStats, KnowledgeEdge,
    KnowledgeNode, ParseStatus, Textbook, TextbookSummary,
)

DB_PATH = Path(os.getenv("SQLITE_PATH", "data/db/app.db"))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


SCHEMA = """
CREATE TABLE IF NOT EXISTS textbooks (
    textbook_id   TEXT PRIMARY KEY,
    filename      TEXT NOT NULL,
    title         TEXT NOT NULL,
    file_format   TEXT NOT NULL,
    total_pages   INTEGER DEFAULT 0,
    total_chars   INTEGER DEFAULT 0,
    parse_status  TEXT NOT NULL,
    error_message TEXT,
    uploaded_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chapters (
    chapter_id   TEXT NOT NULL,
    textbook_id  TEXT NOT NULL,
    title        TEXT NOT NULL,
    page_start   INTEGER DEFAULT 0,
    page_end     INTEGER DEFAULT 0,
    char_count   INTEGER DEFAULT 0,
    content      TEXT NOT NULL,
    PRIMARY KEY (textbook_id, chapter_id),
    FOREIGN KEY (textbook_id) REFERENCES textbooks(textbook_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS knowledge_nodes (
    id            TEXT PRIMARY KEY,
    textbook_id   TEXT NOT NULL,
    chapter_id    TEXT NOT NULL,
    chapter_title TEXT,
    name          TEXT NOT NULL,
    definition    TEXT,
    category      TEXT,
    page          INTEGER DEFAULT 0,
    FOREIGN KEY (textbook_id) REFERENCES textbooks(textbook_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS knowledge_edges (
    source        TEXT NOT NULL,
    target        TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    description   TEXT,
    PRIMARY KEY (source, target, relation_type)
);

CREATE INDEX IF NOT EXISTS idx_nodes_textbook ON knowledge_nodes(textbook_id);
CREATE INDEX IF NOT EXISTS idx_nodes_name ON knowledge_nodes(name);
CREATE INDEX IF NOT EXISTS idx_chapters_textbook ON chapters(textbook_id);

CREATE TABLE IF NOT EXISTS integration_runs (
    run_id            TEXT PRIMARY KEY,
    textbook_ids      TEXT NOT NULL,
    status            TEXT NOT NULL,
    original_textbooks INTEGER DEFAULT 0,
    original_chars    INTEGER DEFAULT 0,
    merged_chars      INTEGER DEFAULT 0,
    compression_ratio REAL DEFAULT 0,
    original_nodes    INTEGER DEFAULT 0,
    merged_nodes      INTEGER DEFAULT 0,
    decisions_merge   INTEGER DEFAULT 0,
    decisions_keep    INTEGER DEFAULT 0,
    decisions_remove  INTEGER DEFAULT 0,
    summary_markdown  TEXT DEFAULT '',
    error_message     TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS integration_decisions (
    decision_id    TEXT PRIMARY KEY,
    run_id         TEXT NOT NULL,
    action         TEXT NOT NULL,
    affected_nodes TEXT NOT NULL,
    result_node    TEXT,
    result_chunks  TEXT NOT NULL,
    reason         TEXT NOT NULL,
    confidence     REAL DEFAULT 0,
    source_excerpt TEXT DEFAULT '',
    source_refs    TEXT NOT NULL,
    created_at     TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES integration_runs(run_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_integration_decisions_run ON integration_decisions(run_id);
CREATE INDEX IF NOT EXISTS idx_integration_runs_updated ON integration_runs(updated_at);

CREATE TABLE IF NOT EXISTS rag_chunks (
    chunk_id       TEXT PRIMARY KEY,
    textbook_id    TEXT NOT NULL,
    textbook_title TEXT NOT NULL,
    chapter_id     TEXT NOT NULL,
    chapter_title  TEXT NOT NULL,
    section_title  TEXT DEFAULT '',
    page_start     INTEGER DEFAULT 0,
    page_end       INTEGER DEFAULT 0,
    text           TEXT NOT NULL,
    char_count     INTEGER DEFAULT 0,
    embedding      BLOB,
    created_at     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_rag_chunks_textbook ON rag_chunks(textbook_id);
CREATE INDEX IF NOT EXISTS idx_rag_chunks_chapter ON rag_chunks(textbook_id, chapter_id);

CREATE TABLE IF NOT EXISTS rag_index_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role       TEXT NOT NULL,
    content    TEXT NOT NULL,
    tool_name  TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(session_id, id);
"""


@contextmanager
def conn() -> Iterator[sqlite3.Connection]:
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    try:
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


def init_db() -> None:
    with conn() as c:
        c.executescript(SCHEMA)


# ============== Textbook ==============

def upsert_textbook(tb: Textbook) -> None:
    with conn() as c:
        c.execute(
            """INSERT OR REPLACE INTO textbooks
            (textbook_id, filename, title, file_format, total_pages,
             total_chars, parse_status, error_message, uploaded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (tb.textbook_id, tb.filename, tb.title, tb.file_format,
             tb.total_pages, tb.total_chars, tb.parse_status.value,
             tb.error_message, tb.uploaded_at.isoformat()),
        )
        # 全量重建 chapters
        c.execute("DELETE FROM chapters WHERE textbook_id=?", (tb.textbook_id,))
        for ch in tb.chapters:
            c.execute(
                """INSERT INTO chapters
                (chapter_id, textbook_id, title, page_start, page_end, char_count, content)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (ch.chapter_id, tb.textbook_id, ch.title,
                 ch.page_start, ch.page_end, ch.char_count, ch.content),
            )


def update_textbook_status(textbook_id: str, status: ParseStatus,
                            error: str | None = None) -> None:
    with conn() as c:
        c.execute(
            "UPDATE textbooks SET parse_status=?, error_message=? WHERE textbook_id=?",
            (status.value, error, textbook_id),
        )


def list_textbooks() -> list[TextbookSummary]:
    with conn() as c:
        rows = c.execute(
            """SELECT t.*, COALESCE(c.cnt, 0) AS chapter_count
               FROM textbooks t
               LEFT JOIN (SELECT textbook_id, COUNT(*) AS cnt FROM chapters GROUP BY textbook_id) c
                 ON t.textbook_id = c.textbook_id
               ORDER BY t.uploaded_at DESC"""
        ).fetchall()
        return [TextbookSummary(
            textbook_id=r["textbook_id"], filename=r["filename"], title=r["title"],
            file_format=r["file_format"], total_pages=r["total_pages"],
            total_chars=r["total_chars"], chapter_count=r["chapter_count"],
            parse_status=ParseStatus(r["parse_status"]), error_message=r["error_message"],
            uploaded_at=r["uploaded_at"],  # type: ignore[arg-type]
        ) for r in rows]


def get_textbook(textbook_id: str) -> Textbook | None:
    with conn() as c:
        r = c.execute("SELECT * FROM textbooks WHERE textbook_id=?", (textbook_id,)).fetchone()
        if not r:
            return None
        chs = c.execute(
            "SELECT * FROM chapters WHERE textbook_id=? ORDER BY chapter_id",
            (textbook_id,),
        ).fetchall()
        return Textbook(
            textbook_id=r["textbook_id"], filename=r["filename"], title=r["title"],
            file_format=r["file_format"], total_pages=r["total_pages"],
            total_chars=r["total_chars"], parse_status=ParseStatus(r["parse_status"]),
            error_message=r["error_message"], uploaded_at=r["uploaded_at"],  # type: ignore
            chapters=[Chapter(
                chapter_id=ch["chapter_id"], title=ch["title"],
                page_start=ch["page_start"], page_end=ch["page_end"],
                char_count=ch["char_count"], content=ch["content"],
            ) for ch in chs],
        )


def list_chapters(textbook_id: str) -> list[Chapter]:
    with conn() as c:
        rows = c.execute(
            "SELECT * FROM chapters WHERE textbook_id=? ORDER BY chapter_id",
            (textbook_id,),
        ).fetchall()
        return [Chapter(
            chapter_id=r["chapter_id"], title=r["title"],
            page_start=r["page_start"], page_end=r["page_end"],
            char_count=r["char_count"], content=r["content"],
        ) for r in rows]


def get_chapter(textbook_id: str, chapter_id: str) -> Chapter | None:
    with conn() as c:
        r = c.execute(
            "SELECT * FROM chapters WHERE textbook_id=? AND chapter_id=?",
            (textbook_id, chapter_id),
        ).fetchone()
        if not r:
            return None
        return Chapter(
            chapter_id=r["chapter_id"], title=r["title"],
            page_start=r["page_start"], page_end=r["page_end"],
            char_count=r["char_count"], content=r["content"],
        )


def delete_textbook(textbook_id: str) -> None:
    with conn() as c:
        c.execute("DELETE FROM textbooks WHERE textbook_id=?", (textbook_id,))


# ============== Knowledge nodes/edges ==============

def upsert_nodes(nodes: list[KnowledgeNode]) -> None:
    with conn() as c:
        for n in nodes:
            c.execute(
                """INSERT OR REPLACE INTO knowledge_nodes
                (id, textbook_id, chapter_id, chapter_title, name, definition, category, page)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (n.id, n.textbook_id, n.chapter_id, n.chapter_title,
                 n.name, n.definition, n.category, n.page),
            )


def upsert_edges(edges: list[KnowledgeEdge]) -> None:
    with conn() as c:
        for e in edges:
            c.execute(
                """INSERT OR REPLACE INTO knowledge_edges
                (source, target, relation_type, description)
                VALUES (?, ?, ?, ?)""",
                (e.source, e.target, e.relation_type, e.description),
            )


def list_nodes(textbook_id: str | None = None) -> list[KnowledgeNode]:
    with conn() as c:
        if textbook_id:
            rows = c.execute("SELECT * FROM knowledge_nodes WHERE textbook_id=?", (textbook_id,)).fetchall()
        else:
            rows = c.execute("SELECT * FROM knowledge_nodes").fetchall()
        return [KnowledgeNode(
            id=r["id"], textbook_id=r["textbook_id"], chapter_id=r["chapter_id"],
            chapter_title=r["chapter_title"] or "", name=r["name"],
            definition=r["definition"] or "", category=r["category"] or "核心概念",
            page=r["page"] or 0,
        ) for r in rows]


def list_edges() -> list[KnowledgeEdge]:
    with conn() as c:
        rows = c.execute("SELECT * FROM knowledge_edges").fetchall()
        return [KnowledgeEdge(
            source=r["source"], target=r["target"],
            relation_type=r["relation_type"],  # type: ignore[arg-type]
            description=r["description"] or "",
        ) for r in rows]


# ============== Integration runs/decisions ==============

def create_integration_run(run_id: str, textbook_ids: list[str], status: str = "queued") -> None:
    from datetime import datetime

    now = datetime.utcnow().isoformat()
    with conn() as c:
        c.execute(
            """INSERT OR REPLACE INTO integration_runs
            (run_id, textbook_ids, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)""",
            (run_id, json.dumps(textbook_ids, ensure_ascii=False), status, now, now),
        )
        c.execute("DELETE FROM integration_decisions WHERE run_id=?", (run_id,))


def update_integration_run(
    run_id: str,
    *,
    status: str | None = None,
    stats: IntegrationStats | None = None,
    summary_markdown: str | None = None,
    error_message: str | None = None,
) -> None:
    from datetime import datetime

    fields: list[str] = ["updated_at=?"]
    values: list[object] = [datetime.utcnow().isoformat()]
    if status is not None:
        fields.append("status=?")
        values.append(status)
    if stats is not None:
        fields.extend([
            "original_textbooks=?", "original_chars=?", "merged_chars=?",
            "compression_ratio=?", "original_nodes=?", "merged_nodes=?",
            "decisions_merge=?", "decisions_keep=?", "decisions_remove=?",
        ])
        values.extend([
            stats.original_textbooks, stats.original_chars, stats.merged_chars,
            stats.compression_ratio, stats.original_nodes, stats.merged_nodes,
            stats.decisions_merge, stats.decisions_keep, stats.decisions_remove,
        ])
    if summary_markdown is not None:
        fields.append("summary_markdown=?")
        values.append(summary_markdown)
    if error_message is not None:
        fields.append("error_message=?")
        values.append(error_message)
    values.append(run_id)

    with conn() as c:
        c.execute(f"UPDATE integration_runs SET {', '.join(fields)} WHERE run_id=?", values)


def replace_integration_decisions(run_id: str, decisions: list[dict]) -> None:
    from datetime import datetime

    now = datetime.utcnow().isoformat()
    with conn() as c:
        c.execute("DELETE FROM integration_decisions WHERE run_id=?", (run_id,))
        for d in decisions:
            c.execute(
                """INSERT INTO integration_decisions
                (decision_id, run_id, action, affected_nodes, result_node, result_chunks,
                 reason, confidence, source_excerpt, source_refs, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    d["decision_id"], run_id, d["action"],
                    json.dumps(d.get("affected_nodes", []), ensure_ascii=False),
                    d.get("result_node"),
                    json.dumps(d.get("result_chunks", []), ensure_ascii=False),
                    d.get("reason", ""),
                    float(d.get("confidence", 0.0)),
                    d.get("source_excerpt", ""),
                    json.dumps(d.get("source_refs", []), ensure_ascii=False),
                    now,
                ),
            )


def get_integration_run(run_id: str | None = None) -> dict | None:
    with conn() as c:
        if run_id:
            r = c.execute("SELECT * FROM integration_runs WHERE run_id=?", (run_id,)).fetchone()
        else:
            r = c.execute(
                "SELECT * FROM integration_runs ORDER BY updated_at DESC LIMIT 1"
            ).fetchone()
        if not r:
            return None
        return {
            "run_id": r["run_id"],
            "textbook_ids": json.loads(r["textbook_ids"] or "[]"),
            "status": r["status"],
            "stats": IntegrationStats(
                original_textbooks=r["original_textbooks"] or 0,
                original_chars=r["original_chars"] or 0,
                merged_chars=r["merged_chars"] or 0,
                compression_ratio=r["compression_ratio"] or 0.0,
                original_nodes=r["original_nodes"] or 0,
                merged_nodes=r["merged_nodes"] or 0,
                decisions_merge=r["decisions_merge"] or 0,
                decisions_keep=r["decisions_keep"] or 0,
                decisions_remove=r["decisions_remove"] or 0,
            ),
            "summary_markdown": r["summary_markdown"] or "",
            "error_message": r["error_message"],
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        }


def list_integration_decisions(run_id: str | None = None) -> list[dict]:
    latest = get_integration_run(run_id)
    if not latest:
        return []
    resolved_run_id = latest["run_id"]
    with conn() as c:
        rows = c.execute(
            """SELECT * FROM integration_decisions
               WHERE run_id=?
               ORDER BY
                 CASE action WHEN 'merge' THEN 0 WHEN 'keep' THEN 1 ELSE 2 END,
                 confidence DESC,
                 decision_id""",
            (resolved_run_id,),
        ).fetchall()
        out: list[dict] = []
        for r in rows:
            base = IntegrationDecision(
                decision_id=r["decision_id"],
                action=r["action"],  # type: ignore[arg-type]
                affected_nodes=json.loads(r["affected_nodes"] or "[]"),
                result_node=r["result_node"],
                result_chunks=json.loads(r["result_chunks"] or "[]"),
                reason=r["reason"] or "",
                confidence=r["confidence"] or 0.0,
            ).model_dump()
            base["source_excerpt"] = r["source_excerpt"] or ""
            base["source_refs"] = json.loads(r["source_refs"] or "[]")
            out.append(base)
        return out


def get_integration_decision(decision_id: str) -> dict | None:
    with conn() as c:
        r = c.execute("SELECT * FROM integration_decisions WHERE decision_id=?", (decision_id,)).fetchone()
        if not r:
            return None
        return {
            "decision_id": r["decision_id"],
            "run_id": r["run_id"],
            "action": r["action"],
            "affected_nodes": json.loads(r["affected_nodes"] or "[]"),
            "result_node": r["result_node"],
            "result_chunks": json.loads(r["result_chunks"] or "[]"),
            "reason": r["reason"] or "",
            "confidence": r["confidence"] or 0.0,
            "source_excerpt": r["source_excerpt"] or "",
            "source_refs": json.loads(r["source_refs"] or "[]"),
        }


def update_integration_decision_action(
    decision_id: str, action: str, reason: str, confidence: float | None = None,
) -> bool:
    fields = ["action=?", "reason=?"]
    values: list[object] = [action, reason]
    if confidence is not None:
        fields.append("confidence=?")
        values.append(confidence)
    values.append(decision_id)
    with conn() as c:
        cur = c.execute(
            f"UPDATE integration_decisions SET {', '.join(fields)} WHERE decision_id=?",
            values,
        )
        return cur.rowcount > 0


def refresh_integration_decision_counts(run_id: str) -> None:
    run = get_integration_run(run_id)
    if not run:
        return
    stats = run["stats"]
    with conn() as c:
        rows = c.execute(
            "SELECT action, COUNT(*) AS cnt FROM integration_decisions WHERE run_id=? GROUP BY action",
            (run_id,),
        ).fetchall()
    counts = {r["action"]: int(r["cnt"]) for r in rows}
    stats.decisions_merge = counts.get("merge", 0)
    stats.decisions_keep = counts.get("keep", 0)
    stats.decisions_remove = counts.get("remove", 0)
    update_integration_run(run_id, stats=stats)


# ============== RAG chunks ==============

def replace_rag_chunks(chunks: list[dict], embeddings: dict[str, bytes] | None = None) -> None:
    from datetime import datetime

    now = datetime.utcnow().isoformat()
    embeddings = embeddings or {}
    with conn() as c:
        c.execute("DELETE FROM rag_chunks")
        for ch in chunks:
            c.execute(
                """INSERT INTO rag_chunks
                (chunk_id, textbook_id, textbook_title, chapter_id, chapter_title,
                 section_title, page_start, page_end, text, char_count, embedding, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    ch["chunk_id"], ch["textbook_id"], ch["textbook_title"],
                    ch["chapter_id"], ch["chapter_title"], ch.get("section_title", ""),
                    ch.get("page_start", 0), ch.get("page_end", 0),
                    ch["text"], ch.get("char_count", len(ch["text"])),
                    embeddings.get(ch["chunk_id"]), now,
                ),
            )
        c.execute(
            "INSERT OR REPLACE INTO rag_index_meta (key, value) VALUES (?, ?)",
            ("chunk_count", str(len(chunks))),
        )
        c.execute(
            "INSERT OR REPLACE INTO rag_index_meta (key, value) VALUES (?, ?)",
            ("updated_at", now),
        )


def list_rag_chunks() -> list[dict]:
    with conn() as c:
        rows = c.execute("SELECT * FROM rag_chunks ORDER BY textbook_id, chapter_id, chunk_id").fetchall()
        return [dict(r) for r in rows]


def get_rag_status() -> dict:
    with conn() as c:
        rows = c.execute("SELECT key, value FROM rag_index_meta").fetchall()
        meta = {r["key"]: r["value"] for r in rows}
        count = c.execute("SELECT COUNT(*) AS cnt FROM rag_chunks").fetchone()["cnt"]
        embedded = c.execute(
            "SELECT COUNT(*) AS cnt FROM rag_chunks WHERE embedding IS NOT NULL"
        ).fetchone()["cnt"]
        textbooks = c.execute(
            "SELECT COUNT(DISTINCT textbook_id) AS cnt FROM rag_chunks"
        ).fetchone()["cnt"]
        return {
            "status": "ready" if count else "empty",
            "chunk_count": count,
            "embedded_count": embedded,
            "textbook_count": textbooks,
            "updated_at": meta.get("updated_at"),
        }


# ============== Chat history ==============

def append_chat_message(session_id: str, message: ChatMessage) -> None:
    with conn() as c:
        c.execute(
            """INSERT INTO chat_messages (session_id, role, content, tool_name, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (
                session_id, message.role, message.content, message.tool_name,
                message.timestamp.isoformat(),
            ),
        )


def list_chat_messages(session_id: str, limit: int = 50) -> list[ChatMessage]:
    with conn() as c:
        rows = c.execute(
            """SELECT * FROM chat_messages WHERE session_id=?
               ORDER BY id DESC LIMIT ?""",
            (session_id, limit),
        ).fetchall()
        return [
            ChatMessage(
                role=r["role"],
                content=r["content"],
                tool_name=r["tool_name"],
                timestamp=r["created_at"],  # type: ignore[arg-type]
            )
            for r in reversed(rows)
        ]
