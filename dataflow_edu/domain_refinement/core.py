# -*- coding: utf-8 -*-
"""
3.4 Domain Refinement 核心逻辑：对 2–3 分题优化题干与答案，提升领域相关性。
参考 utils_from_ROBOTheory/相关性评估与小类区分 的 prompt 思路，以及 3.2 Ambiguity Refinement 的改写结构。
"""

import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple

from tqdm import tqdm

from dataflow_edu.domain_cleaning.core import _evaluate_domain_relevance
from dataflow_edu.serving import call_llm, get_api_delay

PROGRESS_SUFFIX = "_domain_refinement_progress.json"


def _print_domain_relevance_distribution(items: List[dict]) -> None:
    """在终端展示领域相关性分数分布（含百分比）。"""
    from collections import Counter

    total = len(items)
    if total == 0:
        return
    scores = []
    for it in items:
        s = it.get("domain_relevance_score")
        try:
            scores.append(int(s) if s is not None and 1 <= int(s) <= 5 else None)
        except (TypeError, ValueError):
            scores.append(None)
    cnt = Counter(scores)
    print("\n【领域相关性分布】")
    for i in range(1, 6):
        n = cnt.get(i, 0)
        pct = 100 * n / total
        print(f"  {i}分: {n} 题 ({pct:.1f}%)")
    if cnt.get(None, 0) > 0:
        n = cnt[None]
        pct = 100 * n / total
        print(f"  无/未知: {n} 题 ({pct:.1f}%)")
    print(f"  合计: {total} 题")
    sys.stdout.flush()


def _format_taxonomy_for_prompt(taxonomy_items: list) -> str:
    """将 taxonomy 列表拼成「大类: 小类1, 小类2; ...」格式。"""
    if not taxonomy_items:
        return ""
    lines = []
    for t in taxonomy_items:
        name = t.get("name", "") if isinstance(t, dict) else getattr(t, "name", "")
        subcats = t.get("subcategories", []) if isinstance(t, dict) else getattr(t, "subcategories", [])
        sc = "、".join(subcats) if subcats else "（无）"
        lines.append(f"- {name}：{sc}")
    return "\n".join(lines)


def _build_system_prompt(
    domain_name: str,
    subcategory_or_taxonomy: str,
) -> str:
    """构建领域相关性优化的系统提示。"""
    if subcategory_or_taxonomy and subcategory_or_taxonomy.strip():
        target_hint = f"""
## 目标知识小类
本题应归属或贴近的知识小类为：{subcategory_or_taxonomy.strip()}
请围绕该小类提升题目与{domain_name}学科领域的相关性。"""
    else:
        target_hint = f"\n请围绕{domain_name}学科领域提升题目相关性。"
    return f"""你是一位资深的{domain_name}学科教育专家和题目设计师，擅长优化题目与学科领域的相关性。
{target_hint}

## 核心约束 - 必须严格遵守
**绝对不能改变题目的题型和核心内容**
**只能针对"具体领域相关问题"进行优化，使题目更贴近{domain_name}学科考察范围，不能替换整个题目**

## 输出格式
必须严格按照以下JSON格式输出：
{{
    "优化后问题": "（问题内容）",
    "优化后答案": "（答案内容）"
}}"""


def _clean_json_string(text: str) -> str:
    """清理和修复 JSON 字符串。"""
    text = text.strip()
    json_match = re.search(r"\{.*\}", text, re.DOTALL)
    if json_match:
        text = json_match.group()
    text = re.sub(r'(?<![\\])\'', '"', text)
    text = re.sub(r",\s*}", "}", text)
    text = re.sub(r",\s*]", "]", text)
    return text


def _optimize_single(
    question: str,
    answer: str,
    domain_reason: str,
    subcategory_or_taxonomy: str,
    domain_name: str,
    max_retries: int = 3,
) -> Optional[Tuple[str, str]]:
    """
    调用 LLM 优化单个题目的题干和答案，提升领域相关性。

    Returns:
        (优化后问题, 优化后答案) 或 None（失败时）
    """
    system_prompt = _build_system_prompt(domain_name, subcategory_or_taxonomy)
    user_prompt = f"""
原始问题：
{question}

原始答案：
{answer if answer else "无答案"}

**具体领域相关问题**：
{domain_reason if domain_reason else "未提供具体领域相关性分析"}

直接输出JSON格式结果，不要有额外说明。"""

    for attempt in range(max_retries):
        result_text = None
        raw = ""
        try:
            result_text = call_llm(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=2048,
                temperature=0.2,
                max_retries=1,
            )
            if not result_text or not result_text.strip():
                if attempt < max_retries - 1:
                    time.sleep(2 * (attempt + 1))
                    continue
                return None

            raw = result_text.strip()
            if "```" in raw:
                if "```json" in raw:
                    raw = raw.split("```json")[1].split("```")[0]
                else:
                    raw = raw.split("```")[1].split("```")[0]
            raw = raw.strip()

            result = json.loads(raw)
            if result and "优化后问题" in result and "优化后答案" in result:
                return (
                    str(result["优化后问题"]).strip(),
                    str(result["优化后答案"]).strip(),
                )
        except json.JSONDecodeError:
            try:
                cleaned = _clean_json_string(raw)
                result = json.loads(cleaned)
                if result and "优化后问题" in result and "优化后答案" in result:
                    return (
                        str(result["优化后问题"]).strip(),
                        str(result["优化后答案"]).strip(),
                    )
            except Exception:
                pass
            try:
                pattern = r'"优化后问题"\s*:\s*"((?:[^"\\]|\\.)*)".*?"优化后答案"\s*:\s*"((?:[^"\\]|\\.)*)"'
                match = re.search(pattern, raw, re.DOTALL)
                if match:
                    return (match.group(1).strip(), match.group(2).strip())
            except Exception:
                pass
        except Exception:
            pass

        if attempt < max_retries - 1:
            time.sleep(2 * (attempt + 1))

    return None


