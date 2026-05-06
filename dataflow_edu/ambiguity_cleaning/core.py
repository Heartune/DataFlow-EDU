# -*- coding: utf-8 -*-
"""
3.1 Ambiguity Cleaning 核心逻辑：基于 LLM 5 点制二义性评估，剔除低质量样本。
"""

import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple

from dataflow_edu._compat.tqdm import tqdm

from dataflow_edu.serving import call_llm, get_api_delay

PROGRESS_SUFFIX = "_ambiguity_progress.json"
SYSTEM_PROMPT = """你是一位专业的教育测评专家，具有丰富的学科知识和问题分析经验。

## 主要职责
对学科知识题目进行二义性（歧义性）评分，结合题目内容和参考答案综合判断。采用 1–5 分制。

## 5 分制说明
- **1 分（强二义性）**：题目存在多种合理理解，指向不清，答案无法唯一对应题干；或题目明显不完整。
- **2 分（二义性明显）**：表述模糊，答案与题干匹配度低；存在明显歧义或范围不明确。
- **3 分（轻微二义性）**：整体可理解，但有少量模糊表述；答案基本匹配，略有歧义。
- **4 分（基本无二义性）**：表述清晰，答案与题干较好对应；仅有个别措辞可优化。
- **5 分（无二义性）**：表述明确，答案唯一对应，逻辑一致，语境完备。

## 题型识别与处理
- 客观题（判断题、选择题、填空题）答案简短是正常的，不应因答案简短而打低分。
- 重点判断：内容完整性、表述清晰性、指向明确性、答案匹配度、逻辑一致性、语境完备性、文字准确性。

## 输出要求
必须按照以下 JSON 格式输出，不要添加任何其他内容：
{"score": 1到5的整数, "reason": "简要分析理由，至少30字"}
"""


def _print_ambiguity_distribution(items: List[dict]) -> None:
    """在终端展示二义性分数分布（含百分比）。"""
    from collections import Counter

    total = len(items)
    if total == 0:
        return
    scores = []
    for it in items:
        s = it.get("ambiguity_score")
        try:
            scores.append(int(s) if s is not None and 1 <= int(s) <= 5 else None)
        except (TypeError, ValueError):
            scores.append(None)
    cnt = Counter(scores)
    print("\n【二义性分布】")
    for i in range(1, 6):
        n = cnt.get(i, 0)
        pct = 100 * n / total
        print(f"  {i}分: {n} 题 ({pct:.1f}%)")
    if cnt.get(None, 0) > 0:
        n = cnt[None]
        pct = 100 * n / total
        print(f"  无/未知: {n} 题 ({pct:.1f}%)")
    print(f"  合计: {total} 题")


def _evaluate_ambiguity(
    question: str,
    answer: str,
    max_retries: int = 3,
) -> Tuple[Optional[int], str]:
    """
    调用 LLM 对题目进行 5 点制二义性评估。

    Returns:
        (score, reason): score 为 1–5 或 None（评估失败），reason 为分析理由。
    """
    user_prompt = f"""请对以下题目进行二义性评分（1–5 分），输出 JSON 格式。

题目：{question}

参考答案：{answer if answer else '无参考答案'}

请输出：{{"score": 1-5, "reason": "分析理由"}}"""

    for attempt in range(max_retries):
        try:
            result = call_llm(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=user_prompt,
                max_tokens=512,
                temperature=0.1,
                max_retries=1,
            )
            if not result or not result.strip():
                if attempt < max_retries - 1:
                    time.sleep(2 * (attempt + 1))
                    continue
                return None, f"LLM 返回为空，已重试 {max_retries} 次"

            raw = result.strip()
            if "```" in raw:
                if "```json" in raw:
                    raw = raw.split("```json")[1].split("```")[0]
                else:
                    raw = raw.split("```")[1].split("```")[0]
            raw = raw.strip()

            data = json.loads(raw)
            score = data.get("score")
            reason = str(data.get("reason", "")).strip() or "无理由"

            if isinstance(score, (int, float)):
                s = int(score)
                if 1 <= s <= 5:
                    return s, reason
            if attempt < max_retries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            return None, f"score 格式异常，已重试 {max_retries} 次"
        except json.JSONDecodeError as e:
            if attempt < max_retries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            return None, f"JSON 解析失败: {e}，已重试 {max_retries} 次"
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            return None, f"错误: {e}，已重试 {max_retries} 次"
    return None, f"未知错误，已重试 {max_retries} 次"


