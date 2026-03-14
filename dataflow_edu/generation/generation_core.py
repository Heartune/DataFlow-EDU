# -*- coding: utf-8 -*-
"""
两阶段题目生成核心逻辑：Markdown 文本 -> 内容分类分析 -> 题目生成。
支持按 weight 控制题型分布，按题型与能力层级提供不同 Prompt。
"""

import json
import os
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Tuple

import pandas as pd
from tqdm import tqdm

from dataflow_edu.config.schema import (
    AbilityLevelItem,
    EduConfig,
    QuestionType,
    TaxonomyItem,
)
from dataflow_edu.serving import (
    call_llm,
    get_api_delay,
    get_max_workers,
)

SUPPORTED_MD = {".md"}
SAVE_INTERVAL = 5


def load_md_from_folder(folder_path: str) -> List[str]:
    """从文件夹加载所有 Markdown 文件，按文件名排序。"""
    if not os.path.exists(folder_path):
        raise FileNotFoundError(f"Markdown 文件夹不存在: {folder_path}")
    if not os.path.isdir(folder_path):
        raise ValueError(f"路径不是文件夹: {folder_path}")

    md_files = []
    for fname in os.listdir(folder_path):
        ext = Path(fname).suffix.lower()
        if ext in SUPPORTED_MD:
            md_files.append(os.path.join(folder_path, fname))
    md_files.sort(key=lambda x: os.path.basename(x))

    if not md_files:
        raise ValueError(f"文件夹中没有找到 Markdown 文件: {folder_path}")
    return md_files


def get_md_pairs(md_paths: List[str]) -> List[Tuple[str | None, str | None, int, int | None]]:
    """
    每两页一组，返回 [(path1, path2, page1, page2), ...]。
    最后一页单页时 path2=None, page2=None。
    """
    pairs = []
    for i in range(0, len(md_paths), 2):
        p1 = md_paths[i]
        page1 = i + 1
        if i + 1 < len(md_paths):
            pairs.append((p1, md_paths[i + 1], page1, page1 + 1))
        else:
            pairs.append((p1, None, page1, None))
    return pairs


def _format_taxonomy_for_prompt(taxonomy: List[TaxonomyItem]) -> str:
    lines = []
    for t in taxonomy:
        sc = "、".join(t.subcategories) if t.subcategories else "（无）"
        lines.append(f"- {t.name}：{sc}")
    return "\n".join(lines)


def _format_question_types_for_prompt(question_types: List[QuestionType]) -> str:
    names = [q.name for q in question_types]
    return "、".join(names)


def _format_ability_levels_for_prompt(ability_levels: List[AbilityLevelItem]) -> str:
    """将能力层级整理成可插入 Prompt 的文本。"""
    if not ability_levels:
        return ""
    lines = []
    for a in ability_levels:
        sc = "、".join(a.sublevels) if a.sublevels else "（无）"
        desc = f"：{a.description}" if a.description else ""
        lines.append(f"- {a.name}{desc}，子层级：{sc}")
    return "\n".join(lines)


def _allocate_by_weight(items: list, num_slots: int, weight_attr: str = "weight") -> List:
    """
    按 weight 将 num_slots 个槽位分配到 items，返回长度为 num_slots 的序列。
    用于题型、能力层级等的权重分配。当 weight 全为 0 或 items 为空时等分。
    """
    if not items or num_slots <= 0:
        return []
    total = sum(getattr(x, weight_attr, 0.25) for x in items)
    if total <= 0:
        n = len(items)
        base = num_slots // n
        remainder = num_slots % n
        counts = [base + (1 if i < remainder else 0) for i in range(n)]
    else:
        counts = [max(0, round(num_slots * getattr(x, weight_attr, 0) / total)) for x in items]
        current = sum(counts)
        while current < num_slots:
            best_i = max(range(len(items)), key=lambda i: (getattr(items[i], weight_attr, 0), -i))
            counts[best_i] += 1
            current += 1
        while current > num_slots:
            non_zero = [(i, c) for i, c in enumerate(counts) if c > 0]
            if not non_zero:
                break
            worst_i = min(non_zero, key=lambda x: (getattr(items[x[0]], weight_attr, 0), x[0]))[0]
            if counts[worst_i] <= 1:
                counts[worst_i] = 0
            else:
                counts[worst_i] -= 1
            current -= 1
    result = []
    for item, c in zip(items, counts):
        result.extend([item] * c)
    return result[:num_slots]


