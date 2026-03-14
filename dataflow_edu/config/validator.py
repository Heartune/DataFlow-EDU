# -*- coding: utf-8 -*-
"""配置校验：必填字段、类型、路径等。"""

import os
from typing import List, Tuple

from dataflow_edu.config.schema import EduConfig


def validate_config(
    config: EduConfig,
    project_root: str = None,
    check_paths: bool = False,
) -> Tuple[bool, List[str]]:
    """
    校验配置合法性。
    Returns:
        (is_valid, list of error messages)
    """
    errors: List[str] = []

    # taxonomy
    for i, t in enumerate(config.taxonomy):
        if not t.name or not t.name.strip():
            errors.append(f"taxonomy[{i}]: name 不能为空")
        for j, sub in enumerate(t.subcategories):
            if not sub or not str(sub).strip():
                errors.append(f"taxonomy[{i}].subcategories[{j}]: 小类名称不能为空")

    # question_types
    total_weight = 0.0
    for i, q in enumerate(config.question_types):
        if not q.name or not q.name.strip():
            errors.append(f"question_types[{i}]: name 不能为空")
        if not (0 <= q.weight <= 1):
            errors.append(f"question_types[{i}]: weight 必须在 0~1 之间")
        total_weight += q.weight
    if config.question_types and abs(total_weight - 1.0) > 0.001:
        errors.append(f"question_types: 权重之和应为 1.0，当前为 {total_weight:.3f}")

    # ability_levels
    abl_weight_sum = 0.0
    for i, a in enumerate(config.ability_levels):
        if not a.name or not a.name.strip():
            errors.append(f"ability_levels[{i}]: name 不能为空")
        if not isinstance(a.description, str):
            errors.append(f"ability_levels[{i}]: description 需为字符串")
        w = getattr(a, "weight", 0.25)
        if not (0 <= w <= 1):
            errors.append(f"ability_levels[{i}]: weight 必须在 0~1 之间")
        abl_weight_sum += w
        for j, sub in enumerate(a.sublevels):
            if not sub or not str(sub).strip():
                errors.append(f"ability_levels[{i}].sublevels[{j}]: 子层级名称不能为空")
    if config.ability_levels and abs(abl_weight_sum - 1.0) > 0.001:
        errors.append(f"ability_levels: 权重之和应为 1.0，当前为 {abl_weight_sum:.3f}")

    # mineru_parsing
    mp = config.operators.get("mineru_parsing")
    if mp:
        if not mp.img_dir or not str(mp.img_dir).strip():
            errors.append("operators.mineru_parsing: img_dir 不能为空")
        if not mp.md_dir or not str(mp.md_dir).strip():
            errors.append("operators.mineru_parsing: md_dir 不能为空")
        if mp.batch_size < 1 or mp.batch_size > 200:
            errors.append("operators.mineru_parsing: batch_size 应在 1~200 之间")
        if mp.poll_interval < 1:
            errors.append("operators.mineru_parsing: poll_interval 应 >= 1")
        if mp.poll_timeout < 10:
            errors.append("operators.mineru_parsing: poll_timeout 应 >= 10")
        if mp.language not in ("ch", "en"):
            errors.append("operators.mineru_parsing: language 应为 ch 或 en")

        if check_paths and project_root:
            img_abs = mp.img_dir if os.path.isabs(mp.img_dir) else os.path.join(project_root, mp.img_dir)
            if not os.path.isdir(img_abs):
                errors.append(f"operators.mineru_parsing: img_dir 不存在: {img_abs}")

    return len(errors) == 0, errors
