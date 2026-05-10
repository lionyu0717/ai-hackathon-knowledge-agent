"""文档解析器：PDF / Markdown / TXT / DOCX → 统一 Markdown + 章节结构

赛题验收标准（P0-1）：
  「上传一本 PDF 教材后，系统能正确识别出章节结构并显示在前端」
  PDF 必须处理：章节标题识别、页眉页脚过滤、图表区域跳过、逐页处理、不一次性入内存。

设计：4 级 cascade，确保任何 PDF 都能切出有意义的 sections —— 即便完全没有结构。

  Strategy 1 — PDF 内置 TOC（书签）
    最准；过滤元页（封面/版权/前言/目录），优先选含「章/篇/部分/Chapter/Part」的 L1，
    若不足则取所有非元页 L1，再否则取 L2。

  Strategy 2 — Markdown 标题（PyMuPDF4LLM 转出后的 # / ##）
    PDF 字号大的部分会被 PyMuPDF4LLM 标为 H1/H2；适用于无 TOC 但布局清晰的书。

  Strategy 3 — 文本正则（行首「第X章/篇」）
    严格要求标题独占一行，避免命中正文里的交叉引用「第六章）」。

  Strategy 4 — 等量分页兜底
    每 N 页一段（默认 30 页/章），保证下游 chunking 与图谱构建有稳定输入。

输出统一 Textbook (JSON)：chapters[] 每条含 title / page_start / page_end / content (markdown)。
内容是 Markdown，因为：① 保留段落/列表/小标题语义边界，利于后续 chunking 切分；
② 引用展示也好读；③ JSON 包装让 schema 稳定。
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from ..models.schemas import Chapter, Textbook, ParseStatus

# ---- 章节标题关键字（兼容章/篇/部分） ----
CHAPTER_KEYWORD = re.compile(
    r"^(第\s*[一二三四五六七八九十百零\d]+\s*[章篇部])"
    r"|^(Chapter\s+\d+)"
    r"|^(Part\s+\d+)"
    r"|^(绪论|总论|导论)$",
    re.IGNORECASE,
)

# ---- 严格的「行首章节」正则：要求标题独占一行 ----
LINE_CHAPTER = re.compile(
    r"(?m)^[\s#*]{0,8}(第\s*[一二三四五六七八九十百零\d]+\s*章[^\n（）()]{0,60})$"
)

# ---- 元章节（封面/版权/前言/目录等，不计入正文） ----
SKIP_KEYWORDS = (
    "封面", "书名", "版权", "编委", "使用说明", "序言", "教材修订",
    "主审简介", "主编简介", "副主编简介", "前言", "目录", "索引",
    "缩略语", "缩写", "致谢", "参考文献",
)

# ---- 兜底分页大小 ----
FALLBACK_PAGES_PER_SECTION = 30


def _make_id(prefix: str, payload: str) -> str:
    return f"{prefix}_{hashlib.md5(payload.encode('utf-8')).hexdigest()[:8]}"


def _norm(s: str) -> str:
    """归一化标题：去 \r\n 全角空格 末尾标点"""
    return re.sub(r"\s+", " ", s.replace("\r", "").replace("　", " ")).strip()


def _is_skip_meta(title: str) -> bool:
    t = _norm(title)
    if len(t) > 30:
        return False
    return any(k in t for k in SKIP_KEYWORDS)


# ============== 入口 ==============

def parse_textbook(filepath: str | Path, *, given_title: str | None = None) -> Textbook:
    p = Path(filepath)
    ext = p.suffix.lower().lstrip(".")
    title = given_title or p.stem

    if ext == "pdf":
        chapters, total_pages, total_chars, strategy_used = _parse_pdf(p)
        fmt = "pdf"
    elif ext in ("md", "markdown"):
        md = p.read_text(encoding="utf-8")
        chapters, strategy_used = _split_from_markdown(md), "md_headings"
        total_pages = 0
        total_chars = sum(c.char_count for c in chapters) or len(md)
        fmt = "md"
    elif ext == "txt":
        md = p.read_text(encoding="utf-8")
        chapters, strategy_used = _split_from_markdown(md), "txt_headings"
        total_pages = 0
        total_chars = sum(c.char_count for c in chapters) or len(md)
        fmt = "txt"
    elif ext == "docx":
        md = _parse_docx(p)
        chapters, strategy_used = _split_from_markdown(md), "docx_headings"
        total_pages = 0
        total_chars = sum(c.char_count for c in chapters) or len(md)
        fmt = "docx"
    else:
        raise ValueError(f"不支持的文件格式：.{ext}（支持 pdf/md/txt/docx）")

    print(f"[parser] {p.name}: strategy={strategy_used}, chapters={len(chapters)}, "
          f"chars={total_chars}", flush=True)

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


# ============== PDF：四级 cascade ==============

def _parse_pdf(p: Path) -> tuple[list[Chapter], int, int, str]:
    import fitz  # type: ignore[import]

    with fitz.open(str(p)) as doc:
        total_pages = doc.page_count
        toc = doc.get_toc()  # [[level, title, page], ...] 1-indexed page

    # 归一化 + 去元章节
    clean_toc = [(lv, _norm(t), pg) for lv, t, pg in toc if _norm(t)]
    clean_toc = [(lv, t, pg) for lv, t, pg in clean_toc if not _is_skip_meta(t)]

    # ---- Strategy 1: TOC ----
    chapter_pages = _select_toc_chapters(clean_toc)
    if len(chapter_pages) >= 2:
        chapters, total_chars = _extract_by_pages(p, chapter_pages, total_pages)
        if chapters:
            return chapters, total_pages, total_chars, "pdf_toc"

    # 转 Markdown 一次（Strategy 2/3 共用）
    import pymupdf4llm
    try:
        md_full = pymupdf4llm.to_markdown(str(p), show_progress=False)
    except TypeError:
        md_full = pymupdf4llm.to_markdown(str(p))

    # ---- Strategy 2: Markdown 标题 ----
    md_chapters = _split_from_markdown(md_full)
    if len(md_chapters) >= 2 and not _is_single_giant(md_chapters):
        return md_chapters, total_pages, sum(c.char_count for c in md_chapters), "pdf_md_headings"

    # ---- Strategy 3: 文本正则匹配「第X章」独占一行 ----
    regex_chapters = _split_by_regex(md_full)
    if len(regex_chapters) >= 2:
        return regex_chapters, total_pages, sum(c.char_count for c in regex_chapters), "pdf_regex"

    # ---- Strategy 4: 兜底等量分页 ----
    chapters, total_chars = _split_by_pagecount(p, total_pages)
    return chapters, total_pages, total_chars, "pdf_fallback_pagecount"


def _select_toc_chapters(clean_toc: list[tuple[int, str, int]]) -> list[tuple[str, int]]:
    """从 cleaned TOC 选章节，返回 [(title, page_start), ...]
    决策：
    - 优先 L1 含章节关键字 → 用之；不足则用 L1 全部；再不足则用 L2；再不足空。
    """
    l1 = [(t, pg) for lv, t, pg in clean_toc if lv == 1]
    l2 = [(t, pg) for lv, t, pg in clean_toc if lv == 2]

    # 偏好：L1 中含「章/篇/部分」关键字的（教材主体）
    l1_chapter = [(t, pg) for t, pg in l1 if CHAPTER_KEYWORD.search(t)]
    if len(l1_chapter) >= 3:
        return l1_chapter

    # 退化：所有 L1（已剔除元章节）
    if len(l1) >= 2:
        return l1

    # 再退化：用 L2 含关键字的
    l2_chapter = [(t, pg) for t, pg in l2 if CHAPTER_KEYWORD.search(t)]
    if len(l2_chapter) >= 3:
        return l2_chapter

    # 还不行：取 L2 全部（如果数量合理 3-50）
    if 3 <= len(l2) <= 50:
        return l2

    return []


def _extract_by_pages(
    p: Path, chapter_pages: list[tuple[str, int]], total_pages: int,
) -> tuple[list[Chapter], int]:
    """按 (title, page_start) 列表逐章用 PyMuPDF4LLM 抽 Markdown"""
    import pymupdf4llm

    chapters: list[Chapter] = []
    total_chars = 0
    for idx, (title, start) in enumerate(chapter_pages):
        end = chapter_pages[idx + 1][1] - 1 if idx + 1 < len(chapter_pages) else total_pages
        page_list = list(range(start - 1, min(end, total_pages)))
        if not page_list:
            continue
        try:
            md = pymupdf4llm.to_markdown(str(p), pages=page_list, show_progress=False)
        except TypeError:
            md = pymupdf4llm.to_markdown(str(p), pages=page_list)
        body = md.strip()
        chapters.append(Chapter(
            chapter_id=f"ch_{idx + 1:03d}",
            title=title[:100],
            page_start=start,
            page_end=end,
            content=body,
            char_count=len(body),
        ))
        total_chars += len(body)
    return chapters, total_chars


# ============== Strategy 2/3：Markdown 文本切分 ==============

MD_HEADING = re.compile(r"^(#{1,3})\s+(.+?)\s*$", re.MULTILINE)


def _is_single_giant(chapters: list[Chapter]) -> bool:
    """判断是不是只切出一两个大块（说明切分失败）"""
    if not chapters:
        return True
    biggest = max(c.char_count for c in chapters)
    total = sum(c.char_count for c in chapters)
    return total > 0 and biggest / total > 0.85


def _split_from_markdown(markdown: str) -> list[Chapter]:
    """优先 H1，回退 H2"""
    h1 = [(m.start(), _norm(m.group(2))) for m in MD_HEADING.finditer(markdown) if len(m.group(1)) == 1]
    if len(h1) < 3:
        h2 = [(m.start(), _norm(m.group(2))) for m in MD_HEADING.finditer(markdown) if len(m.group(1)) == 2]
        if len(h2) >= 3:
            h1 = h2

    if len(h1) < 2:
        return [Chapter(
            chapter_id="ch_001", title="全文", content=markdown,
            char_count=len(markdown), page_start=0,
        )]

    return _build_chapters_from_positions(markdown, h1)


def _split_by_regex(markdown: str) -> list[Chapter]:
    """严格行首匹配「第X章」"""
    matches = [(m.start(), _norm(m.group(1))) for m in LINE_CHAPTER.finditer(markdown)]
    if len(matches) < 2:
        return []
    return _build_chapters_from_positions(markdown, matches)


def _build_chapters_from_positions(text: str, positions: list[tuple[int, str]]) -> list[Chapter]:
    chapters: list[Chapter] = []
    for idx, (pos, title) in enumerate(positions):
        end = positions[idx + 1][0] if idx + 1 < len(positions) else len(text)
        body = text[pos:end].strip()
        chapters.append(Chapter(
            chapter_id=f"ch_{idx + 1:03d}",
            title=title[:100],
            content=body,
            char_count=len(body),
        ))
    return chapters


# ============== Strategy 4：兜底等量分页 ==============

def _split_by_pagecount(p: Path, total_pages: int) -> tuple[list[Chapter], int]:
    """无任何结构信号时按 N 页一段切分。
    每段独立调 PyMuPDF4LLM 抽 Markdown，保证页码元数据准确。
    """
    import pymupdf4llm

    if total_pages == 0:
        return [], 0

    chapters: list[Chapter] = []
    total_chars = 0
    pages_per = FALLBACK_PAGES_PER_SECTION
    sections = (total_pages + pages_per - 1) // pages_per

    for i in range(sections):
        start = i * pages_per + 1
        end = min((i + 1) * pages_per, total_pages)
        page_list = list(range(start - 1, end))
        try:
            md = pymupdf4llm.to_markdown(str(p), pages=page_list, show_progress=False)
        except TypeError:
            md = pymupdf4llm.to_markdown(str(p), pages=page_list)
        body = md.strip()
        if not body:
            continue
        chapters.append(Chapter(
            chapter_id=f"ch_{i + 1:03d}",
            title=f"第 {start}-{end} 页",
            page_start=start,
            page_end=end,
            content=body,
            char_count=len(body),
        ))
        total_chars += len(body)
    return chapters, total_chars


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