def _allocate_questions_by_weight(
    question_types: List[QuestionType],
    num_questions: int,
) -> List[Tuple[QuestionType, int]]:
    """
    按 weight 分配各题型数量，确保总和为 num_questions。
    当 num_questions 较小时，round 可能使低权重题型（如判断题 8%）得到 0；
    若某题型 weight >= 0.05 却得到 0，会从最「过剩」的题型挪 1 道以保证覆盖。
    Returns: [(QuestionType, count), ...]，count>0 的题型。
    """
    if not question_types or num_questions <= 0:
        return []
    total_weight = sum(q.weight for q in question_types)
    if total_weight <= 0:
        n = len(question_types)
        base = num_questions // n
        remainder = num_questions % n
        return [(q, base + (1 if i < remainder else 0)) for i, q in enumerate(question_types)]
    allocation: List[Tuple[QuestionType, int]] = []
    for q in question_types:
        count = max(0, round(num_questions * q.weight / total_weight))
        if count > 0:
            allocation.append((q, count))
    current_sum = sum(c for _, c in allocation)
    while current_sum < num_questions:
        best = max(allocation, key=lambda x: (x[0].weight, -allocation.index(x)))
        idx = allocation.index(best)
        allocation[idx] = (best[0], best[1] + 1)
        current_sum += 1
    while current_sum > num_questions:
        worst = min(allocation, key=lambda x: (x[0].weight, allocation.index(x)))
        idx = allocation.index(worst)
        if allocation[idx][1] <= 1:
            allocation.pop(idx)
        else:
            allocation[idx] = (worst[0], worst[1] - 1)
        current_sum -= 1

    # 保证 weight >= 0.05 的题型至少有 1 道（如判断题 8% 在 questions_per_pair=5 时易被 round 为 0）
    MIN_WEIGHT_FOR_ONE = 0.05
    allocated_names = {a[0].name for a in allocation}
    zero_types = [q for q in question_types if q.weight >= MIN_WEIGHT_FOR_ONE and q.name not in allocated_names]
    for q in sorted(zero_types, key=lambda x: -x.weight):
        if not allocation:
            break
        excess = [(i, a) for i, a in enumerate(allocation) if a[1] > 1]
        if excess:
            idx = min(excess, key=lambda x: x[1][0].weight)[0]
            allocation[idx] = (allocation[idx][0], allocation[idx][1] - 1)
            if allocation[idx][1] == 0:
                allocation.pop(idx)
            allocation.append((q, 1))
        else:
            # 每题型均 1 道，用 zero_type 替换权重最小的题型
            idx = min(range(len(allocation)), key=lambda i: allocation[i][0].weight)
            allocation[idx] = (q, 1)
    return [(q, c) for q, c in allocation if c > 0]


def _get_type_specific_instructions(q_type_name: str) -> str:
    """按题型返回针对性的生成说明。"""
    hints = {
        "选择题": "必须包含 A、B、C、D 四个选项，且题干与选项完整独立。",
        "单选题": "必须包含 A、B、C、D 四个选项，只有一个正确答案。",
        "多选题": "必须包含多个选项，明确标注可多选。",
        "填空题": "题干中需留出明确的填空位置（用下划线或括号表示），答案应为填空处的标准作答。",
        "判断题": "题干为陈述句，答案仅为「正确」或「错误」。",
        "简答题": "题干简洁明确，答案要点清晰、分条陈述。",
        "计算题": "题干需给出可计算的数据或情境，答案须包含计算步骤和最终结果。",
        "综合题": "可结合多种考查形式，答案需综合、有层次。",
    }
    for k, v in hints.items():
        if k in q_type_name or q_type_name in k:
            return v
    return "题干与答案须独立完整，无模糊指代。"


