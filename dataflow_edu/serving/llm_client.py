# -*- coding: utf-8 -*-
"""
纯文本 LLM 客户端：Provider 选择、API 配置、交互式配置、带重试调用。

适用于 Generation、Ambiguity Cleaning、Balancing 等需要 LLM 的算子。
"""

import json
import os
import re
import threading
import time
import unicodedata
from pathlib import Path

from openai import OpenAI


def _display_width(s: str) -> int:
    """CJK 等宽：中文等宽字符计 2，ASCII 计 1"""
    w = 0
    for c in s:
        w += 2 if unicodedata.east_asian_width(c) in ("F", "W") else 1
    return w


def _pad_to_display(s: str, width: int) -> str:
    """按显示宽度右补空格，使括号列对齐"""
    return s + " " * max(0, width - _display_width(s))

RETRY_DELAY = 2

# ======================== 配置持久化 ========================

_GEN_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _GEN_SCRIPT_DIR.parent.parent
_CONFIG_FILE = _PROJECT_ROOT / ".llm_config.json"


def _load_config() -> dict:
    if _CONFIG_FILE.exists():
        try:
            with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_config(key: str, value):
    cfg = _load_config()
    cfg[key] = value
    try:
        with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"写入配置失败: {e}")


def _get_config(key: str, default=None):
    return _load_config().get(key, default)


# ======================== Provider 配置 ========================
# 与 utils_from_CNLaw-Bench/optimize_answers.py 中的 VLM_PROVIDERS 对齐。
# default_api_key 从 .env 环境变量读取，变量名见下方注释。

def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


def _env_list(key: str) -> list:
    val = os.getenv(key) or ""
    return [k.strip() for k in val.split(",") if k.strip()]


LLM_PROVIDERS = {
    "zaiwen": {
        "name": "Zaiwen (在问)",
        "base_url": "https://back.zaiwenai.com/api/v1/ai",
        "default_api_key": _env("LLM_ZAIWEN_API_KEY"),
        "default_concurrent": 32,
        "default_delay": 0.3,
        "default_timeout": 120,
    },
    "gptagent": {
        "name": "GPT-Agent.cc",
        "base_url": "https://gpt-agent.cc/v1",
        "default_api_key": _env("LLM_GPTAGENT_API_KEY"),
        "default_concurrent": 32,
        "default_delay": 0.3,
        "default_timeout": 120,
    },
    "aiping": {
        "name": "Aiping (爱拼)",
        "base_url": "https://www.aiping.cn/api/v1",
        "default_api_key": _env("LLM_AIPING_API_KEY"),
        "default_concurrent": 128,
        "default_delay": 0.2,
        "default_timeout": 120,
    },
    "blt": {
        "name": "BLT",
        "base_url": "https://api.bltcy.ai/v1",
        "default_api_key": _env("LLM_BLT_API_KEY"),
        "extra_api_keys": _env_list("LLM_BLT_EXTRA_API_KEYS"),
        "default_concurrent": 128,
        "default_delay": 0.2,
        "default_timeout": 120,
    },
    "openrouter_official": {
        "name": "OpenRouter (官方)",
        "base_url": "https://openrouter.ai/api/v1",
        "default_api_key": _env("LLM_OPENROUTER_OFFICIAL_API_KEY"),
        "default_concurrent": 64,
        "default_delay": 0.2,
        "default_timeout": 120,
        "default_headers": {
            "HTTP-Referer": "https://github.com/DataFlow-EDU",
            "X-Title": "DataFlow-EDU",
        },
    },
    "openrouter": {
        "name": "OpenRouter (中转)",
        "base_url": "https://openrouter.fans/v1",
        "default_api_key": _env("LLM_OPENROUTER_API_KEY"),
        "default_concurrent": 16,
        "default_delay": 1.0,
        "default_timeout": 60,
    },
    "xiaoai": {
        "name": "XiaoAI (小爱)",
        "base_url": "https://xiaoai.plus/v1/",
        "default_api_key": _env("LLM_XIAOAI_API_KEY"),
        "default_concurrent": 16,
        "default_delay": 1.0,
        "default_timeout": 120,
    },
    "qiniu": {
        "name": "Qiniu (七牛云)",
        "base_url": "https://api.qnaigc.com/v1",
        "default_api_key": _env("LLM_QINIU_API_KEY"),
        "default_concurrent": 16,
        "default_delay": 1.0,
        "default_timeout": 120,
    },
    "iflytek": {
        "name": "iFlytek (讯飞 MaaS)",
        "base_url": "https://maas-api.cn-huabei-1.xf-yun.com/v2",
        "default_api_key": _env("LLM_IFLYTEK_API_KEY"),
        "default_concurrent": 16,
        "default_delay": 1.0,
        "default_timeout": 120,
    },
    "openai": {
        "name": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "default_api_key": _env("OPENAI_API_KEY"),
        "default_concurrent": 16,
        "default_delay": 1.0,
        "default_timeout": 120,
    },
    "custom": {
        "name": "自定义 (Custom)",
        "base_url": None,
        "default_api_key": "",
        "default_concurrent": 16,
        "default_delay": 1.0,
        "default_timeout": 120,
    },
}

