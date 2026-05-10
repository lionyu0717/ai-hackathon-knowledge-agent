"""Teacher dialog routes."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..services.dialog_agent import handle_message, history

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


@router.post("")
def chat(req: ChatRequest) -> dict:
    if not req.message.strip():
        raise HTTPException(400, "message is empty")
    return handle_message(req.session_id, req.message.strip())


@router.get("/{session_id}")
def get_history(session_id: str) -> dict:
    return history(session_id)
