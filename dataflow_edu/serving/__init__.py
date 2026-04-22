# -*- coding: utf-8 -*-
"""
DataFlow-EDU 通用 LLM/API 客户端包。

被 Generation、Ambiguity Cleaning、Balancing 等算子共用。
"""

from dataflow_edu.serving.llm_client import (
    call_llm,
    get_api_delay,
    get_max_workers,
    interactive_config_llm,
    init_client,
)
from dataflow_edu.serving.web_search_llm import call_web_search_llm

__all__ = [
    "call_llm",
    "call_web_search_llm",
    "get_api_delay",
    "get_max_workers",
    "interactive_config_llm",
    "init_client",
]