# Zaiwen 常用 LLM 模型列表（与 optimize_answers 中的 ZAIWEN_VLM_MODELS 对齐）
ZAIWEN_LLM_MODELS = [
    {"name": "Gemini-3.0-Flash", "in_k": 0.2, "out_k": 0.8},
    {"name": "Gemini-3.0-Pro", "in_k": 0.1, "out_k": 0.4},
    {"name": "Gemini-3.0-Pro-Thinking", "in_k": 1, "out_k": 4},
    {"name": "gemini_2_5_flash", "in_k": 0.2, "out_k": 0.8},
    {"name": "gemini_2_5_pro", "in_k": 0.2, "out_k": 0.8},
    {"name": "GPT-5.1", "in_k": 1, "out_k": 4},
    {"name": "GPT-5.2-Pro", "in_k": 5, "out_k": 20},
    {"name": "GPT-5.2-Instant", "in_k": 0.2, "out_k": 0.8},
    {"name": "gpt-4o", "in_k": 0.2, "out_k": 0.8},
    {"name": "gpt-4o-mini", "in_k": 0.2, "out_k": 0.8},
    {"name": "Claude-Sonnet-4.5", "in_k": 0.1, "out_k": 0.4},
    {"name": "Claude-Opus-4.5", "in_k": 2, "out_k": 8},
    {"name": "claude-haiku-4.5", "in_k": 0.2, "out_k": 0.8},
    {"name": "deepseek-reasoner", "in_k": 0.2, "out_k": 0.8},
    {"name": "deepseekv3", "in_k": 0.2, "out_k": 0.8},
    {"name": "Qwen-3-Max", "in_k": 0.2, "out_k": 0.8},
    {"name": "o3", "in_k": 0.3, "out_k": 1.2},
]

# 全局状态
_client: OpenAI | None = None
_api_key = os.getenv("OPENAI_API_KEY", "")
_base_url = ""
_headers: dict | None = None
_model_name = "gpt-4o-mini"
_max_workers = 8
_api_delay = 0.3
_request_timeout = 120
_max_retries = 3
_api_key_list: list[str] = []
_api_key_index = 0
_api_key_lock = threading.Lock()
_client_cache: dict[str, OpenAI] = {}


def _create_client(api_key: str, base_url: str, headers: dict | None) -> OpenAI:
    import httpx

    kwargs = {"api_key": api_key, "base_url": base_url}
    if headers:
        kwargs["default_headers"] = headers
    kwargs["http_client"] = httpx.Client()
    return OpenAI(**kwargs)


def _get_next_client() -> tuple[OpenAI, str]:
    global _api_key_index
    if len(_api_key_list) <= 1:
        return _client, _api_key_list[0][-6:] if _api_key_list else "default"
    with _api_key_lock:
        key = _api_key_list[_api_key_index % len(_api_key_list)]
        _api_key_index += 1
    if key not in _client_cache:
        _client_cache[key] = _create_client(key, _base_url, _headers)
    return _client_cache[key], f"...{key[-6:]}"


def init_client(
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    headers: dict | None = None,
    max_workers: int | None = None,
    api_delay: float | None = None,
    request_timeout: int | None = None,
    max_retries: int | None = None,
):
    """初始化 LLM 客户端。"""
    global _client, _api_key, _base_url, _headers, _model_name
    global _max_workers, _api_delay, _request_timeout, _max_retries
    global _api_key_list, _client_cache, _api_key_index

    if api_key:
        _api_key = api_key
    if base_url:
        _base_url = base_url
    if model:
        _model_name = model
    if headers is not None:
        _headers = headers
    if max_workers is not None:
        _max_workers = max_workers
    if api_delay is not None:
        _api_delay = api_delay
    if request_timeout is not None:
        _request_timeout = request_timeout
    if max_retries is not None:
        _max_retries = max_retries

    _client = _create_client(_api_key, _base_url, _headers)
    _api_key_list = [_api_key]
    _client_cache = {_api_key: _client}
    _api_key_index = 0
    return _client


