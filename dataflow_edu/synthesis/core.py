# -*- coding: utf-8 -*-
"""
3.6 Synthesis 核心逻辑：基于 question + answer 调用 LLM 生成 explanation 字段。

参考 utils_from_ROBOTheory/解析生成/generate_explanations解析生成_优化版.py 的 system prompt 风格
（专业、言简意赅、分段不分点），统一通过 dataflow_edu.serving.call_llm 调用。
"""

import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple

from dataflow_edu._compat.tqdm import tqdm

from dataflow_edu.serving import call_llm, get_api_delay

PROGRESS_SUFFIX = "_synthesis_progress.json"

SYSTEM_PROMPT = """你是一位资深的教育专家，擅长为高水平的学术问题提供深入、专业的解析。

你的任务是：根据给定的问题和答案，生成详细的解析。

要求：
- 解析必须专业、准确、有深度
- 不要太啰嗦，要言简意赅，分段不分点，分段不分点，分段不分点，分段不分点，分段不分点！！！
- 不要重复问题和答案的内容，而是提供额外的解释性内容
- 直接输出解析正文，不要包含任何前缀、标题或元说明"""


def _generate_explanation(
    question: str,
    answer: str,
    max_tokens: int = 2000,
    temperature: float = 0.3,
    max_retries: int = 3,
) -> Optional[str]:
    """调用 LLM 生成单条题目的 explanation。"""
    user_prompt = f"""问题：
{question}

答案：
{answer if answer else '（无参考答案）'}

请为这道题目生成详细的解析。"""

    for attempt in range(max_retries):
        try:
            result = call_llm(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=user_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                max_retries=1,
            )
            if result and result.strip():
                return result.strip()
        except Exception:
            pass
        if attempt < max_retries - 1:
            time.sleep(2 * (attempt + 1))
    return None