def _get_ability_level_prompt_for_batch(
    ability_levels: List[AbilityLevelItem],
    target_ability: AbilityLevelItem | None,
) -> str:
    """为某一能力层级生成针对性的 Prompt 补充。若 target_ability 为 None，则要求覆盖多种能力层级。"""
    if not ability_levels:
        return ""
    if target_ability:
        sc = "、".join(target_ability.sublevels) if target_ability.sublevels else "（无）"
        return (
            f"\n\n【本批重点考察能力】{target_ability.name}（子层级：{sc}）\n"
            f"题目应主要考察该能力层级，答案需体现对应思维层次。"
        )
    ability_str = _format_ability_levels_for_prompt(ability_levels)
    return (
        f"\n\n【考察能力层级】每题需明确标明主要考察的能力层级或子层级：\n{ability_str}\n"
        "请在题目间覆盖不同能力层级，保持多样性。"
    )


def _read_md_content(md_pair: Tuple) -> str:
    """读取页面对应的 Markdown 文本并拼接。"""
    path1, path2, page1, page2 = md_pair
    parts = []
    for p in [path1, path2]:
        if p and os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    parts.append(f.read())
            except Exception:
                parts.append(f"[无法读取: {p}]")
    return "\n\n---\n\n".join(parts) if parts else ""


def analyze_content_taxonomy(
    md_pair: Tuple,
    taxonomy: List[TaxonomyItem],
    question_types: List[QuestionType],
) -> Tuple[List[str], str, bool]:
    """
    阶段1：分析两页内容属于哪些 taxonomy 小类。
    Returns: (subcategories, page_info, failed)
    """
    path1, path2, page1, page2 = md_pair
    page_info = f"{page1}-{page2}" if page2 else str(page1)
    content = _read_md_content(md_pair)
    if not content.strip():
        return [], page_info, True

    tax_str = _format_taxonomy_for_prompt(taxonomy)
    sys_prompt = """你是学科教材内容分析专家。根据给定的学科分类体系，分析教材页面内容属于哪些知识小类。
只输出 JSON 数组，包含匹配的小类名称，如 ["XXX", "XXXX"]。
无匹配时返回空数组 []。不要输出任何解释。"""

    user_prompt = f"""【学科分类体系】
{tax_str}

【教材内容（第{page_info}页）】
{content[:8000]}

请输出匹配的小类名称 JSON 数组。"""

    result = call_llm(sys_prompt, user_prompt, max_tokens=1024, temperature=0.2)
    if not result:
        return [], page_info, True

    try:
        raw = result.strip()
        if "```" in raw:
            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0]
            else:
                raw = raw.split("```")[1].split("```")[0]
        arr = json.loads(raw)
        if not isinstance(arr, list):
            arr = []
        valid = [s for s in arr if isinstance(s, str) and s.strip()]
        return valid if valid else [], page_info, False
    except json.JSONDecodeError:
        return [], page_info, True