def add_extra_api_keys(keys: list[str]):
    """添加额外的 API Key 用于轮换。"""
    global _api_key_list
    for k in keys:
        if k and k not in _api_key_list:
            _api_key_list.append(k)


def _fetch_model_list(api_key: str, base_url: str) -> list[str] | None:
    """从 API 获取可用模型列表"""
    try:
        temp = OpenAI(api_key=api_key, base_url=base_url, timeout=15)
        resp = temp.models.list()
        return sorted([m.id for m in resp.data]) if resp.data else None
    except Exception as e:
        print(f"获取模型列表失败: {e}")
        return None


def _display_and_pick_model(
    models: list[str],
    default_model: str | None = None,
    allow_back: bool = False,
) -> str | None:
    """显示模型列表并让用户选择"""
    print(f"\n{'=' * 60}")
    print(f"可用模型 (共 {len(models)} 个):")
    print("=" * 60)
    default_idx = -1
    for i, mid in enumerate(models):
        mark = " *" if mid == default_model else ""
        if mid == default_model:
            default_idx = i
        print(f"  {i + 1:3d}. {mid}{mark}")
    print("=" * 60)
    hint = "输入编号选择，或直接输入模型名称"
    if allow_back:
        hint += "，输入 'b' 返回重新搜索"
    default_hint = f" (直接回车使用：{default_model})" if default_model and default_idx >= 0 else ""
    while True:
        choice = input(f"{hint}{default_hint}: ").strip()
        if not choice and default_model and default_idx >= 0:
            print(f"✓ 使用已选模型: {default_model}")
            return default_model
        if not choice:
            print("输入不能为空，请重试。")
            continue
        if allow_back and choice.lower() == "b":
            return None
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(models):
                print(f"✓ 模型: {models[idx]}")
                return models[idx]
            print(f"编号超出范围 (1-{len(models)})，请重试。")
            continue
        except ValueError:
            pass
        print(f"✓ 模型: {choice}")
        return choice


def _manual_input_model(default_model: str | None, config_key: str) -> str:
    """手动输入模型名称"""
    while True:
        hint = f" (直接回车使用：{default_model})" if default_model else ""
        model = input(f"\n请输入模型名称 (如 Gemini-3.0-Flash, gpt-4o){hint}: ").strip()
        if not model and default_model:
            return default_model
        if model:
            _save_config(config_key, model)
            return model
        print("模型名称不能为空，请重试。")


def _interactive_select_zaiwen_model(default_model: str | None, config_key: str) -> str:
    """Zaiwen 专用：从预置列表选择模型"""
    print(f"\n{'=' * 70}")
    print("Zaiwen 可用 LLM 模型 (显示消耗倍率):")
    print(f"{'No.':<4} {'Model Name':<28} {'In Mult':<10} {'Out Mult':<10}")
    print("=" * 70)
    default_idx = -1
    for i, m in enumerate(ZAIWEN_LLM_MODELS):
        name = m["name"]
        mark = " *" if name == default_model else ""
        if name == default_model:
            default_idx = i
        print(f"  {i + 1:<3}. {name:28s} {m['in_k']:<10} {m['out_k']:<10}{mark}")
    print("=" * 70)
    default_hint = f" (直接回车使用：{default_model})" if default_model and default_idx >= 0 else ""
    while True:
        choice = input(
            f"请输入编号 (1-{len(ZAIWEN_LLM_MODELS)}) 或直接输入模型名{default_hint}: "
        ).strip()
        if not choice and default_model and default_idx >= 0:
            print(f"✓ 使用已选模型: {default_model}")
            return default_model
        if not choice:
            print("输入不能为空，请重试。")
            continue
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(ZAIWEN_LLM_MODELS):
                sel = ZAIWEN_LLM_MODELS[idx]["name"]
                print(f"✓ 模型: {sel}")
                _save_config(config_key, sel)
                return sel
        except ValueError:
            pass
        for m in ZAIWEN_LLM_MODELS:
            if m["name"] == choice:
                print(f"✓ 模型: {choice}")
                _save_config(config_key, choice)
                return choice
        filtered = [m for m in ZAIWEN_LLM_MODELS if choice.lower() in m["name"].lower()]
        if len(filtered) == 1:
            sel = filtered[0]["name"]
            print(f"✓ 搜索匹配: {sel}")
            _save_config(config_key, sel)
            return sel
        if filtered:
            print(f"找到 {len(filtered)} 个匹配项，请更精确输入:")
            for mm in filtered:
                print(f"  - {mm['name']}")
            continue
        print(f"✓ 模型: {choice}")
        _save_config(config_key, choice)
        return choice


