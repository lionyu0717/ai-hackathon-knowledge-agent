"""跨教材整合路由。"""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from ..services import store
from ..services.integrator import run_integration

router = APIRouter(prefix="/api/integrate", tags=["integrate"])
logger = logging.getLogger(__name__)


class IntegrationRunRequest(BaseModel):
    textbook_ids: list[str] = []


def _do_run(run_id: str, textbook_ids: list[str]) -> None:
    try:
        store.update_integration_run(run_id, status="running")
        result = run_integration(run_id, textbook_ids or None)
        store.replace_integration_decisions(run_id, result.decisions)
        store.update_integration_run(
            run_id,
            status="done",
            stats=result.stats,
            summary_markdown=result.summary_markdown,
            error_message="",
        )
        logger.info("[integrate] %s done: %s decisions, ratio=%.3f",
                    run_id, len(result.decisions), result.stats.compression_ratio)
    except Exception as exc:
        logger.exception("[integrate] %s failed", run_id)
        store.update_integration_run(run_id, status="failed", error_message=str(exc)[:500])


@router.post("/run")
def start_integration(req: IntegrationRunRequest, background_tasks: BackgroundTasks) -> dict:
    run_id = f"run_{uuid.uuid4().hex[:10]}"
    store.create_integration_run(run_id, req.textbook_ids, status="queued")
    background_tasks.add_task(_do_run, run_id, req.textbook_ids)
    return {"started": True, "run_id": run_id, "textbook_ids": req.textbook_ids}


@router.get("/status")
def get_status(run_id: str | None = None) -> dict:
    run = store.get_integration_run(run_id)
    if not run:
        return {"status": "idle"}
    return {
        "run_id": run["run_id"],
        "status": run["status"],
        "textbook_ids": run["textbook_ids"],
        "stats": run["stats"].model_dump(),
        "error_message": run["error_message"],
        "updated_at": run["updated_at"],
    }


@router.get("/decisions")
def get_decisions(run_id: str | None = None) -> dict:
    run = store.get_integration_run(run_id)
    if not run:
        raise HTTPException(404, "integration run not found")
    return {
        "run_id": run["run_id"],
        "status": run["status"],
        "decisions": store.list_integration_decisions(run["run_id"]),
    }


@router.get("/stats")
def get_stats(run_id: str | None = None) -> dict:
    run = store.get_integration_run(run_id)
    if not run:
        raise HTTPException(404, "integration run not found")
    return {
        "run_id": run["run_id"],
        "status": run["status"],
        "stats": run["stats"].model_dump(),
    }


@router.get("/summary")
def get_summary(run_id: str | None = None) -> dict:
    run = store.get_integration_run(run_id)
    if not run:
        raise HTTPException(404, "integration run not found")
    return {
        "run_id": run["run_id"],
        "status": run["status"],
        "summary_markdown": run["summary_markdown"],
    }
