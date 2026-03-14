# -*- coding: utf-8 -*-
"""
LLM 输出分数解析模块。
参考 utils_from_CNLaw-Bench/gen_judgment.py 的 extract_objective_score / extract_subjective_score。
"""

import json
import re


def extract_objective_score(llm_output: str) -> float:
    """从 LLM 输出中提取填空题分数（0 或 1），返回 0.0 或 1.0。"""
    if not llm_output or not isinstance(llm_output, str):
        return 0.0
    s = llm_output.strip()
    try:
        m = re.search(r'\{[^{}]*"score"[^{}]*\}', s)
        if m:
            obj = json.loads(m.group(0))
            score = obj.get("score", 0)
            return 1.0 if score >= 1 else 0.0
        matches = re.findall(r'(?<!\d)(0|1)(?!\d)', s)
        return float(int(matches[-1])) if matches else 0.0
    except (json.JSONDecodeError, TypeError, ValueError):
        matches = re.findall(r'(?<!\d)(0|1)(?!\d)', s)
        return float(int(matches[-1])) if matches else 0.0


def extract_subjective_score(llm_output: str) -> float:
    """从 LLM 输出中提取主观题分数（1-10），归一化到 0.0-1.0。"""
    if not llm_output or not isinstance(llm_output, str):
        return 0.0
    s = llm_output.strip()
    try:
        m = re.search(r'\{[^{}]*"score"[^{}]*\}', s)
        if m:
            obj = json.loads(m.group(0))
            score = obj.get("score", 1)
            score = max(1, min(10, int(score)))
            return score / 10.0
        matches = re.findall(r'(?<!\d)([1-9]|10)(?!\d)', s)
        return int(matches[0]) / 10.0 if matches else 0.0
    except (json.JSONDecodeError, TypeError, ValueError):
        matches = re.findall(r'(?<!\d)([1-9]|10)(?!\d)', s)
        return int(matches[0]) / 10.0 if matches else 0.0