def interactive_select_llm_model(
    provider: str, api_key: str, base_url: str
) -> str:
    """交互式选择 LLM 模型，与 optimize_answers 的模型列表逻辑一致"""
    config_key = f"llm_model_{provider}"
    default_model = _get_config(config_key)

    if provider == "zaiwen":
        return _interactive_select_zaiwen_model(default_model, config_key)

    # 有默认模型时，先询问是否使用，用户不使用时再获取列表
    if default_model:
        hint = input(f"\n是否使用已选模型 [{default_model}]? (y/n, 回车=y): ").strip().lower()
        if hint in ("", "y", "yes"):
            print(f"✓ 使用已选模型: {default_model}")
            return default_model

    print("\n正在获取可用模型列表...")
    models = _fetch_model_list(api_key, base_url)
    if not models:
        print("未能获取模型列表，请手动输入。")
        return _manual_input_model(default_model, config_key)

    if len(models) <= 30:
        sel = _display_and_pick_model(models, default_model=default_model)
        if sel:
            _save_config(config_key, sel)
            return sel

    print(f"\n共有 {len(models)} 个可用模型。")
    print("提示: 输入关键词搜索，输入 'all' 显示全部，或直接输入完整模型名。")
    while True:
        hint = f" (直接回车使用：{default_model})" if default_model else ""
        keyword = input(f"\n搜索模型 (关键词/模型名/all){hint}: ").strip()
        if not keyword and default_model:
            print(f"✓ 使用已选模型: {default_model}")
            return default_model
        if not keyword:
            print("输入不能为空，请重试。")
            continue
        if keyword.lower() == "all":
            sel = _display_and_pick_model(models, default_model=default_model)
            if sel:
                _save_config(config_key, sel)
                return sel
            continue
        if keyword in models:
            print(f"✓ 模型: {keyword}")
            _save_config(config_key, keyword)
            return keyword
        filtered = [m for m in models if keyword.lower() in m.lower()]
        if not filtered:
            print(f"未找到包含 '{keyword}' 的模型，请重试。")
            continue
        if len(filtered) == 1:
            print(f"✓ 模型: {filtered[0]}")
            _save_config(config_key, filtered[0])
            return filtered[0]
        sel = _display_and_pick_model(
            filtered, allow_back=True, default_model=default_model
        )
        if sel:
            _save_config(config_key, sel)
            return sel


def call_llm(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 4096,
    temperature: float = 0.3,
    max_retries: int | None = None,
) -> str | None:
    """
    纯文本 LLM 调用，带重试。
    """
    global _client, _model_name, _request_timeout, _max_retries
    retries = max_retries if max_retries is not None else _max_retries

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    for attempt in range(retries):
        try:
            cur_client, key_tag = _get_next_client()
            t0 = time.time()
            resp = cur_client.chat.completions.create(
                model=_model_name,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                timeout=_request_timeout,
                stream=False,
            )
            elapsed = time.time() - t0
            content = resp.choices[0].message.content
            if isinstance(content, str):
                content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL)
            usage = getattr(resp, "usage", None)
            finish = getattr(resp.choices[0], "finish_reason", "unknown")
            # 简单日志
            print(
                f"[API] OK | key={key_tag} | {elapsed:.2f}s | "
                f"tokens=({getattr(usage, 'prompt_tokens', '?')}/{getattr(usage, 'completion_tokens', '?')})"
            )
            return content.strip() if content else None
        except Exception as e:
            err = str(e)
            print(
                f"[API] 异常 尝试 {attempt + 1}/{retries} | {type(e).__name__}: {err[:300]}"
            )
            if "429" in err or "rate" in err.lower():
                wait = RETRY_DELAY * (attempt + 1) * 2
                print(f"限流，等待 {wait}s 后重试...")
                time.sleep(wait)
            elif attempt < retries - 1:
                time.sleep(RETRY_DELAY)
    return None


