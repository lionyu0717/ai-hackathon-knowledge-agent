"""Markdown report routes for the right-side report panel."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/reports", tags=["reports"])

ROOT_DIR = Path(__file__).resolve().parents[3]

REPORTS: dict[str, tuple[str, Path]] = {
    "integration": ("整合报告", ROOT_DIR / "report" / "整合报告.md"),
    "essence": ("精华教材", ROOT_DIR / "report" / "精华教材.md"),
    "requirements": ("需求分析", ROOT_DIR / "docs" / "需求分析.md"),
    "design": ("系统设计", ROOT_DIR / "docs" / "系统设计.md"),
    "agent": ("Agent 架构说明", ROOT_DIR / "docs" / "Agent架构说明.md"),
    "p2": ("P2 技术报告", ROOT_DIR / "docs" / "P2-技术报告.md"),
    "api": ("接口文档", ROOT_DIR / "docs" / "接口文档.md"),
    "scorecard": ("评分自检表", ROOT_DIR / "docs" / "评分自检表.md"),
}


@router.get("")
def list_reports() -> dict:
    return {
        "reports": [
            {"id": key, "title": title, "available": path.exists()}
            for key, (title, path) in REPORTS.items()
        ]
    }


@router.get("/{report_id}")
def get_report(report_id: str) -> dict:
    item = REPORTS.get(report_id)
    if not item:
        raise HTTPException(404, "report not found")
    title, path = item
    if not path.exists():
        raise HTTPException(404, f"{title} not found")
    return {"id": report_id, "title": title, "markdown": path.read_text(encoding="utf-8")}
