# -*- coding: utf-8 -*-
"""
4.2 Judge 核心逻辑：基于正确答案的 LLM-as-a-Judge 评分。
输入 4_1_executed JSON，输出带 judge_score 的 JSON 到 4_2_judged。
"""

import glob
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
from typing import List, Tuple

from dataflow_edu._compat.tqdm import tqdm

from dataflow_edu.judge.llm_prompts import build_scoring_prompt
from dataflow_edu.judge.llm_scoring import (
    extract_objective_score,
    extract_subjective_score,
)
from dataflow_edu.judge.rule_scoring import (
    LLM_TYPES,
    OBJECTIVE_TYPES,
    score_multiple_choice,
    score_single_choice,
    score_true_false,
)
from dataflow_edu.serving import llm_client

FLUSH_INTERVAL = 10


def scan_judge_candidates(input_dir: str) -> List[Tuple[str, str]]:
    """扫描 input_dir 下 4_1 产出的 JSON（排除 *_judged_*），返回 [(display_name, fullpath)]。"""
    if not os.path.isdir(input_dir):
        return []
    candidates = []
    for fname in sorted(os.listdir(input_dir)):
        if not fname.endswith(".json") or "_judged_" in fname or fname.startswith("."):
            continue
        fullpath = os.path.join(input_dir, fname)
        if os.path.isfile(fullpath):
            candidates.append((fname[:-5], fullpath))
    return candidates


def display_judge_table(candidates: List[Tuple[str, str]]) -> None:
    """交互展示可选文件列表。"""
    print(f"\n{'=' * 60}")
    print("4.2 Judge Operator - 可选文件")
    print("=" * 60)
    print(f" {'序号':>4} | 文件")
    print("-" * 60)
    for i, (name, _) in enumerate(candidates, 1):
        print(f" {i:>4} | {name}.json")
    print("=" * 60)


def safe_model_id(model_name: str) -> str:
    """将模型名转为文件名安全字符串。"""
    return re.sub(r'[\\/:*?"<>|]', "_", model_name)


def find_latest_resume_file(output_dir: str, base_stem: str) -> str | None:
    """查找已存在的 judged 文件用于断点续传。base_stem 为输入文件名（不含 .json）。"""
    pattern = os.path.join(output_dir, f"{base_stem}_judged_*.json")
    matches = glob.glob(pattern)
    if not matches:
        return None
    return max(matches, key=os.path.getmtime)


def _extract_llm_score(llm_output: str, qtype: str) -> float:
    """按题型从 LLM 返回中解析分数。填空题用 0/1，其他主观题用 1-10 归一化到 0.0-1.0。"""
    if qtype == "填空题":
        return extract_objective_score(llm_output)
    return extract_subjective_score(llm_output)


def _process_one(
    idx: int,
    q: dict,
    judge_mode: int,
    system_prompt: str,
) -> Tuple[int, float, str]:
    """
    单题评分。返回 (idx, score, method)。
    method: "rule" | "llm" | "skip"
    """
    qtype = str(q.get("type", "")).strip()
    model_answer = q.get("model_answer", "")
    standard_answer = q.get("answer", "")

    if not model_answer or not str(model_answer).strip():
        return (idx, 0.0, "skip")

    model_out = str(model_answer).strip()
    std_ans = str(standard_answer).strip() if standard_answer else ""

    if qtype in ("单选题", "选择题"):
        score, _ = score_single_choice(model_out, std_ans)
        return (idx, score, "rule")
    if qtype == "多选题":
        score, _ = score_multiple_choice(model_out, std_ans)
        return (idx, score, "rule")
    if qtype == "判断题":
        score, _ = score_true_false(model_out, std_ans)
        return (idx, score, "rule")

    if judge_mode == 0:
        return (idx, 0.0, "skip")

    if qtype in LLM_TYPES or qtype not in OBJECTIVE_TYPES:
        question_text = q.get("question", "")
        user_prompt = build_scoring_prompt(question_text, std_ans, model_out, qtype)
        result = llm_client.call_llm(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=512,
            temperature=0.0,
        )
        score = _extract_llm_score(result, qtype) if result else 0.0
        return (idx, score, "llm")

    return (idx, 0.0, "skip")


