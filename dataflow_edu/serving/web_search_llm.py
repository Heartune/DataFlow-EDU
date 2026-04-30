# -*- coding: utf-8 -*-
"""
联网 LLM 客户端：默认复用 ``LLM_PROVIDERS["blt"]`` provider，依赖模型自带搜索能力。

设计要点（详见 agent_notes.md「联网 LLM 与素养建议」一节）：
- 不引入 Tavily / Bing / SerpAPI 等外部检索 SDK，全部靠默认 provider 上具备
  原生联网能力的模型（如 gemini-3-flash-preview-nothinking / Pro 系）按 system prompt 自行检索。
- API key 一律从环境变量 ``LLM_API_KEY`` 读取（与 ``task_runner`` 的 BYOK
  链路一致），不会触发交互式 ``interactive_config_llm``。
- 模型选择优先级：函数入参 > ``.llm_config.json::llm_model_blt`` > 内置默认
  ``gemini-3-flash-preview-nothinking``。

stdout / stderr 协议：调用方（CLI / Operator）需自行序列化结果，本模块仅返回
原始字符串（或 ``None``），与现有 ``call_llm`` 行为对齐。
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Optional

import httpx
from openai import OpenAI

from dataflow_edu.serving.llm_client import LLM_PROVIDERS

DEFAULT_MODEL = "gemini-3-flash-preview-nothinking"
DEFAULT_PROVIDER = "blt"
DEFAULT_TIMEOUT = 60
DEFAULT_RETRIES = 2

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_CONFIG_FILE = _PROJECT_ROOT / ".llm_config.json"


def _load_saved_model() -> Optional[str]:
    """读取 ``.llm_config.json`` 中默认 provider 的模型选项；不存在或损坏返回 None。"""
    if not _CONFIG_FILE.exists():
        return None
    try:
        with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        return None
    # original: val = cfg.get("llm_model_zgca")
    val = cfg.get(f"llm_model_{DEFAULT_PROVIDER}")
    return val if isinstance(val, str) and val.strip() else None


def _resolve_model(model: Optional[str]) -> str:
    if model and model.strip():
        return model.strip()
    saved = _load_saved_model()
    if saved:
        return saved
    return DEFAULT_MODEL


def _resolve_api_key() -> str:
    # 与 task_runner 注入的 env 变量名对齐，覆盖几个常见命名以便复用相同 BYOK 头
    # original: ("LLM_API_KEY", "LLM_ZGCA_API_KEY", "OPENAI_API_KEY")
    for key in ("LLM_API_KEY", "LLM_BLT_API_KEY", "LLM_ZGCA_API_KEY", "OPENAI_API_KEY"):
        v = os.getenv(key)
        if v and v.strip():
            return v.strip()
    return ""


def _build_client(api_key: str, timeout: int) -> OpenAI:
    # original: provider = LLM_PROVIDERS["zgca"]
    provider = LLM_PROVIDERS[DEFAULT_PROVIDER]
    base_url = provider["base_url"]
    return OpenAI(
        api_key=api_key,
        base_url=base_url,
        timeout=timeout,
        http_client=httpx.Client(timeout=timeout),
    )


WEB_SEARCH_HINT = (
    "你是一名熟悉中国基础教育课程标准的研究助理。"
    "请使用你内置的网络搜索 / 联网检索能力（务必检索最新课程标准、教育部官方文件、"
    "学科课程标准修订版本，例如《普通高中XX课程标准（2017年版2020年修订）》或义务教育课程标准），"
    "并基于检索证据给出答案。"
    "请只输出严格符合用户要求的 JSON，不要包含任何解释性文字、Markdown 围栏或额外注释。"
)


def call_web_search_llm(
    system_prompt: str,
    user_prompt: str,
    *,
    model: Optional[str] = None,
    max_tokens: int = 2048,
    temperature: float = 0.3,
    timeout: int = DEFAULT_TIMEOUT,
    max_retries: int = DEFAULT_RETRIES,
) -> Optional[str]:
    """以默认 provider 调用具备联网能力的模型。

    - ``system_prompt`` 会被前置 ``WEB_SEARCH_HINT``，强化「调用联网能力」的指令。
    - 失败重试 ``max_retries`` 次，最终失败返回 ``None``。
    """
    api_key = _resolve_api_key()
    if not api_key:
        return None
    actual_model = _resolve_model(model)

    merged_system = WEB_SEARCH_HINT + "\n\n" + (system_prompt or "")
    messages = [
        {"role": "system", "content": merged_system},
        {"role": "user", "content": user_prompt},
    ]

    last_err: Optional[Exception] = None
    for attempt in range(max_retries + 1):
        try:
            client = _build_client(api_key, timeout)
            resp = client.chat.completions.create(
                model=actual_model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                timeout=timeout,
                stream=False,
            )
            content = resp.choices[0].message.content
            if isinstance(content, str) and content.strip():
                return content.strip()
            return None
        except Exception as e:  # noqa: BLE001
            last_err = e
            if attempt < max_retries:
                time.sleep(2 * (attempt + 1))
            continue
    # 调用方负责日志，stderr 由上层 CLI 决定输出格式
    if last_err is not None:
        # 把最后一次错误暴露到一个固定 env 变量，方便 CLI/Operator 再读取
        os.environ.setdefault(
            "DATAFLOW_EDU_LAST_WEB_SEARCH_ERROR", f"{type(last_err).__name__}: {last_err}"
        )
    return None


__all__ = [
    "DEFAULT_MODEL",
    "WEB_SEARCH_HINT",
    "call_web_search_llm",
]
