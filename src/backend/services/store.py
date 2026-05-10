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
    Chapter, KnowledgeEdge, KnowledgeNode, ParseStatus, Textbook, TextbookSummary,
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
