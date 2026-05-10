"""LLM 客户端封装

使用 ModelScope 推理 API（OpenAI 兼容协议），免费额度内调用 DeepSeek-V3.2。
同一个 MODELSCOPE_ACCESS_TOKEN 同时用于 Studio 部署和 LLM 调用。

接入方式：
    from .llm import get_client, chat_json, chat_text, MODEL
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from openai import OpenAI

DEFAULT_BASE_URL = "https://api-inference.modelscope.cn/v1/"
DEFAULT_MODEL = "deepseek-ai/DeepSeek-V3.2"


def _api_key() -> str:
    key = os.getenv("MODELSCOPE_ACCESS_TOKEN")
    if not key:
        raise RuntimeError(
            "MODELSCOPE_ACCESS_TOKEN 未配置。本地：在 .env 设置；"
            "魔搭部署：在 Studio Settings → Secrets 添加。"
        )
    return key


@lru_cache(maxsize=1)
def get_client() -> OpenAI:
    return OpenAI(
        api_key=_api_key(),
        base_url=os.getenv("LLM_BASE_URL", DEFAULT_BASE_URL),
        timeout=120.0,
    )


MODEL = os.getenv("LLM_MODEL", DEFAULT_MODEL)


def chat_text(
    user: str,
    system: str | None = None,
    *,
    temperature: float = 0.2,
    max_tokens: int = 1024,
) -> str:
    """单轮文本对话，返回纯文本"""
    messages: list[dict[str, Any]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": user})

    resp = get_client().chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return (resp.choices[0].message.content or "").strip()


def chat_json(
    user: str,
    system: str | None = None,
    *,
    temperature: float = 0.1,
    max_tokens: int = 2048,
) -> Any:
    """请求 LLM 返回 JSON，宽松解析（兼容代码块包裹与前后多余字符）"""
    import json
    import re

    sys_msg = (system or "") + "\n严格输出合法 JSON，禁止包裹任何解释、注释或代码块标记。"
    raw = chat_text(user, sys_msg.strip(), temperature=temperature, max_tokens=max_tokens)

    # 去掉常见 ```json ... ``` 包装
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.MULTILINE)
    # 截取首个 { 或 [ 到对应结尾
    m = re.search(r"[\{\[]", raw)
    if m:
        raw = raw[m.start():]
        # 反向找到最后一个 } 或 ]
        last = max(raw.rfind("}"), raw.rfind("]"))
        if last >= 0:
            raw = raw[: last + 1]

    return json.loads(raw)