def _scan_cleaning_candidates(input_dir: str) -> List[str]:
    """扫描 input_dir 下 *_balanced_questions.json，返回教材名列表。"""
    if not os.path.isdir(input_dir):
        return []
    candidates = []
    for fname in sorted(os.listdir(input_dir)):
        if fname.endswith("_balanced_questions.json"):
            folder_name = fname.replace("_balanced_questions.json", "")
            candidates.append(folder_name)
    return candidates


def _load_questions(input_path: str) -> Tuple[List[dict], dict]:
    """加载 JSON 中的 questions 数组及 metadata。"""
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    questions = data.get("questions", [])
    metadata = data.get("metadata", {})
    return questions, metadata


def _load_progress(progress_path: str) -> Optional[Dict[str, Any]]:
    """加载进度：{ "results": [{idx, score, reason, item}, ...] }"""
    if not os.path.isfile(progress_path):
        return None
    try:
        with open(progress_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _save_progress(progress_path: str, results: List[dict]) -> None:
    """保存进度。"""
    with open(progress_path, "w", encoding="utf-8") as f:
        json.dump({"results": results}, f, ensure_ascii=False, indent=2)


def _process_single(
    idx: int,
    item: dict,
    max_retries: int,
) -> Tuple[int, Optional[int], str, dict]:
    """处理单个题目，返回 (idx, score, reason, item)。"""
    question = str(item.get("question", "")).strip()
    answer = str(item.get("output", item.get("answer", ""))).strip()
    if not question:
        return idx, None, "题目为空，跳过", item
    score, reason = _evaluate_ambiguity(question, answer, max_retries=max_retries)
    return idx, score, reason, item


def run_ambiguity_cleaning(
    input_path: str,
    output_dir: str,
    folder_name: str,
    max_workers: int = 8,
    max_retries: int = 3,
    threshold_remove: int = 2,
    resume: bool = False,
    no_confirm: bool = False,
) -> Tuple[bool, str, str]:
    """
    执行二义性清洗：评估 -> 剔除 1–threshold_remove 分 -> 保存。

    Returns:
        (ok, cleaned_path, removed_path)
    """
    os.makedirs(output_dir, exist_ok=True)
    progress_path = os.path.join(output_dir, f"{folder_name}{PROGRESS_SUFFIX}")
    cleaned_path = os.path.join(output_dir, f"{folder_name}_ambiguity_cleaned.json")
    removed_path = os.path.join(output_dir, f"{folder_name}_ambiguity_removed.json")

    questions, metadata = _load_questions(input_path)
    total = len(questions)
    if total == 0:
        return False, cleaned_path, removed_path

    results_by_idx: Dict[int, Tuple[Optional[int], str, dict]] = {}
    needs_work: List[int] = []

    if resume:
        prog = _load_progress(progress_path)
        if prog:
            for r in prog.get("results", []):
                i = r.get("idx", -1)
                if 0 <= i < total:
                    results_by_idx[i] = (
                        r.get("score"),
                        r.get("reason", ""),
                        r.get("item", questions[i]),
                    )
            needs_work = [i for i in range(total) if i not in results_by_idx]
            if not needs_work:
                pass
            else:
                print(f"Resume: 已处理 {len(results_by_idx)}/{total}，剩余 {len(needs_work)} 题")
        else:
            needs_work = list(range(total))
    else:
        needs_work = list(range(total))

    lock = threading.Lock()
    api_delay = get_api_delay()

    with tqdm(
        total=len(needs_work),
        desc="二义性评估",
        unit="题",
    ) as pbar:
        if max_workers <= 1:
            for idx in needs_work:
                item = questions[idx]
                _, score, reason, item_with_meta = _process_single(
                    idx, item, max_retries
                )
                item_out = dict(item_with_meta)
                item_out["ambiguity_score"] = score
                item_out["ambiguity_reason"] = reason
                with lock:
                    results_by_idx[idx] = (score, reason, item_out)
                pbar.update(1)
                time.sleep(api_delay)
        else:
            with ThreadPoolExecutor(max_workers=max_workers) as ex:
                futures = {
                    ex.submit(_process_single, idx, questions[idx], max_retries): idx
                    for idx in needs_work
                }
                for future in as_completed(futures):
                    idx = futures[future]
                    try:
                        _, score, reason, item = future.result()
                        item_out = dict(item)
                        item_out["ambiguity_score"] = score
                        item_out["ambiguity_reason"] = reason
                        with lock:
                            results_by_idx[idx] = (score, reason, item_out)
                    except Exception as e:
                        item_out = dict(questions[idx])
                        item_out["ambiguity_score"] = None
                        item_out["ambiguity_reason"] = str(e)
                        with lock:
                            results_by_idx[idx] = (None, str(e), item_out)
                    pbar.update(1)
                    time.sleep(api_delay)

    for idx in range(total):
        if idx not in results_by_idx:
            item_out = dict(questions[idx])
            item_out["ambiguity_score"] = None
            item_out["ambiguity_reason"] = "未处理"
            results_by_idx[idx] = (None, "未处理", item_out)

    results = [
        {"idx": i, "score": results_by_idx[i][0], "reason": results_by_idx[i][1], "item": results_by_idx[i][2]}
        for i in range(total)
    ]
    _save_progress(progress_path, results)

    removed_items = []
    kept_items = []
    for i in range(total):
        score, reason, item = results_by_idx[i]
        if score is not None and 1 <= score <= threshold_remove:
            removed_items.append(item)
        else:
            kept_items.append(item)

    n_removed = len(removed_items)
    n_kept = len(kept_items)
    print(f"\n评估完成: 保留 {n_kept}，剔除 {n_removed}（1–{threshold_remove} 分）")

    if n_removed > 0 and not no_confirm:
        print("\n剔除样本示例（前 3 条）:")
        for j, it in enumerate(removed_items[:3]):
            q = str(it.get("question", ""))[:80]
            s = it.get("ambiguity_score", "?")
            print(f"  {j + 1}. [score={s}] {q}...")
        while True:
            r = input("\n确认剔除并保存？(y/n): ").strip().lower()
            if r in ("y", "yes", "是", "确认"):
                break
            if r in ("n", "no", "否", "取消"):
                print("操作已取消。")
                return False, cleaned_path, removed_path
            print("请输入 y/yes/是 或 n/no/否")

    meta_cleaned = {
        **metadata,
        "source": input_path,
        "ambiguity_cleaning": {
            "kept": n_kept,
            "removed": n_removed,
            "threshold_remove": threshold_remove,
        },
    }
    meta_removed = {
        **metadata,
        "source": input_path,
        "ambiguity_cleaning": {"removed_count": n_removed, "threshold_remove": threshold_remove},
    }

    with open(cleaned_path, "w", encoding="utf-8") as f:
        json.dump({"questions": kept_items, "metadata": meta_cleaned}, f, ensure_ascii=False, indent=2)
    with open(removed_path, "w", encoding="utf-8") as f:
        json.dump({"questions": removed_items, "metadata": meta_removed}, f, ensure_ascii=False, indent=2)

    print(f"✓ 保留: {cleaned_path}")
    print(f"✓ 剔除: {removed_path}")
    return True, cleaned_path, removed_path