def _scan_refinement_candidates(input_dir: str) -> List[str]:
    """扫描 input_dir 下 *_domain_cleaned.json，返回教材名列表。"""
    if not os.path.isdir(input_dir):
        return []
    candidates = []
    for fname in sorted(os.listdir(input_dir)):
        if fname.endswith("_domain_cleaned.json"):
            folder_name = fname.replace("_domain_cleaned.json", "")
            candidates.append(folder_name)
    return candidates


def _load_questions(input_path: str) -> Tuple[List[dict], dict]:
    """加载 JSON 中的 questions 数组及 metadata，兼容 answer/output 字段。"""
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    questions = data.get("questions", [])
    metadata = data.get("metadata", {})
    return questions, metadata


def _load_progress(progress_path: str) -> Optional[Dict[str, Any]]:
    """加载进度：{ "refined": { idx: { question, answer }, ... } }"""
    if not os.path.isfile(progress_path):
        return None
    try:
        with open(progress_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _save_progress(progress_path: str, refined: Dict[int, dict]) -> None:
    """保存进度。"""
    with open(progress_path, "w", encoding="utf-8") as f:
        json.dump({"refined": refined}, f, ensure_ascii=False, indent=2)


def _process_single(
    idx: int,
    item: dict,
    target_scores: List[int],
    taxonomy_items: list,
    domain_name: str,
    max_retries: int,
) -> Tuple[int, Optional[Tuple[str, str]], dict]:
    """处理单个目标分题目，返回 (idx, (优化后问题, 优化后答案) 或 None, item)。"""
    score = item.get("domain_relevance_score")
    if score is None:
        try:
            score = int(item.get("domain_relevance_score", -1))
        except (TypeError, ValueError):
            score = -1
    if score not in target_scores:
        return idx, None, item

    question = str(item.get("question", "")).strip()
    answer = str(item.get("output", item.get("answer", ""))).strip()
    reason = str(item.get("domain_relevance_reason", "")).strip()
    subcategory = item.get("subcategory", "")
    subcategory_or_taxonomy = str(subcategory).strip() if subcategory else _format_taxonomy_for_prompt(taxonomy_items)

    if not question:
        return idx, None, item

    result = _optimize_single(
        question,
        answer,
        reason,
        subcategory_or_taxonomy,
        domain_name,
        max_retries=max_retries,
    )
    return idx, result, item


def run_domain_refinement(
    input_path: str,
    output_dir: str,
    folder_name: str,
    domain_name: str,
    taxonomy_items: Optional[List] = None,
    max_workers: int = 8,
    max_retries: int = 3,
    target_scores: Optional[List[int]] = None,
    threshold_discard: int = 1,
    resume: bool = False,
) -> Tuple[bool, str]:
    """
    执行领域相关性精修：筛选 2–3 分题 -> LLM 优化 -> 与 4-5 分题合并 -> 输出。

    taxonomy_items: config.taxonomy 列表，用于无 subcategory 时拼接参考；可为空。

    Returns:
        (ok, refined_path)
    """
    if target_scores is None:
        target_scores = [2, 3]
    if taxonomy_items is None:
        taxonomy_items = []
    os.makedirs(output_dir, exist_ok=True)
    progress_path = os.path.join(output_dir, f"{folder_name}{PROGRESS_SUFFIX}")
    refined_path = os.path.join(output_dir, f"{folder_name}_domain_refined.json")

    questions, metadata = _load_questions(input_path)
    total = len(questions)
    if total == 0:
        return False, refined_path

    # 筛选 domain_relevance_score in target_scores 的题目索引
    def _score_in_target(q: dict) -> bool:
        s = q.get("domain_relevance_score")
        if s is None:
            return False
        try:
            return int(s) in target_scores
        except (TypeError, ValueError):
            return False


    to_refine_idxs = [i for i, q in enumerate(questions) if _score_in_target(q)]
    if not to_refine_idxs:
        meta_out = {
            **metadata,
            "source": input_path,
            "domain_refinement": {
                "refined_count": 0,
                "unchanged_high": total,
                "failed_kept": 0,
            },
        }
        with open(refined_path, "w", encoding="utf-8") as f:
            json.dump({"questions": questions, "metadata": meta_out}, f, ensure_ascii=False, indent=2)
        print(f"\n无 {target_scores} 分题需要优化，已复制到 {refined_path}")
        return True, refined_path

    # 加载 resume 进度
    refined_by_idx: Dict[int, dict] = {}
    needs_work: List[int] = to_refine_idxs
    if resume:
        prog = _load_progress(progress_path)
        if prog:
            refined_by_idx = prog.get("refined", {})
            for k, v in list(refined_by_idx.items()):
                if isinstance(k, str):
                    refined_by_idx[int(k)] = v
                    del refined_by_idx[k]
            needs_work = [i for i in to_refine_idxs if i not in refined_by_idx]
            if needs_work:
                print(f"Resume: 已优化 {len(refined_by_idx)}/{len(to_refine_idxs)}，剩余 {len(needs_work)} 题")

    api_delay = get_api_delay()
    lock = threading.Lock()

    with tqdm(total=len(needs_work), desc="领域相关性精修", unit="题") as pbar:
        if max_workers <= 1:
            for idx in needs_work:
                item = questions[idx]
                _, result, _ = _process_single(
                    idx, item, target_scores, taxonomy_items, domain_name, max_retries
                )
                if result:
                    q_new, a_new = result
                    with lock:
                        refined_by_idx[idx] = {"question": q_new, "answer": a_new}
                pbar.update(1)
                time.sleep(api_delay)
        else:
            with ThreadPoolExecutor(max_workers=max_workers) as ex:
                futures = {
                    ex.submit(
                        _process_single,
                        idx,
                        questions[idx],
                        target_scores,
                        taxonomy_items,
                        domain_name,
                        max_retries,
                    ): idx
                    for idx in needs_work
                }
                for future in as_completed(futures):
                    idx = futures[future]
                    try:
                        _, result, _ = future.result()
                        if result:
                            q_new, a_new = result
                            with lock:
                                refined_by_idx[idx] = {"question": q_new, "answer": a_new}
                    except Exception:
                        pass
                    pbar.update(1)
                    time.sleep(api_delay)

    _save_progress(progress_path, refined_by_idx)

    # 对优化后题目重评：调用 domain cleaning 的评估逻辑，低分则丢弃
    rescore_results: Dict[int, Tuple[Optional[int], str]] = {}
    for idx in tqdm(refined_by_idx, desc="精修后重评", unit="题"):
        r = refined_by_idx[idx]
        q_new = r.get("question", "")
        a_new = r.get("answer", "")
        score, reason = _evaluate_domain_relevance(
            q_new, a_new, domain_name, max_retries=max_retries
        )
        rescore_results[idx] = (score, reason)
        time.sleep(api_delay)

    # 构建输出：4-5 分题保持不变；2-3 分题替换为优化后，重评仍低分则丢弃
    output_items = []
    refined_count = 0
    discarded_rescore = 0
    failed_kept = 0
    for i in range(total):
        item = dict(questions[i])
        if i in refined_by_idx:
            r = refined_by_idx[i]
            score, reason = rescore_results.get(i, (None, ""))
            if score is not None and score <= threshold_discard:
                discarded_rescore += 1
                continue
            item["question"] = r.get("question", item.get("question"))
            item["answer"] = r.get("answer", item.get("output", item.get("answer", "")))
            if "output" in item:
                item["output"] = item["answer"]
            item["domain_relevance_score"] = score
            item["domain_relevance_reason"] = reason
            item["domain_refinement_applied"] = True
            refined_count += 1
        elif _score_in_target(item):
            failed_kept += 1
        output_items.append(item)

    unchanged_high = total - refined_count - failed_kept - discarded_rescore

    meta_out = {
        **metadata,
        "source": input_path,
        "domain_refinement": {
            "refined_count": refined_count,
            "unchanged_high": unchanged_high,
            "failed_kept": failed_kept,
            "discarded_rescore": discarded_rescore,
        },
    }

    with open(refined_path, "w", encoding="utf-8") as f:
        json.dump({"questions": output_items, "metadata": meta_out}, f, ensure_ascii=False, indent=2)

    print(f"\n3.4 领域精修完成: 优化 {refined_count}，保留原样 {unchanged_high}，失败保留 {failed_kept}，重评低分丢弃 {discarded_rescore}")
    print(f"✓ 输出: {refined_path}")
    return True, refined_path
