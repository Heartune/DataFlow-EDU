# -*- coding: utf-8 -*-
"""任务产物 → 统一题目记录列表。

约定：
- task_dir 内的某个 stage 目录（如 `3_8_mcq_verified/`）下，可能存在多个 `*.json`
  （每本教材一个文件）。每个文件的顶层结构是 `{"questions": [...]}` 或直接是题目列表。
- 不同 stage 字段集合略有差异，本模块统一映射成 `QuestionRecord`，缺字段就置空。
- 多语言字段命名约定：`<base>_en`, `<base>_fr`，未翻译则回退到中文原文。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


SUPPORTED_LANGS = ("zh", "en", "fr")
"""可选导出语言。zh=中文原文（无后缀字段）。"""


@dataclass
class QuestionRecord:
    """归一化后的单道题。语言相关字段按 `lang` 已经 resolve 完毕。"""

    question: str = ""
    options: Any = None  # 原样保留：可能是 list / dict / str / None
    answer: str = ""
    explanation: str = ""
    type: str = ""
    category: str = ""
    subcategory: str = ""
    ability_main: str = ""
    ability_level: str = ""
    difficulty: str = ""
    source_page: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _coerce_question_list(payload: Any) -> List[Dict[str, Any]]:
    """兼容三种文件结构：dict-with-questions、list、其它（忽略）。"""

    if isinstance(payload, dict):
        for key in ("questions", "items", "data"):
            if isinstance(payload.get(key), list):
                return [q for q in payload[key] if isinstance(q, dict)]
    if isinstance(payload, list):
        return [q for q in payload if isinstance(q, dict)]
    return []


def _pick_localized(item: Dict[str, Any], base: str, lang: str) -> str:
    """按语言取字段；缺失或为空时回退到中文原文。"""

    if lang in ("en", "fr"):
        val = item.get(f"{base}_{lang}")
        if isinstance(val, str) and val.strip():
            return val
    val = item.get(base)
    return val if isinstance(val, str) else ("" if val is None else str(val))


def _pick_options(item: Dict[str, Any], lang: str) -> Any:
    """选项可能是 list[str] 或 dict[letter -> text]。同样支持多语言后缀。"""

    if lang in ("en", "fr"):
        val = item.get(f"options_{lang}")
        if val:
            return val
    return item.get("options")


def _to_record(item: Dict[str, Any], lang: str) -> QuestionRecord:
    return QuestionRecord(
        question=_pick_localized(item, "question", lang),
        options=_pick_options(item, lang),
        answer=_pick_localized(item, "answer", lang),
        explanation=_pick_localized(item, "explanation", lang),
        type=str(item.get("type") or ""),
        category=str(item.get("category") or ""),
        subcategory=str(item.get("subcategory") or ""),
        ability_main=str(item.get("ability_main") or ""),
        ability_level=str(item.get("ability_level") or ""),
        difficulty=str(item.get("difficulty") or ""),
        source_page=str(item.get("source_page") or ""),
        raw=item,
    )


def find_stage_dir(task_dir: str | os.PathLike[str], stage: str) -> Optional[Path]:
    """task_dir 下扫一级子目录，匹配以 stage 名字结尾的目录（带或不带数字前缀）。

    例如 stage='3_8_mcq_verified' 时既可命中 `3_8_mcq_verified/` 也命中 `xxx_3_8_mcq_verified/`。
    """

    root = Path(task_dir)
    if not root.is_dir():
        return None
    direct = root / stage
    if direct.is_dir():
        return direct
    for sub in sorted(root.iterdir()):
        if sub.is_dir() and sub.name.endswith(stage):
            return sub
    return None


def iter_stage_json_files(stage_dir: Path) -> Iterable[Path]:
    """stage 目录下递归列出所有 `*.json`（按文件名稳定排序）。"""

    return sorted(p for p in stage_dir.rglob("*.json") if p.is_file())


def load_task_questions(
    task_dir: str | os.PathLike[str],
    stage: str = "3_8_mcq_verified",
    lang: str = "zh",
) -> List[QuestionRecord]:
    """从 task_dir/stage 下汇总所有题目并按统一 schema 输出。"""

    if lang not in SUPPORTED_LANGS:
        raise ValueError(f"unsupported lang: {lang!r}, expected one of {SUPPORTED_LANGS}")

    stage_dir = find_stage_dir(task_dir, stage)
    if stage_dir is None:
        return []

    records: List[QuestionRecord] = []
    for jf in iter_stage_json_files(stage_dir):
        try:
            payload = _read_json(jf)
        except Exception:
            continue
        for item in _coerce_question_list(payload):
            records.append(_to_record(item, lang))
    return records
