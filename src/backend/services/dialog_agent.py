"""Lightweight teacher dialog agent for integration decisions and RAG."""
from __future__ import annotations

import re
import uuid

from ..models.schemas import ChatMessage
from . import store
from .answerer import answer_question


def handle_message(session_id: str | None, content: str) -> dict:
    sid = session_id or f"session_{uuid.uuid4().hex[:8]}"
    user_msg = ChatMessage(role="user", content=content)
    store.append_chat_message(sid, user_msg)

    reply, tool = _route(content)
    assistant_msg = ChatMessage(role="assistant", content=reply, tool_name=tool)
    store.append_chat_message(sid, assistant_msg)

    return {
        "session_id": sid,
        "reply": reply,
        "tool_name": tool,
        "history": [m.model_dump() for m in store.list_chat_messages(sid)],
    }


def history(session_id: str) -> dict:
    return {"session_id": session_id, "history": [m.model_dump() for m in store.list_chat_messages(session_id)]}


def _route(content: str) -> tuple[str, str]:
    if any(word in content for word in ("为什么", "解释", "原因")):
        found = _find_decision(content)
        if found:
            return f"这条决策的理由是：{found['reason']}", "explain_decision"

    if any(word in content for word in ("保留", "不要删除", "不删除")):
        found = _find_decision(content)
        if found:
            reason = f"{found['reason']} 教师反馈：要求保留该知识点，系统已将决策调整为 keep。"
            store.update_integration_decision_action(found["decision_id"], "keep", reason, 0.96)
            return f"已更新：{found['decision_id']} 调整为 keep。", "modify_decision"

    if any(word in content for word in ("不要合并", "分开", "拆开", "不是同一个")):
        found = _find_decision(content, prefer_action="merge")
        if found:
            reason = f"{found['reason']} 教师反馈：要求拆分该合并簇，系统已取消 merge 并转为 keep。"
            store.update_integration_decision_action(found["decision_id"], "keep", reason, 0.96)
            return f"已更新：{found['decision_id']} 已由 merge 调整为 keep。", "modify_decision"

    if content.strip().endswith("?") or "？" in content or any(w in content for w in ("什么", "如何", "请问")):
        ans = answer_question(content)
        return ans.answer, "query_rag"

    latest = store.get_integration_run()
    if latest:
        stats = latest["stats"]
        return (
            f"当前整合结果：{stats.original_textbooks} 本教材，"
            f"{stats.decisions_merge} 条 merge、{stats.decisions_keep} 条 keep、"
            f"{stats.decisions_remove} 条 remove，压缩比 {stats.compression_ratio:.1%}。"
        ), "summarize_integration"
    return "当前还没有整合结果。请先运行 Phase 3 跨教材整合。", "summarize_integration"


def _find_decision(content: str, prefer_action: str | None = None) -> dict | None:
    decisions = store.list_integration_decisions()
    if prefer_action:
        decisions = [d for d in decisions if d["action"] == prefer_action]
    if not decisions:
        return None

    explicit = re.search(r"(run_[A-Za-z0-9_]+|manual_[A-Za-z0-9_]+|[A-Za-z0-9_]+_(?:merge|keep|remove)_\d{4})", content)
    if explicit:
        needle = explicit.group(1)
        for d in decisions:
            if needle in d["decision_id"]:
                return d

    linked = re.findall(r"\[\[([^\]]+)\]\]", content)
    terms = linked or re.findall(r"[\u4e00-\u9fa5A-Za-z]{2,12}", content)
    for term in terms:
        for d in decisions:
            haystack = f"{d['reason']} {' '.join(d.get('source_refs', []))}"
            if term and term in haystack:
                return d
    return decisions[0]
