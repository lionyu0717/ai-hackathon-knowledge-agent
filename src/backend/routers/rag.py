"""RAG indexing and query routes."""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel

from ..services import store
from ..services.answerer import answer_question
from ..services.rag_index import rebuild_index

router = APIRouter(prefix="/api/rag", tags=["rag"])


class RagIndexRequest(BaseModel):
    textbook_ids: list[str] = []


class RagQueryRequest(BaseModel):
    question: str
    top_k: int = 5


_index_state: dict = {"status": "idle"}


def _do_index(textbook_ids: list[str]) -> None:
    global _index_state
    try:
        _index_state = {"status": "running"}
        status = rebuild_index(textbook_ids or None)
        _index_state = {"status": "ready", **status}
    except Exception as exc:
        _index_state = {"status": "failed", "error": str(exc)[:500]}


@router.post("/index")
def start_index(req: RagIndexRequest, background_tasks: BackgroundTasks) -> dict:
    background_tasks.add_task(_do_index, req.textbook_ids)
    _index_state.update({"status": "queued"})
    return {"started": True, "textbook_ids": req.textbook_ids}


@router.post("/index/sync")
def run_index_sync(req: RagIndexRequest) -> dict:
    status = rebuild_index(req.textbook_ids or None)
    _index_state.update({"status": "ready", **status})
    return _index_state


@router.get("/status")
def get_status() -> dict:
    persisted = store.get_rag_status()
    if _index_state.get("status") in {"queued", "running", "failed"}:
        return {**persisted, **_index_state}
    return persisted


@router.post("/query")
def query(req: RagQueryRequest) -> dict:
    return answer_question(req.question, top_k=req.top_k).model_dump()
