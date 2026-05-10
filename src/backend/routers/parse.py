"""上传与解析路由

POST /api/upload         多文件上传，后台异步解析
GET  /api/textbooks      列出已上传教材（带解析状态）
GET  /api/textbooks/{id} 单本教材详情
GET  /api/textbooks/{id}/chapters 章节列表
DELETE /api/textbooks/{id}
"""
from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile

from ..models.schemas import (
    Chapter, ParseStatus, Textbook, TextbookSummary,
)
from ..services import store
from ..services.parser import parse_textbook

router = APIRouter(prefix="/api", tags=["parse"])

UPLOAD_DIR = Path("data/textbooks")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_EXT = {".pdf", ".md", ".markdown", ".txt", ".docx"}


def _do_parse(filepath: Path, given_title: str, placeholder_id: str) -> None:
    """后台任务：实际解析 + 存库。失败时更新 status=failed"""
    try:
        tb = parse_textbook(filepath, given_title=given_title)
        # 用 placeholder_id 覆盖（让前端能用最初返回的 id 查状态）
        tb.textbook_id = placeholder_id
        store.upsert_textbook(tb)
    except Exception as e:
        store.update_textbook_status(placeholder_id, ParseStatus.FAILED, str(e)[:500])


@router.post("/upload")
async def upload_files(
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
) -> dict:
    """接受多文件上传，立刻返回 task 列表，后台异步解析"""
    if not files:
        raise HTTPException(400, "no files provided")

    accepted: list[dict] = []
    for f in files:
        ext = Path(f.filename or "").suffix.lower()
        if ext not in ALLOWED_EXT:
            accepted.append({"filename": f.filename, "status": "rejected",
                              "reason": f"unsupported format {ext}"})
            continue

        # 保存文件到 data/textbooks
        target = UPLOAD_DIR / (f.filename or "untitled")
        with target.open("wb") as out:
            shutil.copyfileobj(f.file, out)

        # 注册一个 PENDING 记录（让前端能 poll 状态）
        title = Path(f.filename or "").stem
        placeholder = Textbook(
            textbook_id=f"book_{abs(hash(str(target) + str(target.stat().st_mtime))) % (10**8):08x}",
            filename=f.filename or "untitled",
            title=title,
            file_format=ext.lstrip("."),  # type: ignore[arg-type]
            parse_status=ParseStatus.PARSING,
        )
        store.upsert_textbook(placeholder)

        # 后台启动解析
        background_tasks.add_task(_do_parse, target, title, placeholder.textbook_id)
        accepted.append({"filename": f.filename, "status": "accepted",
                          "textbook_id": placeholder.textbook_id})

    return {"files": accepted}


@router.get("/textbooks", response_model=list[TextbookSummary])
def list_textbooks() -> list[TextbookSummary]:
    return store.list_textbooks()


@router.get("/textbooks/{textbook_id}", response_model=Textbook)
def get_textbook(textbook_id: str) -> Textbook:
    tb = store.get_textbook(textbook_id)
    if not tb:
        raise HTTPException(404, "textbook not found")
    return tb


@router.get("/textbooks/{textbook_id}/chapters", response_model=list[Chapter])
def list_chapters(textbook_id: str) -> list[Chapter]:
    chs = store.list_chapters(textbook_id)
    if not chs:
        # 检查是不是教材本身不存在
        if not store.get_textbook(textbook_id):
            raise HTTPException(404, "textbook not found")
    return chs


@router.get("/textbooks/{textbook_id}/chapters/{chapter_id}", response_model=Chapter)
def get_chapter(textbook_id: str, chapter_id: str) -> Chapter:
    ch = store.get_chapter(textbook_id, chapter_id)
    if not ch:
        if not store.get_textbook(textbook_id):
            raise HTTPException(404, "textbook not found")
        raise HTTPException(404, "chapter not found")
    return ch


@router.delete("/textbooks/{textbook_id}")
def delete_textbook(textbook_id: str) -> dict:
    store.delete_textbook(textbook_id)
    return {"deleted": textbook_id}
