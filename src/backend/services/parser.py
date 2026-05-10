"""文档解析器：PDF / Markdown / TXT / DOCX → 统一 Markdown + 章节结构

核心策略：
- PDF：
  ① 优先使用内置 TOC (PDF 书签) 切章节 —— 最准确（医学教材几乎都带 TOC）
  ② 退化策略：用 PyMuPDF4LLM 转 Markdown + 标题正则
  正文：用 PyMuPDF4LLM 直出 Markdown（保留段落、列表、子标题）
- Markdown / TXT：直接读
- DOCX：python-docx 按 Heading 1 切

章节过滤：跳过封面/版权/前言/目录等元页（不计入 char_count，不参与压缩计算）
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from ..models.schemas import Chapter, Textbook, ParseStatus

# ---- 章节标题识别：匹配「第X章」「第X部分」「Chapter X」 ----
CHAPTER_KEYWORDS = re.compile(
    r"^(第\s*[一二三四五六七八九十百零\d]+\s*[章篇部])|^(Chapter\s+\d+)|^(Part\s+\d+)",
    re.IGNORECASE,
)
# ---- 跳过的元章节（封面/版权/前言/目录/索引等） ----
SKIP_TITLE_PATTERNS = [
    "封面", "书名", "版权", "编委", "使用说明", "序言", "序",
    "教材修订", "主审简介", "主编简介", "副主编简介",
    "前言", "目录", "索引", "缩略语", "缩写", "致谢",
]


def _make_id(prefix: str, payload: str) -> str:
    return f"{prefix}_{hashlib.md5(payload.encode('utf-8')).hexdigest()[:8]}"


def _is_real_chapter(title: str) -> bool:
    """判定是否为真正的学术章节（排除元章节）"""
    t = title.strip()
    if not t:
        return False
    for skip in SKIP_TITLE_PATTERNS:
        if skip in t and len(t) <= len(skip) + 4:
            return False
    return True


def parse_textbook(filepath: str | Path, *, given_title: str | None = None) -> Textbook:
    p = Path(filepath)
    ext = p.suffix.lower().lstrip(".")
    title = given_title or p.stem

    if ext == "pdf":
        chapters, total_pages, total_chars = _parse_pdf(p)
        fmt = "pdf"
    elif ext in ("md", "markdown"):
        md = p.read_text(encoding="utf-8")
        chapters = _split_chapters_from_markdown(md)
        total_pages = 0
        total_chars = sum(c.char_count for c in chapters) or len(md)
        fmt = "md"
    elif ext == "txt":
        md = p.read_text(encoding="utf-8")
        chapters = _split_chapters_from_markdown(md)
        total_pages = 0
        total_chars = sum(c.char_count for c in chapters) or len(md)
        fmt = "txt"
    elif ext == "docx":
        md = _parse_docx(p)
        chapters = _split_chapters_from_markdown(md)
        total_pages = 0
        total_chars = sum(c.char_count for c in chapters) or len(md)
        fmt = "docx"
    else:
        raise ValueError(f"不支持的文件格式：.{ext}（支持 pdf/md/txt/docx）")

    return Textbook(
        textbook_id=_make_id("book", str(p) + str(p.stat().st_mtime)),
        filename=p.name,
        title=title,
        file_format=fmt,  # type: ignore[arg-type]
        total_pages=total_pages,
        total_chars=total_chars,
        chapters=chapters,
        parse_status=ParseStatus.DONE,
    )


# ============== PDF ==============

def _parse_pdf(p: Path) -> tuple[list[Chapter], int, int]:
    """优先使用 PDF 内置 TOC 切章节；正文用 PyMuPDF4LLM 转 Markdown"""
    import fitz  # type: ignore[import]

    with fitz.open(str(p)) as doc:
        total_pages = doc.page_count
        toc = doc.get_toc()  # list of [level, title, page] (1-indexed)

    # Strategy A: 用 L1 章节切分（仅保留含「章/篇/部分/Chapter/Part」的真章节）
    real_chapters: list[tuple[str, int]] = []  # (title, page)
    for level, title, page in toc:
        if level != 1:
            continue
        if not _is_real_chapter(title):
            continue
        if not (CHAPTER_KEYWORDS.search(title.strip()) or title.strip().startswith(("绪论", "总论"))):
            # L1 不含章节关键字，可能是"附录""参考文献"，跳过
            continue
        real_chapters.append((title.strip(), page))

    # 如果 L1 章节太少，回退取所有 L1 entry（不含元页）
    if len(real_chapters) < 2:
        real_chapters = [
            (t.strip(), pg) for lvl, t, pg in toc
            if lvl == 1 and _is_real_chapter(t)
        ]

    # 仍然太少，回退到 Markdown 标题策略
    if len(real_chapters) < 2:
        import pymupdf4llm
        md = pymupdf4llm.to_markdown(str(p))
        return _split_chapters_from_markdown(md), total_pages, len(md)

    # 计算每章页范围
    chapter_pages: list[tuple[str, int, int]] = []  # (title, start, end)
    for i, (title, start) in enumerate(real_chapters):
        end = real_chapters[i + 1][1] - 1 if i + 1 < len(real_chapters) else total_pages
        chapter_pages.append((title, start, end))

    # 用 PyMuPDF4LLM 按页范围抽 Markdown
    import pymupdf4llm
    chapters: list[Chapter] = []
    total_chars = 0
    for idx, (title, start, end) in enumerate(chapter_pages):
        # PyMuPDF4LLM 的 pages 参数是 0-indexed 列表
        page_list = list(range(start - 1, min(end, total_pages)))
        if not page_list:
            continue
        try:
            md = pymupdf4llm.to_markdown(str(p), pages=page_list, show_progress=False)
        except TypeError:
            # 老版本不支持 show_progress
            md = pymupdf4llm.to_markdown(str(p), pages=page_list)
        chapters.append(Chapter(
            chapter_id=f"ch_{idx + 1:03d}",
            title=title[:100],
            page_start=start,
            page_end=end,
            content=md.strip(),
            char_count=len(md.strip()),
        ))
        total_chars += len(md.strip())

    return chapters, total_pages, total_chars


# ============== DOCX ==============

def _parse_docx(p: Path) -> str:
    import docx  # python-docx
    doc = docx.Document(str(p))
    out: list[str] = []
    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        style = (para.style.name or "").lower()
        if "heading 1" in style:
            out.append(f"# {text}")
        elif "heading 2" in style:
            out.append(f"## {text}")
        elif "heading 3" in style:
            out.append(f"### {text}")
        else:
            out.append(text)
    return "\n\n".join(out)


# ============== 章节切分（Markdown 兜底策略） ==============

MD_HEADING = re.compile(r"^(#{1,3})\s+(.+?)\s*$", re.MULTILINE)


def _split_chapters_from_markdown(markdown: str) -> list[Chapter]:
    """从 Markdown 文本切分章节（用于 .md/.txt/.docx 或 PDF TOC 不可用时）"""
    h1 = [(m.start(), m.group(2).strip()) for m in MD_HEADING.finditer(markdown)
          if len(m.group(1)) == 1]
    if len(h1) < 2:
        h2 = [(m.start(), m.group(2).strip()) for m in MD_HEADING.finditer(markdown)
              if len(m.group(1)) == 2]
        if len(h2) >= 2:
            h1 = h2

    if not h1:
        return [Chapter(
            chapter_id="ch_001", title="全文", content=markdown,
            char_count=len(markdown), page_start=1,
        )]

    chapters: list[Chapter] = []
    for idx, (pos, title) in enumerate(h1):
        end = h1[idx + 1][0] if idx + 1 < len(h1) else len(markdown)
        body = markdown[pos:end].strip()
        chapters.append(Chapter(
            chapter_id=f"ch_{idx + 1:03d}",
            title=title[:100],
            content=body,
            char_count=len(body),
        ))
    return chapters
