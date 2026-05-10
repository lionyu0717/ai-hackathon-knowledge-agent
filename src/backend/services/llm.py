"""LLM 客户端封装

使用 ModelScope 推理 API（OpenAI 兼容协议），优先调用平台免费额度模型。
当免费 API-Inference 触发限流/额度限制时，可通过 “模型ID:外部提供方”
继续走魔搭平台 Token 鉴权，例如 deepseek-ai/DeepSeek-V3.2:DeepSeek。

接入方式：
    from .llm import get_client, chat_json, chat_text, MODEL
"""
from __future__ import annotations

import os
import logging
from functools import lru_cache
from typing import Any

from openai import OpenAI

DEFAULT_BASE_URL = "https://api-inference.modelscope.cn/v1/"
DEFAULT_MODEL = "Qwen/Qwen3-235B-A22B"
DEFAULT_FALLBACK_MODELS = "Qwen/Qwen3-30B-A3B,deepseek-ai/DeepSeek-V3.2"

logger = logging.getLogger(__name__)


def _api_key() -> str:
    key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("MODELSCOPE_ACCESS_TOKEN")
    if not key:
        raise RuntimeError(
            "DEEPSEEK_API_KEY 或 MODELSCOPE_ACCESS_TOKEN 均未配置。"
            "本地：在 .env 设置；魔搭部署：在 Studio Settings → Secrets 添加。"
        )
    return key


@lru_cache(maxsize=1)
def get_client() -> OpenAI:
    base_url = os.getenv("LLM_BASE_URL", DEFAULT_BASE_URL)
    logger.info("[llm] connecting to %s with model %s", base_url, MODEL)
    return OpenAI(
        api_key=_api_key(),
        base_url=base_url,
        timeout=120.0,
    )


MODEL = os.getenv("LLM_MODEL", DEFAULT_MODEL)


def _models_to_try() -> list[str]:
    fallbacks = [
        item.strip()
        for item in os.getenv("LLM_FALLBACK_MODELS", DEFAULT_FALLBACK_MODELS).split(",")
        if item.strip()
    ]
    out: list[str] = []
    for model in [MODEL, *fallbacks]:
        if model not in out:
            out.append(model)
    return out


def _should_try_fallback(exc: Exception) -> bool:
    text = str(exc).lower()
    if "未配置" in str(exc) or "access_token" in text:
        return False
    return any(key in text for key in (
        "429", "rate limit", "quota", "exceeded", "unavailable",
        "not found", "model", "temporarily",
    ))


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

    last_exc: Exception | None = None
    for idx, model in enumerate(_models_to_try()):
        try:
            resp = get_client().chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            if not resp.choices:
                raise RuntimeError(f"模型 {model} 返回空 choices（可能额度用尽或模型不可用）")
            content = resp.choices[0].message.content or ""
            if not content.strip():
                raise RuntimeError(f"模型 {model} 返回空内容")
            return content.strip()
        except Exception as exc:
            last_exc = exc
            if idx >= len(_models_to_try()) - 1 or not _should_try_fallback(exc):
                raise
            logger.warning("[llm] model %s failed, trying fallback: %s", model, exc)

    assert last_exc is not None
    raise last_exc


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

    sys_msg = (system or "") + "\n严格输出合法 JSON，禁止包裹任何解释、注释或代码块标记。/no_think"
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
