# -*- coding: utf-8 -*-
"""
多学科 prompt 加载器。

按 config.subject 加载 prompts/<subject_key>.yaml，未匹配时回退 default.yaml。
学科特化文件中的 type_hints 与 default 合并（子项覆盖），其余字段直接覆盖。
"""

import copy
import os

import yaml

_PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "prompts")

_SUBJECT_TO_KEY: dict[str, str] = {
    # 高中学科（senior_ 前缀文件）
    "生物学": "senior_biology",
    "生物": "senior_biology",
    "物理": "senior_physics",
    "物理学": "senior_physics",
    "数学": "senior_math",
    "语文": "senior_chinese",
    "历史": "senior_history",
    "英语": "senior_english",
    "化学": "senior_chemistry",
    "思想政治": "senior_politics",
    "政治": "senior_politics",
    "地理": "senior_geography",
    # 初中学科（junior_ 前缀文件）
    "初中语文": "junior_chinese",
    "初中数学": "junior_math",
    "初中英语": "junior_english",
    "初中物理": "junior_physics",
    "初中化学": "junior_chemistry",
    "初中生物学": "junior_biology",
    "初中生物": "junior_biology",
    "初中道德与法治": "junior_politics",
    "初中政治": "junior_politics",
    "初中历史": "junior_history",
    "初中地理": "junior_geography",
}

_cache: dict[str, dict] = {}


def load_prompts(subject: str = "") -> dict:
    """
    加载指定学科的 prompt 配置，优先返回缓存。

    合并规则：
    - type_hints：subject YAML 与 default 深度合并，subject 值覆盖 default 同键
    - 其余顶级字段：subject YAML 直接覆盖 default

    Args:
        subject: 学科名称，如「生物学」「物理」「数学」。空字符串使用 default。

    Returns:
        合并后的 prompt 配置字典，至少包含：
        - taxonomy_analysis_system: str
        - question_generation_system_prefix: str
        - type_hints: dict[str, str]
    """
    cache_key = subject.strip()
    if cache_key in _cache:
        return _cache[cache_key]

    default_path = os.path.join(_PROMPTS_DIR, "default.yaml")
    with open(default_path, "r", encoding="utf-8") as f:
        prompts: dict = yaml.safe_load(f) or {}

    key = _SUBJECT_TO_KEY.get(cache_key, "")
    if key:
        subject_path = os.path.join(_PROMPTS_DIR, f"{key}.yaml")
        if os.path.exists(subject_path):
            with open(subject_path, "r", encoding="utf-8") as f:
                subj: dict = yaml.safe_load(f) or {}
            prompts = copy.deepcopy(prompts)
            for k, v in subj.items():
                if k == "type_hints" and isinstance(v, dict):
                    prompts.setdefault("type_hints", {}).update(v)
                else:
                    prompts[k] = v

    _cache[cache_key] = prompts
    return prompts


def get_type_hint(prompts: dict, q_type_name: str) -> str:
    """
    从已加载的 prompts 中查找题型专属指引，模糊匹配（包含关系）。
    未命中返回通用兜底文案。
    """
    hints: dict = prompts.get("type_hints", {})
    for k, v in hints.items():
        if k in q_type_name or q_type_name in k:
            return str(v)
    return "题干与答案须独立完整，无模糊指代。"
