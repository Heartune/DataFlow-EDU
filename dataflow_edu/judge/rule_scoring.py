# -*- coding: utf-8 -*-
"""
规则评分模块：单选题、多选题、判断题。
复用 utils_from_CNLaw-Bench/gen_judgment.py 的 score_single_choice、score_multiple_choice。
"""

import re
from typing import Tuple

# 题型分类
OBJECTIVE_TYPES = {"单选题", "选择题", "多选题", "判断题"}
LLM_TYPES = {"填空题", "简答题", "计算题", "综合题"}


def score_single_choice(model_output: str, standard_answer: str) -> Tuple[float, str]:
    """单选题评分。返回 (score, score_type)。"""
    output = str(model_output).strip().upper()
    answer_raw = str(standard_answer).strip().upper()

    # 提取标准答案中的单个选项
    ans_patterns = re.findall(r'(?:答案[是为：:]?\s*|选\s*)([A-D])', answer_raw)
    if ans_patterns:
        answer = ans_patterns[0]
    else:
        all_ans = re.findall(r'[A-D]', answer_raw)
        answer = all_ans[0] if all_ans else ""

    if not answer:
        return (0.0, "invalid")

    # 检查 Pass
    if output == "P":
        return (0.0, "skip")

    # 尝试提取单个选项字母
    answer_patterns = re.findall(r'(?:答案[是为：:]?\s*|选\s*)([A-D])', output)
    if answer_patterns:
        extracted = answer_patterns[-1]
    else:
        all_letters = re.findall(r'[A-D]', output)
        if len(all_letters) == 1:
            extracted = all_letters[0]
        elif len(all_letters) > 1:
            extracted = all_letters[0]
        else:
            return (0.0, "invalid")

    if extracted == answer:
        return (1.0, "correct")
    return (-0.25, "wrong")


def score_multiple_choice(model_output: str, standard_answer: str) -> Tuple[float, str]:
    """多选题评分。返回 (score, score_type)。"""
    output = str(model_output).strip().upper()
    answer = str(standard_answer).strip().upper()

    if output == "P":
        return (0.0, "skip")

    answer_set = set(re.findall(r'[A-D]', answer))
    if not answer_set:
        return (0.0, "invalid")

    answer_patterns = re.findall(r'(?:答案[是为：:]?\s*|选\s*)([A-D]+)', output)
    if answer_patterns:
        extracted_str = answer_patterns[-1]
    else:
        continuous = re.findall(r'[A-D]{2,}', output)
        if continuous:
            extracted_str = continuous[-1]
        else:
            all_letters = re.findall(r'[A-D]', output)
            extracted_str = ''.join(all_letters) if all_letters else ""
        if not extracted_str:
            return (0.0, "invalid")

    output_set = set(extracted_str)
    if output_set == answer_set:
        return (1.0, "correct")
    return (-0.25, "wrong")


def score_true_false(model_output: str, standard_answer: str) -> Tuple[float, str]:
    """判断题评分（对/错）。返回 (score, score_type)。"""
    output = str(model_output).strip()
    answer_raw = str(standard_answer).strip()

    # 解析标准答案：对/错/√/×/正确/错误
    answer_tokens = {"对", "√", "正确", "true", "yes", "是"}
    answer_false = {"错", "×", "错误", "false", "no", "否"}
    ref = ""
    al = answer_raw.lower()
    for t in answer_tokens:
        if t in al or t in answer_raw:
            ref = "对"
            break
    if not ref:
        for t in answer_false:
            if t in al or t in answer_raw:
                ref = "错"
                break
    if not ref:
        # 兜底：取第一个字
        if answer_raw:
            ref = "对" if answer_raw[0] in "对√正确" else "错"
        else:
            return (0.0, "invalid")

    out_lower = output.lower()
    out_val = ""
    for t in answer_tokens:
        if t in out_lower or t in output:
            out_val = "对"
            break
    if not out_val:
        for t in answer_false:
            if t in out_lower or t in output:
                out_val = "错"
                break
    if not out_val:
        if output:
            out_val = "对" if output[0] in "对√正确" else "错"
        else:
            return (0.0, "invalid")

    if out_val == ref:
        return (1.0, "correct")
    return (0.0, "wrong")