def run_judge(
    output_path: str,
    model_id_from_file: str,
    source_file: str,
    judge_mode: int,
    work_questions: list,
    pending_indices: list,
    max_workers: int,
    api_delay: float,
    system_prompt: str,
) -> Tuple[bool, str]:
    """
    执行评分：并发调用规则/LLM，将 judge_score 写入 work_questions，定期保存到 output_path。

    Returns:
        (success, output_path)
    """
    start_time = time.time()
    rule_count = 0
    llm_count = 0
    correct_count = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_process_one, i, work_questions[i], judge_mode, system_prompt): i
            for i in pending_indices
        }

        flush_count = 0
        with tqdm(total=len(pending_indices), desc="评分中", unit="题") as pbar:
            for future in as_completed(futures):
                idx, score, method = future.result()
                work_questions[idx]["judge_score"] = score
                if method == "rule":
                    rule_count += 1
                elif method == "llm":
                    llm_count += 1
                if score >= 0.99:
                    correct_count += 1
                if method == "llm":
                    work_questions[idx]["judgement_result"] = bool(score >= 0.5)
                flush_count += 1
                if flush_count >= FLUSH_INTERVAL:
                    out = {
                        "model_id": model_id_from_file,
                        "source_file": source_file,
                        "judge_mode": judge_mode,
                        "questions": work_questions,
                    }
                    with open(output_path, "w", encoding="utf-8") as f:
                        json.dump(out, f, ensure_ascii=False, indent=2)
                    flush_count = 0
                if api_delay > 0:
                    time.sleep(api_delay)
                pbar.update(1)
                pbar.set_postfix(
                    规则=rule_count,
                    LLM=llm_count,
                    正确=correct_count,
                )

    out = {
        "model_id": model_id_from_file,
        "source_file": source_file,
        "judge_mode": judge_mode,
        "questions": work_questions,
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    elapsed = time.time() - start_time
    total_scored = rule_count + llm_count
    print(f"\n完成: {output_path}")
    print(f"已评分: {total_scored} 题（规则={rule_count}, LLM={llm_count}）")
    print(f"正确: {correct_count}/{total_scored}（按满分计）")
    print(f"耗时: {elapsed:.2f}s")
    _print_summary(work_questions)
    return True, output_path


def _print_summary(work_questions: list) -> None:
    """按题型打印评分摘要统计。"""
    by_type: dict[str, list[float]] = defaultdict(list)
    for q in work_questions:
        s = q.get("judge_score")
        if s is not None:
            try:
                by_type[str(q.get("type", "")).strip()].append(float(s))
            except (TypeError, ValueError):
                pass

    if not by_type:
        return

    print("\n" + "=" * 60)
    print("评分摘要（按题型）")
    print("=" * 60)

    all_types = ["单选题", "选择题", "多选题", "判断题", "填空题", "简答题", "计算题", "综合题"]
    total_n = 0
    total_sum = 0.0

    for qtype in all_types:
        scores = by_type.get(qtype)
        if not scores:
            continue
        n = len(scores)
        avg = sum(scores) / n
        total_n += n
        total_sum += sum(scores)

        if qtype in ("单选题", "选择题", "多选题"):
            correct = sum(1 for x in scores if x >= 0.99)
            wrong = sum(1 for x in scores if x == -0.25)
            skip = n - correct - wrong
            print(f"  {qtype:6s}: 共 {n} 题 | 正确={correct} 错误={wrong} 跳过={skip} | 平均={avg:.4f}")
        elif qtype == "判断题":
            correct = sum(1 for x in scores if x >= 0.99)
            wrong = n - correct
            print(f"  {qtype:6s}: 共 {n} 题 | 正确={correct} 错误={wrong} | 平均={avg:.4f}")
        elif qtype == "填空题":
            correct = sum(1 for x in scores if x >= 0.99)
            wrong = sum(1 for x in scores if x < 0.01)
            print(f"  {qtype:6s}: 共 {n} 题 | 正确={correct} 错误={wrong} | 平均={avg:.4f}")
        else:
            # 简答题、计算题、综合题（1-10 档）
            excellent = sum(1 for x in scores if x >= 0.9)
            pass_count = sum(1 for x in scores if x >= 0.5)
            print(f"  {qtype:6s}: 共 {n} 题 | 优秀(≥9分)={excellent} 及格(≥5分)={pass_count} | 平均={avg:.4f}")

    # 未在 all_types 中列出的题型
    for qtype, scores in sorted(by_type.items()):
        if qtype in all_types:
            continue
        n = len(scores)
        avg = sum(scores) / n
        total_n += n
        total_sum += sum(scores)
        print(f"  {qtype:6s}: 共 {n} 题 | 平均={avg:.4f}")

    print("-" * 60)
    if total_n > 0:
        print(f"  总计: 已评 {total_n} 题，总体平均分={total_sum / total_n:.4f}")
    print("=" * 60)
