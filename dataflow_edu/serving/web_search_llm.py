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

import requests

DEFAULT_MODEL = "gemini-3-flash-preview-nothinking"
DEFAULT_PROVIDER = "blt"
DEFAULT_TIMEOUT = 60
DEFAULT_RETRIES = 2

PROVIDER_BASE_URLS = {
    "zaiwen": "https://back.zaiwenai.com/api/v1/ai",
    "zgca": "http://35.220.164.252:3888/v1",
    "gptagent": "https://gpt-agent.cc/v1",
    "aiping": "https://www.aiping.cn/api/v1",
    "blt": "https://api.bltcy.ai/v1",
    "openrouter_official": "https://openrouter.ai/api/v1",
    "openrouter": "https://openrouter.fans/v1",
    "xiaoai": "https://xiaoai.plus/v1/",
    "qiniu": "https://api.qnaigc.com/v1",
    "iflytek": "https://maas-api.cn-huabei-1.xf-yun.com/v2",
    "openai": "https://api.openai.com/v1",
    "dashscope": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "volcengine": "https://ark.cn-beijing.volces.com/api/v3",
}

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
    env_model = os.getenv("DATAFLOW_LLM_MODEL")
    if env_model and env_model.strip():
        return env_model.strip()
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


def _resolve_provider() -> str:
    return (os.getenv("DATAFLOW_LLM_PROVIDER") or DEFAULT_PROVIDER).strip().lower() or DEFAULT_PROVIDER


def _resolve_base_url() -> str:
    provider = _resolve_provider()
    env_base_url = os.getenv("DATAFLOW_LLM_BASE_URL")
    if env_base_url and env_base_url.strip():
        return env_base_url.strip().rstrip("/")
    return PROVIDER_BASE_URLS.get(provider, PROVIDER_BASE_URLS[DEFAULT_PROVIDER]).rstrip("/")


def _post_chat_completion(
    api_key: str,
    messages: list[dict[str, str]],
    *,
    model: str,
    max_tokens: int,
    temperature: float,
    timeout: int,
) -> Optional[str]:
    url = f"{_resolve_base_url()}/chat/completions"
    resp = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    return content.strip() if isinstance(content, str) and content.strip() else None


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
            content = _post_chat_completion(
                api_key,
                messages,
                model=actual_model,
                max_tokens=max_tokens,
                temperature=temperature,
                timeout=timeout,
            )
            return content
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
