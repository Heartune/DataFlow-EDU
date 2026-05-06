# -*- coding: utf-8 -*-
"""
4.1 Execute 核心逻辑：将待测大模型接入系统进行作答，记录其答案。
输入 3_5_deduplicated JSON，输出带 model_answer 的完整 JSON 到 4_1_executed。
"""

import glob
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Tuple

from dataflow_edu._compat.tqdm import tqdm

from dataflow_edu.serving import llm_client

FLUSH_INTERVAL = 10  # 每完成 N 题刷新一次到磁盘


def scan_execute_candidates(input_dir: str) -> List[Tuple[str, str]]:
    """扫描 input_dir 下 *_deduplicated.json，返回 [(stem, fullpath)]。"""
    if not os.path.isdir(input_dir):
        return []
    candidates = []
    for fname in sorted(os.listdir(input_dir)):
        if fname.endswith("_deduplicated.json"):
            stem = fname[: -len("_deduplicated.json")]
            if stem:
                candidates.append((stem, os.path.join(input_dir, fname)))
    return candidates


def safe_model_id(model_name: str) -> str:
    """将模型名转为文件名安全字符串。"""
    return re.sub(r'[\\/:*?"<>|]', "_", model_name)


def _build_prompt(question: str, qtype: str) -> str:
    """根据题型构建学科通用作答 Prompt。"""
    qtype = str(qtype).strip() if qtype else ""
    qtext = str(question).strip()

    if qtype in ("单选题", "选择题"):
        return f"""请回答以下单选题。只输出选项字母（A、B、C 或 D），不要输出其他内容。

{qtext}"""
    if qtype in ("多选题",):
        return f"""请回答以下多选题。只输出正确选项的字母组合（如 ABC），不要输出其他内容。

{qtext}"""
    if qtype in ("填空题",):
        return f"""请对以下填空题作答，给出简洁准确的答案。

{qtext}"""
    if qtype in ("判断题",):
        return f"""请对以下判断题作答，只输出"对"或"错"。

{qtext}"""
    if qtype in ("简答题",):
        return f"""请回答以下简答题。

{qtext}"""
    if qtype in ("计算题",):
        return f"""请解答以下计算题，并给出解题过程和最终答案。

{qtext}"""
    if qtype in ("综合题",):
        return f"""请按要求回答以下综合题。

{qtext}"""
    # 未知题型
    return f"""请回答以下问题。

{qtext}"""


def find_latest_resume_file(output_dir: str, stem: str, model_id_safe: str) -> str | None:
    """查找同一教材+model_id 的最新答案文件。"""
    pattern = os.path.join(output_dir, f"{stem}_{model_id_safe}_*.json")
    matches = glob.glob(pattern)
    if not matches:
        return None
    return max(matches, key=os.path.getmtime)


def _process_one(
    idx: int,
    question: dict,
    system_prompt: str,
) -> Tuple[int, str]:
    """处理单题，返回 (idx, model_answer)。"""
    qtext = question.get("question", "")
    qtype = question.get("type", "")
    if not qtext or not str(qtext).strip():
        return (idx, "")
    user_prompt = _build_prompt(qtext, qtype)
    result = llm_client.call_llm(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        max_tokens=8192,
        temperature=0.0,
    )
    return (idx, result.strip() if result else "")


def display_execute_table(candidates: List[Tuple[str, str]], output_dir: str) -> None:
    """显示可选教材列表。"""
    print(f"\n{'=' * 60}")
    print("4.1 Execute Operator - 可选教材")
    print(f"{'=' * 60}")
    print(f" {'序号':>4} | 教材名称")
    print("-" * 60)
    for i, (stem, _) in enumerate(candidates, 1):
        print(f" {i:>4} | {stem}")
    print("=" * 60)


def run_execute(
    input_path: str,
    output_path: str,
    stem: str,
    model_name: str,
    model_id_safe: str,
    work_questions: list,
    pending_indices: list,
    max_workers: int,
    api_delay: float,
    system_prompt: str,
) -> Tuple[bool, str]:
    """
    执行作答：并发调用 LLM，将 model_answer 写入 work_questions，定期保存到 output_path。

    Returns:
        (success, output_path)
    """
    start_time = time.time()
    success_count = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_process_one, i, work_questions[i], system_prompt): i
            for i in pending_indices
        }

        flush_count = 0
        with tqdm(total=len(pending_indices), desc="作答中", unit="题") as pbar:
            for future in as_completed(futures):
                idx, answer = future.result()
                if answer:
                    work_questions[idx]["model_answer"] = answer
                    success_count += 1
                flush_count += 1
                if flush_count >= FLUSH_INTERVAL:
                    out = {
                        "model_id": model_id_safe,
                        "model_name": model_name,
                        "source_file": os.path.basename(input_path),
                        "questions": work_questions,
                    }
                    with open(output_path, "w", encoding="utf-8") as f:
                        json.dump(out, f, ensure_ascii=False, indent=2)
                    flush_count = 0
                if api_delay > 0:
                    time.sleep(api_delay)
                pbar.update(1)
                pbar.set_postfix(成功=f"{success_count}/{pbar.n}")

    out = {
        "model_id": model_id_safe,
        "model_name": model_name,
        "source_file": os.path.basename(input_path),
        "questions": work_questions,
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    elapsed = time.time() - start_time
    print(f"\n完成: {output_path}")
    print(f"成功: {success_count}/{len(pending_indices)} ({success_count / len(pending_indices) * 100:.1f}%)")
    print(f"耗时: {elapsed:.2f}s")
    return True, output_path

