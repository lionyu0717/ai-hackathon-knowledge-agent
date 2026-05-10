"""Markdown-aware RAG chunking."""
from __future__ import annotations

import hashlib
import re

from ..models.schemas import Chunk, Textbook
from . import store

TARGET_CHARS = 700
OVERLAP_CHARS = 90


def build_chunks(textbook_ids: list[str] | None = None) -> list[Chunk]:
    wanted = set(textbook_ids or [])
    chunks: list[Chunk] = []
    for item in store.list_textbooks():
        if item.parse_status.value != "done":
            continue
        if wanted and item.textbook_id not in wanted:
            continue
        tb = store.get_textbook(item.textbook_id)
        if not tb:
            continue
        chunks.extend(_chunks_for_textbook(tb))
    return chunks


def _chunks_for_textbook(tb: Textbook) -> list[Chunk]:
    out: list[Chunk] = []
    for chapter in tb.chapters:
        sections = _split_sections(chapter.content)
        for section_title, section_text in sections:
            for start, text in _sliding_windows(section_text):
                if len(text.strip()) < 80:
                    continue
                payload = f"{tb.textbook_id}:{chapter.chapter_id}:{section_title}:{start}:{text[:40]}"
                cid = "chunk_" + hashlib.md5(payload.encode("utf-8")).hexdigest()[:12]
                out.append(Chunk(
                    chunk_id=cid,
                    textbook_id=tb.textbook_id,
                    textbook_title=tb.title,
                    chapter_id=chapter.chapter_id,
                    chapter_title=chapter.title,
                    section_title=section_title,
                    page_start=chapter.page_start,
                    page_end=chapter.page_end,
                    text=text.strip(),
                    char_count=len(text.strip()),
                ))
    return out


def _split_sections(markdown: str) -> list[tuple[str, str]]:
    matches = list(re.finditer(r"(?m)^(#{2,4})\s+(.+?)\s*$", markdown))
    if not matches:
        return [("", markdown)]
    sections: list[tuple[str, str]] = []
    prefix = markdown[:matches[0].start()].strip()
    if len(prefix) > 100:
        sections.append(("", prefix))
    for idx, match in enumerate(matches):
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(markdown)
        title = re.sub(r"\s+", " ", match.group(2)).strip()[:80]
        body = markdown[match.start():end].strip()
        sections.append((title, body))
    return sections


def _sliding_windows(text: str) -> list[tuple[int, str]]:
    normalized = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(normalized) <= TARGET_CHARS:
        return [(0, normalized)]

    windows: list[tuple[int, str]] = []
    start = 0
    while start < len(normalized):
        target_end = min(len(normalized), start + TARGET_CHARS)
        end = _best_break(normalized, start, target_end)
        chunk = normalized[start:end].strip()
        if chunk:
            windows.append((start, chunk))
        if end >= len(normalized):
            break
        start = max(end - OVERLAP_CHARS, start + 1)
    return windows


def _best_break(text: str, start: int, target_end: int) -> int:
    if target_end >= len(text):
        return len(text)
    slice_text = text[start:target_end]
    for sep in ("\n##", "\n\n", "。", "；", "\n"):
        pos = slice_text.rfind(sep)
        if pos >= TARGET_CHARS * 0.55:
            return start + pos + len(sep)
    return target_end