def _generate_questions_single_type(
    md_pair: Tuple,
    subcategories: List[str],
    q_type: QuestionType,
    count: int,
    ability_levels: List[AbilityLevelItem],
    target_ability: AbilityLevelItem | None,
    page_info: str,
    content: str,
    sc_str: str,
) -> List[dict]:
    """
    针对单一题型与（可选）目标能力层级生成题目，使用定制化 Prompt。
    """
    type_hint = _get_type_specific_instructions(q_type.name)
    ability_hint = _get_ability_level_prompt_for_batch(ability_levels, target_ability)

    sys_prompt = f"""你是学科习题命题专家。根据教材内容生成指定题型的习题。
【本题型】{q_type.name}
【本题型要求】{type_hint}
每题必须独立完整，题干中不得出现「根据上文」「文中提到」等指代。"""
    sys_prompt += ability_hint

    user_prompt = f"""【教材内容（第{page_info}页）】
{content[:8000]}

【知识小类】{sc_str}

请生成 {count} 道【{q_type.name}】习题，输出纯 JSON 数组，每道题格式：
{{"question": "题干", "answer": "标准答案", "type": "{q_type.name}", "subcategory": "小类名", "ability_level": "能力层级名或子层级名", "difficulty": "难/中/易"}}
type 固定为 "{q_type.name}"，ability_level 从配置的能力层级或子层级中选择。"""

    result = call_llm(sys_prompt, user_prompt, max_tokens=4096, temperature=0.6)
    if not result:
        return []

    try:
        raw = result.strip()
        if "```" in raw:
            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0]
            else:
                raw = raw.split("```")[1].split("```")[0]
        arr = json.loads(raw)
        if not isinstance(arr, list):
            arr = [arr] if arr else []
        questions = []
        for q in arr:
            if not isinstance(q, dict) or not q.get("question"):
                continue
            questions.append({
                "question": str(q.get("question", "")).strip(),
                "answer": str(q.get("answer", "")).strip() or "无",
                "type": q_type.name,
                "subcategory": str(q.get("subcategory", sc_str)).strip(),
                "ability_level": str(q.get("ability_level", "")).strip() or "通用",
                "difficulty": str(q.get("difficulty", "中")).strip(),
                "source_page": page_info,
            })
        time.sleep(get_api_delay())
        return questions
    except json.JSONDecodeError:
        return []


def generate_questions_for_balance(
    md_pair: Tuple,
    subcategories: List[str],
    q_type: QuestionType,
    target_ability_sublevel: str,
    count: int,
) -> List[dict]:
    """
    为 Balancing 定向生成题目：指定题型与能力子层级。
    供 2.2 Balancing Operator 补题时调用。

    Args:
        md_pair: 页面对 (path1, path2, page1, page2)
        subcategories: 知识小类
        q_type: 目标题型
        target_ability_sublevel: 目标能力子层级名（如「结构与功能观」）
        count: 生成数量

    Returns:
        题目列表，格式与 generate_questions 一致
    """
    path1, path2, page1, page2 = md_pair
    page_info = f"{page1}-{page2}" if page2 else str(page1)
    content = _read_md_content(md_pair)
    if not content.strip() or count <= 0:
        return []

    sc_str = "、".join(subcategories) if subcategories else "通用"
    type_hint = _get_type_specific_instructions(q_type.name)
    ability_hint = (
        f"\n\n【本批重点考察能力】{target_ability_sublevel}\n"
        "题目必须主要考察该能力子层级，答案需体现对应思维层次。"
    )

    sys_prompt = f"""你是学科习题命题专家。根据教材内容生成指定题型的习题。
【本题型】{q_type.name}
【本题型要求】{type_hint}
每题必须独立完整，题干中不得出现「根据上文」「文中提到」等指代。"""
    sys_prompt += ability_hint

    user_prompt = f"""【教材内容（第{page_info}页）】
{content[:8000]}

【知识小类】{sc_str}

请生成 {count} 道【{q_type.name}】习题，输出纯 JSON 数组，每道题格式：
{{"question": "题干", "answer": "标准答案", "type": "{q_type.name}", "subcategory": "小类名", "ability_level": "{target_ability_sublevel}", "difficulty": "难/中/易"}}
type 固定为 "{q_type.name}"，ability_level 固定为 "{target_ability_sublevel}"。"""

    result = call_llm(sys_prompt, user_prompt, max_tokens=4096, temperature=0.6)
    if not result:
        return []

    try:
        raw = result.strip()
        if "```" in raw:
            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0]
            else:
                raw = raw.split("```")[1].split("```")[0]
        arr = json.loads(raw)
        if not isinstance(arr, list):
            arr = [arr] if arr else []
        questions = []
        for q in arr:
            if not isinstance(q, dict) or not q.get("question"):
                continue
            questions.append({
                "question": str(q.get("question", "")).strip(),
                "answer": str(q.get("answer", "")).strip() or "无",
                "type": q_type.name,
                "subcategory": str(q.get("subcategory", sc_str)).strip(),
                "ability_level": str(q.get("ability_level", target_ability_sublevel)).strip() or target_ability_sublevel,
                "difficulty": str(q.get("difficulty", "中")).strip(),
                "source_page": page_info,
            })
        time.sleep(get_api_delay())
        return questions
    except json.JSONDecodeError:
        return []