def interactive_config_llm(gen_config_max_workers: int = 8) -> bool:
    """
    交互式配置 LLM：Provider、API Key、模型、参数。
    完成后初始化客户端，返回是否成功。
    """
    global _model_name, _max_workers, _api_delay, _request_timeout, _max_retries

    provider_keys = list(LLM_PROVIDERS.keys())
    default_provider = _get_config("llm_provider") or "zaiwen"

    print("\n" + "=" * 60)
    print("请选择 LLM API Provider:")
    print("=" * 60)
    name_width = 28  # 显示宽度，使括号列对齐
    for i, key in enumerate(provider_keys):
        info = LLM_PROVIDERS[key]
        url = info.get("base_url") or "需手动输入"
        mark = " *" if key == default_provider else ""
        name_pad = _pad_to_display(info["name"], name_width)
        print(f"  {i + 1}. {name_pad} ({url}){mark}")
    print("=" * 60)
    default_provider_name = LLM_PROVIDERS.get(default_provider, {}).get('name', default_provider)
    default_hint = f" (直接回车使用：{default_provider_name})"

    while True:
        choice = input(f"请输入编号 (1-{len(provider_keys)}){default_hint}: ").strip()
        if not choice and default_provider in provider_keys:
            choice_idx = provider_keys.index(default_provider) + 1
        else:
            try:
                choice_idx = int(choice)
            except ValueError:
                print("无效输入，请重试。")
                continue
        if 1 <= choice_idx <= len(provider_keys):
            provider = provider_keys[choice_idx - 1]
            break
        print("无效编号，请重试。")

    _save_config("llm_provider", provider)
    pc = LLM_PROVIDERS[provider]
    base_url = pc.get("base_url")
    default_key = pc.get("default_api_key")
    saved_key = _get_config(f"llm_api_key_{provider}")
    api_key = default_key or saved_key

    if not api_key:
        api_key = input("\n请输入 API Key: ").strip()
        if not api_key:
            print("API Key 不能为空，配置取消。")
            return False
        _save_config(f"llm_api_key_{provider}", api_key)
        print(f"✓ 已保存 {pc['name']} API Key")
    elif default_key and api_key == default_key:
        print(f"✓ 使用 {pc['name']} 的 API Key（来自环境变量）")
    else:
        print(f"✓ 使用已保存的 {pc['name']} API Key")

    if not base_url:
        base_url = input("请输入 API Base URL (如 https://api.example.com/v1): ").strip()
        if not base_url:
            print("Base URL 不能为空，配置取消。")
            return False
        _save_config(f"llm_base_url_{provider}", base_url)
    else:
        custom = _get_config(f"llm_base_url_{provider}")
        if custom:
            base_url = custom

    model = interactive_select_llm_model(provider, api_key, base_url)

    _max_workers = pc.get("default_concurrent", gen_config_max_workers)
    _api_delay = pc.get("default_delay", 0.3)
    _request_timeout = pc.get("default_timeout", 120)
    _max_retries = 3

    print("\n运行参数 (直接回车使用当前值):")
    w = input(f"  最大并发数 [{_max_workers}]: ").strip()
    if w:
        try:
            _max_workers = int(w)
        except ValueError:
            pass
    d = input(f"  请求延迟/秒 [{_api_delay}]: ").strip()
    if d:
        try:
            _api_delay = float(d)
        except ValueError:
            pass
    t = input(f"  超时/秒 [{_request_timeout}]: ").strip()
    if t:
        try:
            _request_timeout = int(t)
        except ValueError:
            pass
    print(f"  ✓ 并发={_max_workers}  延迟={_api_delay}s  超时={_request_timeout}s")

    headers = pc.get("default_headers")
    init_client(
        api_key=api_key,
        base_url=base_url,
        model=model,
        headers=headers,
        max_workers=_max_workers,
        api_delay=_api_delay,
        request_timeout=_request_timeout,
        max_retries=_max_retries,
    )
    # 启用 API Key 轮换（如 BLT 有 extra_api_keys）
    extra_keys = pc.get("extra_api_keys", [])
    if extra_keys:
        add_extra_api_keys(extra_keys)
        print(f"  ✓ 已加载 {len(extra_keys)} 个额外 Key 用于轮换")
    return True


def get_client() -> OpenAI | None:
    return _client


def get_model_name() -> str:
    return _model_name


def get_max_workers() -> int:
    return _max_workers


def get_api_delay() -> float:
    return _api_delay


def get_request_timeout() -> int:
    return _request_timeout


def get_max_retries() -> int:
    return _max_retries
