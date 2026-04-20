# -*- coding: utf-8 -*-
"""JSON 导出：直接 dump 当前题库快照成单个 .json 文件。

与历史的 `GET /export?format=json`（流式 zip 多文件）相区分：这里的 JSON 是按
统一 schema 抽取后的「整本题库」单文件版本，便于数据分析和模型微调直接消费。
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

from dataflow_edu.export.data_loader import load_task_questions


def export_json(
    task_dir: str | os.PathLike[str],
    output_path: str | os.PathLike[str],
    *,
    stage: str = "3_8_mcq_verified",
    lang: str = "zh",
    task_name: Optional[str] = None,
    keep_raw: bool = True,
) -> Path:
    """生成 JSON 快照。

    Args:
        task_dir: 任务工作目录。
        output_path: 目标 .json 文件绝对路径。
        stage: 取哪个 stage 的产物（如 `3_8_mcq_verified` / `3_7_translated`）。
        lang: zh|en|fr。zh 取原文。
        task_name: 写入元信息，便于追溯。
        keep_raw: True 时保留每题原始 JSON（含所有语言版本与评分理由）；
            False 时只保留按 lang resolve 后的字段，体积更小。

    Returns:
        实际写入的 Path（与传入的 output_path 相同）。
    """

    records = load_task_questions(task_dir, stage=stage, lang=lang)

    items = []
    for r in records:
        if keep_raw:
            items.append(r.raw)
        else:
            items.append(
                {
                    "question": r.question,
                    "options": r.options,
                    "answer": r.answer,
                    "explanation": r.explanation,
                    "type": r.type,
                    "category": r.category,
                    "subcategory": r.subcategory,
                    "ability_main": r.ability_main,
                    "ability_level": r.ability_level,
                    "difficulty": r.difficulty,
                    "source_page": r.source_page,
                }
            )

    payload: Dict[str, Any] = {
        "schema_version": 1,
        "exported_at": int(time.time()),
        "task_name": task_name or "",
        "stage": stage,
        "lang": lang,
        "keep_raw": bool(keep_raw),
        "count": len(items),
        "questions": items,
    }

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return out