def generate_questions(
    md_pair: Tuple,
    subcategories: List[str],
    question_types: List[QuestionType],
    ability_levels: List[AbilityLevelItem],
    num_questions: int,
) -> List[dict]:
    """
    阶段2：根据 content、小类、按 weight 分配题型数量，使用题型与能力层级不同的 Prompt 生成题目。
    返回题目列表，每题含 question, answer, type, subcategory, ability_level, difficulty, source_page。
    """
    path1, path2, page1, page2 = md_pair
    page_info = f"{page1}-{page2}" if page2 else str(page1)
    content = _read_md_content(md_pair)
    if not content.strip():
        return []

    sc_str = "、".join(subcategories) if subcategories else "通用"
    allocation = _allocate_questions_by_weight(question_types, num_questions)
    if not allocation:
        if question_types:
            allocation = [(question_types[0], num_questions)]
        else:
            return []

    all_questions = []
    ability_list = ability_levels or []
    # 按 weight 将能力层级分配到各题型批次，无 weight 或全 0 时等分
    ability_sequence = (
        _allocate_by_weight(ability_list, len(allocation), "weight")
        if ability_list
        else [None] * len(allocation)
    )
    for i, (q_type, count) in enumerate(allocation):
        target_ability = ability_sequence[i] if i < len(ability_sequence) else None
        qs = _generate_questions_single_type(
            md_pair=md_pair,
            subcategories=subcategories,
            q_type=q_type,
            count=count,
            ability_levels=ability_levels,
            target_ability=target_ability,
            page_info=page_info,
            content=content,
            sc_str=sc_str,
        )
        all_questions.extend(qs)

    return all_questions


def process_page_pair_stage1(pair_data, taxonomy: List[TaxonomyItem], question_types: List[QuestionType]):
    """阶段1 单对处理。Returns: (subcategories, page_info, failed) for completed_pairs dict."""
    subcats, page_info, failed = analyze_content_taxonomy(pair_data, taxonomy, question_types)
    return subcats, page_info, failed


def process_page_pair_stage2(
    pair_data,
    subcategories: List[str],
    question_types: List[QuestionType],
    ability_levels: List[AbilityLevelItem],
    num_questions: int,
):
    """阶段2 单对处理。Returns: (questions, page_info)."""
    if not subcategories:
        subcategories = ["通用"]
    questions = generate_questions(
        pair_data, subcategories, question_types, ability_levels, num_questions
    )
    _, _, page1, page2 = pair_data
    page_info = f"{page1}-{page2}" if page2 else str(page1)
    return questions, page_info


def get_stage1_dir(output_dir: str) -> str:
    """dataflow_edu/data/generation_and_balancing 下 2_1_generated_stage_1 目录。"""
    d = os.path.join(output_dir, "2_1_generated_stage_1")
    os.makedirs(d, exist_ok=True)
    return d


def get_stage2_dir(output_dir: str) -> str:
    """dataflow_edu/data/generation_and_balancing 下 2_1_generated_stage_2 目录。"""
    d = os.path.join(output_dir, "2_1_generated_stage_2")
    os.makedirs(d, exist_ok=True)
    return d


def get_balanced_dir(output_dir: str) -> str:
    """dataflow_edu/data/generation_and_balancing 下 2_2_balanced 目录。2.2 Balancing 输出。"""
    d = os.path.join(output_dir, "2_2_balanced")
    os.makedirs(d, exist_ok=True)
    return d


def get_stage1_output_path(md_folder: str, output_dir: str) -> str:
    folder_name = os.path.basename(os.path.normpath(md_folder))
    stage1_dir = get_stage1_dir(output_dir)
    return os.path.join(stage1_dir, f"{folder_name}_stage1_taxonomy.json")