def _scan_synthesis_candidates(input_dir: str) -> List[str]:
    """扫描 input_dir 下 *_deduplicated.json，返回教材名列表。"""
    if not os.path.isdir(input_dir):
        return []
    candidates = []
    for fname in sorted(os.listdir(input_dir)):
        if fname.endswith("_deduplicated.json"):
            folder_name = fname.replace("_deduplicated.json", "")
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
    """加载进度：{ "explanations": { idx: explanation, ... } }"""
    if not os.path.isfile(progress_path):
        return None
    try:
        with open(progress_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _save_progress(progress_path: str, explanations: Dict[int, str]) -> None:
    """保存进度。"""
    with open(progress_path, "w", encoding="utf-8") as f:
        json.dump(
            {"explanations": {str(k): v for k, v in explanations.items()}},
            f,
            ensure_ascii=False,
            indent=2,
        )


def _print_explanation_coverage(items: List[dict]) -> None:
    """终端打印 explanation 覆盖率。"""
    total = len(items)
    if total == 0:
        return
    with_exp = sum(1 for it in items if str(it.get("explanation", "")).strip())
    print("\n【解析覆盖率】")
    print(f"  含 explanation: {with_exp} / {total} ({100 * with_exp / total:.1f}%)")
    if with_exp < total:
        print(f"  缺失 explanation: {total - with_exp} 题")


def _process_single(
    idx: int,
    item: dict,
    max_tokens: int,
    temperature: float,
    max_retries: int,
) -> Tuple[int, Optional[str]]:
    """处理单条题目，返回 (idx, explanation 或 None)。"""
    question = str(item.get("question", "")).strip()
    answer = str(item.get("output", item.get("answer", ""))).strip()
    if not question:
        return idx, None
    exp = _generate_explanation(
        question, answer, max_tokens=max_tokens, temperature=temperature, max_retries=max_retries
    )
    return idx, exp


def run_synthesis(
    input_path: str,
    output_dir: str,
    folder_name: str,
    max_workers: int = 8,
    max_retries: int = 3,
    max_tokens: int = 2000,
    temperature: float = 0.3,
    skip_existing: bool = True,
    force_regenerate: bool = False,
    resume: bool = False,
) -> Tuple[bool, str]:
    """
    执行解析生成：加载 questions → 过滤需处理项 → 并发调用 LLM → 写回 explanation。

    Returns:
        (ok, synthesized_path)
    """
    os.makedirs(output_dir, exist_ok=True)
    progress_path = os.path.join(output_dir, f"{folder_name}{PROGRESS_SUFFIX}")
    synthesized_path = os.path.join(output_dir, f"{folder_name}_synthesized.json")

    questions, metadata = _load_questions(input_path)
    total = len(questions)
    if total == 0:
        return False, synthesized_path

    explanations_by_idx: Dict[int, str] = {}

    if resume:
        prog = _load_progress(progress_path)
        if prog:
            for k, v in (prog.get("explanations") or {}).items():
                try:
                    i = int(k)
                except (TypeError, ValueError):
                    continue
                if 0 <= i < total and isinstance(v, str) and v.strip():
                    explanations_by_idx[i] = v

    needs_work: List[int] = []
    for i in range(total):
        if i in explanations_by_idx:
            continue
        existing = str(questions[i].get("explanation", "")).strip()
        if existing and skip_existing and not force_regenerate:
            explanations_by_idx[i] = existing
            continue
        if not str(questions[i].get("question", "")).strip():
            continue
        needs_work.append(i)

    if resume and explanations_by_idx and needs_work:
        print(
            f"Resume: 已生成 {len(explanations_by_idx)}/{total}，剩余 {len(needs_work)} 题"
        )

    api_delay = get_api_delay()
    lock = threading.Lock()
    save_every = max(10, max_workers * 2)
    completed_since_save = 0

    if needs_work:
        with tqdm(total=len(needs_work), desc="解析生成", unit="题") as pbar:
            if max_workers <= 1:
                for idx in needs_work:
                    item = questions[idx]
                    _, exp = _process_single(
                        idx, item, max_tokens, temperature, max_retries
                    )
                    if exp:
                        with lock:
                            explanations_by_idx[idx] = exp
                            completed_since_save += 1
                            if completed_since_save >= save_every:
                                _save_progress(progress_path, explanations_by_idx)
                                completed_since_save = 0
                    pbar.update(1)
                    time.sleep(api_delay)
            else:
                with ThreadPoolExecutor(max_workers=max_workers) as ex:
                    futures = {
                        ex.submit(
                            _process_single,
                            idx,
                            questions[idx],
                            max_tokens,
                            temperature,
                            max_retries,
                        ): idx
                        for idx in needs_work
                    }
                    for future in as_completed(futures):
                        idx = futures[future]
                        try:
                            _, exp = future.result()
                            if exp:
                                with lock:
                                    explanations_by_idx[idx] = exp
                                    completed_since_save += 1
                                    if completed_since_save >= save_every:
                                        _save_progress(progress_path, explanations_by_idx)
                                        completed_since_save = 0
                        except Exception:
                            pass
                        pbar.update(1)
                        time.sleep(api_delay)

    _save_progress(progress_path, explanations_by_idx)

    output_items: List[dict] = []
    success_count = 0
    failed_count = 0
    skipped_count = 0
    for i in range(total):
        item = dict(questions[i])
        if i in explanations_by_idx and explanations_by_idx[i].strip():
            item["explanation"] = explanations_by_idx[i]
            success_count += 1
        else:
            existing = str(item.get("explanation", "")).strip()
            if existing:
                skipped_count += 1
            else:
                failed_count += 1
        output_items.append(item)

    meta_out = {
        **metadata,
        "source": input_path,
        "synthesis": {
            "total": total,
            "with_explanation": sum(
                1 for it in output_items if str(it.get("explanation", "")).strip()
            ),
            "newly_generated": success_count,
            "kept_existing": skipped_count,
            "failed": failed_count,
            "skip_existing": skip_existing,
            "force_regenerate": force_regenerate,
        },
    }

    with open(synthesized_path, "w", encoding="utf-8") as f:
        json.dump(
            {"questions": output_items, "metadata": meta_out},
            f,
            ensure_ascii=False,
            indent=2,
        )

    print(
        f"\n3.6 解析生成完成: 新生成 {success_count}，保留已有 {skipped_count}，失败 {failed_count}"
    )
    print(f"✓ 输出: {synthesized_path}")
    return True, synthesized_path