def _save_stage1_json(stage1_file: str, md_folder: str, total_pages: int, total_pairs: int, completed_pairs: dict):
    folder_name = os.path.basename(os.path.normpath(md_folder))
    data = {
        "source_folder": md_folder,
        "folder_name": folder_name,
        "total_pages": total_pages,
        "total_pairs": total_pairs,
        "pairs": [completed_pairs[k] for k in sorted(completed_pairs.keys())],
    }
    with open(stage1_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def run_stage1(
    md_folder: str,
    output_dir: str,
    config: EduConfig,
    max_workers: int = 8,
    resume: bool = False,
    tiny: int = 0,
    tiny_seed: int = 42,
) -> Tuple[bool, str | None]:
    """
    阶段1：内容分类分析，结果保存到 {folder_name}_stage1_taxonomy.json
    Returns: (success, stage1_file_path)
    """
    taxonomy = config.taxonomy
    question_types = config.question_types
    md_paths = load_md_from_folder(md_folder)
    total_pages = len(md_paths)
    page_pairs = get_md_pairs(md_paths)
    total_pairs = len(page_pairs)

    if tiny > 0 and tiny < total_pairs:
        random.seed(tiny_seed)
        idxs = sorted(random.sample(range(total_pairs), tiny))
        page_pairs = [page_pairs[i] for i in idxs]
        total_pairs = len(page_pairs)
        print(f"  [Tiny] 抽取 {tiny} 组 (seed={tiny_seed})")

    stage1_file = get_stage1_output_path(md_folder, output_dir)
    completed_pairs = {}
    failed_indices = []
    if resume and os.path.exists(stage1_file):
        try:
            with open(stage1_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            for p in data.get("pairs", []):
                idx = p["pair_index"]
                if p.get("failed", False):
                    failed_indices.append(idx)
                else:
                    completed_pairs[idx] = p
            print(f"  从进度恢复：已完成 {len(completed_pairs)} 组，失败 {len(failed_indices)} 组待重跑")
        except Exception:
            pass

    pending = sorted(set(i for i in range(total_pairs) if i not in completed_pairs) | set(failed_indices))
    if not pending:
        print("  阶段1 已全部完成")
        return True, stage1_file

    def task(idx):
        pair = page_pairs[idx]
        subcats, page_info, failed = process_page_pair_stage1(pair, taxonomy, question_types)
        path1, path2, p1, p2 = pair
        return idx, {
            "pair_index": idx,
            "page_info": page_info,
            "md1_path": path1,
            "md2_path": path2,
            "subcategories": subcats,
            "failed": failed,
        }

    with tqdm(total=total_pairs, desc="阶段1-内容分类", unit="组", initial=len(completed_pairs)) as pbar:
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = {ex.submit(task, i): i for i in pending}
            for fut in as_completed(futures):
                idx = futures[fut]
                try:
                    i, info = fut.result()
                    completed_pairs[i] = info
                except Exception as e:
                    pair = page_pairs[idx]
                    _, _, p1, p2 = pair
                    page_info = f"{p1}-{p2}" if p2 else str(p1)
                    completed_pairs[idx] = {
                        "pair_index": idx,
                        "page_info": page_info,
                        "md1_path": pair[0],
                        "md2_path": pair[1],
                        "subcategories": [],
                        "failed": True,
                        "error": str(e),
                    }
                pbar.update(1)
                if (len(completed_pairs)) % SAVE_INTERVAL == 0:
                    _save_stage1_json(stage1_file, md_folder, total_pages, total_pairs, completed_pairs)

    _save_stage1_json(stage1_file, md_folder, total_pages, total_pairs, completed_pairs)
    success_count = sum(1 for p in completed_pairs.values() if not p.get("failed", False))
    print(f"  阶段1 完成：成功 {success_count}/{total_pairs} 组")
    return True, stage1_file


def run_stage2(
    md_folder: str,
    output_dir: str,
    config: EduConfig,
    stage1_file: str,
    questions_per_pair: int = 5,
    max_workers: int = 8,
    resume: bool = False,
    pair_start: int | None = None,
    pair_end: int | None = None,
    tiny: int = 0,
    tiny_seed: int = 42,
) -> Tuple[bool, str | None, str | None]:
    """
    阶段2：题目生成，输出 Excel + JSON。
    Returns: (success, excel_path, json_path)
    """
    with open(stage1_file, "r", encoding="utf-8") as f:
        stage1_data = json.load(f)
    pairs_info = {p["pair_index"]: p for p in stage1_data["pairs"]}
    folder_name = stage1_data.get("folder_name", os.path.basename(os.path.normpath(md_folder)))
    md_paths = load_md_from_folder(md_folder)
    page_pairs = get_md_pairs(md_paths)
    question_types = config.question_types
    ability_levels = config.ability_levels

    indices_to_process = sorted(pairs_info.keys())
    if pair_start is not None or pair_end is not None:
        start = pair_start if pair_start is not None else 0
        end = pair_end if pair_end is not None else len(page_pairs)
        indices_to_process = [i for i in indices_to_process if start <= i < end]

    stage2_dir = get_stage2_dir(output_dir)
    partial_path = os.path.join(stage2_dir, f"{folder_name}_stage2_partial.json")

    results_by_idx = {}
    if resume and os.path.isfile(partial_path):
        try:
            with open(partial_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            results_by_idx = {int(k): v for k, v in data.get("results_by_idx", {}).items()}
            if results_by_idx:
                print(f"  从进度恢复：已完成 {len(results_by_idx)} 组")
        except Exception:
            pass

    pending = [i for i in indices_to_process if i not in results_by_idx]
    if not pending:
        print("  阶段2 已全部完成")
    else:

        def task(idx: int):
            if idx >= len(page_pairs):
                return idx, []
            pair = page_pairs[idx]
            info = pairs_info.get(idx, {})
            subcats = info.get("subcategories", [])
            if info.get("failed", False) and not subcats:
                subcats = ["通用"]
            qs, _ = process_page_pair_stage2(
                pair, subcats, question_types, ability_levels, questions_per_pair
            )
            return idx, qs

        def save_partial():
            with open(partial_path, "w", encoding="utf-8") as f:
                json.dump(
                    {"results_by_idx": {str(k): v for k, v in results_by_idx.items()}},
                    f,
                    ensure_ascii=False,
                    indent=2,
                )

        with tqdm(
            total=len(indices_to_process),
            desc="阶段2-题目生成",
            unit="组",
            initial=len(results_by_idx),
        ) as pbar:
            with ThreadPoolExecutor(max_workers=max_workers) as ex:
                futures = {ex.submit(task, idx): idx for idx in pending}
                for fut in as_completed(futures):
                    try:
                        idx, qs = fut.result()
                        results_by_idx[idx] = qs
                    except Exception:
                        results_by_idx[futures[fut]] = []
                    pbar.update(1)
                    if len(results_by_idx) % SAVE_INTERVAL == 0:
                        save_partial()

    all_questions = []
    for idx in sorted(results_by_idx.keys()):
        all_questions.extend(results_by_idx[idx])

    if os.path.isfile(partial_path):
        try:
            os.remove(partial_path)
        except OSError:
            pass

    excel_path = os.path.join(stage2_dir, f"{folder_name}_generated_questions.xlsx")
    json_path = os.path.join(stage2_dir, f"{folder_name}_generated_questions.json")

    # Excel：题目、标准答案、题型、知识小类、能力层级、难度、来源页码
    rows = []
    for i, q in enumerate(all_questions, 1):
        rows.append({
            "序号": i,
            "题目": q.get("question", ""),
            "标准答案": q.get("answer", ""),
            "题型": q.get("type", ""),
            "知识小类": q.get("subcategory", ""),
            "能力层级": q.get("ability_level", "通用"),
            "难度": q.get("difficulty", "中"),
            "来源页码": q.get("source_page", ""),
        })
    df = pd.DataFrame(rows)
    df.to_excel(excel_path, index=False, sheet_name="题目")
    print(f"  Excel 已保存: {excel_path} ({len(rows)} 道题)")

    meta = {"source": md_folder, "stage1_file": stage1_file, "total": len(all_questions)}
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"questions": all_questions, "metadata": meta}, f, ensure_ascii=False, indent=2)
    print(f"  JSON 已保存: {json_path}")

    return True, excel_path, json_path
