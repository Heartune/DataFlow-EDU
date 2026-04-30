# -*- coding: utf-8 -*-
"""
两阶段题目生成核心逻辑：Markdown 文本 -> 内容分类分析 -> 题目生成。
阶段2 按 weight 构造随机题型序列，每个 pair 从序列按序取槽位指定题型，整体分布符合目标。
"""

import json
import os
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, List, Optional, Set, Tuple, Union

import pandas as pd
from tqdm import tqdm

from dataflow_edu.config.schema import (
    AbilityLevelItem,
    EduConfig,
    QuestionType,
    TaxonomyItem,
)
from dataflow_edu.generation.prompt_loader import get_type_hint, load_prompts
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


def _build_subcat_to_category(taxonomy: List[TaxonomyItem]) -> Dict[str, str]:
    """从 taxonomy 构建 小类 -> 大类 映射。"""
    m = {}
    for t in taxonomy:
        for sc in (t.subcategories or []):
            if sc and sc.strip():
                m[sc.strip()] = t.name
    return m


def _build_subcat_whitelist(taxonomy: List[TaxonomyItem], include_generic: bool = True) -> set:
    """从 taxonomy 构建小类白名单（set）。include_generic 为 True 时加入「通用」。"""
    whitelist = set()
    for t in taxonomy:
        for sc in (t.subcategories or []):
            if sc and sc.strip():
                whitelist.add(sc.strip())
    if include_generic:
        whitelist.add("通用")
    return whitelist


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


def _build_shuffled_type_sequence(
    question_types: List[QuestionType],
    total_slots: int,
    seed: int | None = None,
) -> List[QuestionType]:
    """
    按 weight 构造总槽位数的题型序列，随机打乱后返回。
    用于 2.1 阶段「按题轮转」：每个 pair 从序列中按序取 questions_per_pair 个槽位。
    """
    if not question_types or total_slots <= 0:
        return []
    rng = random.Random(seed) if seed is not None else random
    total_weight = sum(q.weight for q in question_types)
    if total_weight <= 0:
        n = len(question_types)
        base = total_slots // n
        remainder = total_slots % n
        counts = [base + (1 if i < remainder else 0) for i in range(n)]
    else:
        counts = [max(0, round(total_slots * q.weight / total_weight)) for q in question_types]
        current = sum(counts)
        while current < total_slots:
            best_i = max(range(len(question_types)), key=lambda i: (question_types[i].weight, -i))
            counts[best_i] += 1
            current += 1
        while current > total_slots:
            non_zero = [(i, c) for i, c in enumerate(counts) if c > 0]
            if not non_zero:
                break
            worst_i = min(non_zero, key=lambda x: (question_types[x[0]].weight, x[0]))[0]
            if counts[worst_i] <= 1:
                counts[worst_i] = 0
            else:
                counts[worst_i] -= 1
            current -= 1
    sequence: List[QuestionType] = []
    for q, c in zip(question_types, counts):
        sequence.extend([q] * c)
    rng.shuffle(sequence)
    return sequence[:total_slots]


def _sublevel_to_main(ability_level: str, ability_levels: List[AbilityLevelItem]) -> str:
    """
    由子层级名反查主层级。配置中每个子层级只属于一个主层级。
    找不到时返回空字符串（槽位设计下应能映射）。
    """
    if not ability_level or not ability_level.strip():
        return ""
    al = ability_level.strip()
    for a in ability_levels or []:
        if a.sublevels:
            if al in a.sublevels:
                return a.name
        else:
            if al == a.name:
                return a.name
    return ""


def _expand_ability_levels_to_sublevels(
    ability_levels: List[AbilityLevelItem],
) -> List[Tuple[str, float]]:
    """
    将 ability_levels 展开为子层级及权重列表。
    有 sublevels 时：每个子层级权重 = item.weight / len(sublevels)
    无 sublevels 时：用 item.name 作为子层级，权重 = item.weight
    Returns: [(sublevel_name, weight), ...]
    """
    result: List[Tuple[str, float]] = []
    for a in ability_levels:
        if a.sublevels:
            per_sub = a.weight / len(a.sublevels)
            for sub in a.sublevels:
                result.append((sub, per_sub))
        else:
            result.append((a.name, a.weight))
    return result


def _build_shuffled_ability_sequence(
    ability_levels: List[AbilityLevelItem],
    total_slots: int,
    seed: int | None = None,
) -> List[str | None]:
    """
    按 weight 将能力层级展开为子层级，分配 total_slots 个槽位，随机打乱后返回子层级名列表。
    与题型一致：每个 pair 从序列中按序取 questions_per_pair 个槽位。
    """
    if total_slots <= 0:
        return []
    if not ability_levels:
        return [None] * total_slots
    expanded = _expand_ability_levels_to_sublevels(ability_levels)
    if not expanded:
        return [None] * total_slots
    # 使用带 weight 的对象以复用 _allocate_by_weight
    items = [SimpleNamespace(name=name, weight=w) for name, w in expanded]
    allocated = _allocate_by_weight(items, total_slots, "weight")
    names = [x.name for x in allocated]
    rng = random.Random(seed) if seed is not None else random
    rng.shuffle(names)
    return names[:total_slots]


def _get_type_specific_instructions(q_type_name: str, subject: str = "") -> str:
    """按题型返回针对性的生成说明，优先从学科 prompt YAML 加载。"""
    return get_type_hint(load_prompts(subject), q_type_name)


def _get_ability_level_prompt_for_batch(
    ability_levels: List[AbilityLevelItem],
    target_ability: str | None,
) -> str:
    """为某一能力层级生成针对性的 Prompt 补充。若 target_ability 为 None，则要求覆盖多种能力层级。"""
    if not ability_levels:
        return ""
    if target_ability:
        return (
            f"\n\n【本批重点考察能力】{target_ability}\n"
            "题目应主要考察该能力层级，答案需体现对应思维层次。"
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
    subject: str = "",
) -> Tuple[List[str], str, bool]:
    """
    阶段1：分析两页内容属于哪些 taxonomy 小类。
    白名单校验：返回的小类必须在 taxonomy 内；非法则重试最多 3 次，仍失败则 marked failed。
    Returns: (subcategories, page_info, failed)
    """
    path1, path2, page1, page2 = md_pair
    page_info = f"{page1}-{page2}" if page2 else str(page1)
    content = _read_md_content(md_pair)
    if not content.strip():
        return [], page_info, True

    whitelist = _build_subcat_whitelist(taxonomy or [])
    tax_str = _format_taxonomy_for_prompt(taxonomy)
    prompts = load_prompts(subject)
    sys_prompt = prompts.get("taxonomy_analysis_system", "").strip()

    user_prompt = f"""【学科分类体系】
{tax_str}

【教材内容（第{page_info}页）】
{content[:8000]}

请输出匹配的小类名称 JSON 数组。"""

    for attempt in range(4):  # 首次 + 3 次重试
        result = call_llm(sys_prompt, user_prompt, max_tokens=1024, temperature=0.2)
        if not result:
            if attempt < 3:
                time.sleep(get_api_delay())
                continue
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
            valid = [s.strip() for s in arr if isinstance(s, str) and s.strip()]
            # 白名单校验：任一小类不在白名单内则重试
            if valid and any(s not in whitelist for s in valid):
                if attempt < 3:
                    time.sleep(get_api_delay())
                    continue
                return [], page_info, True
            return valid if valid else [], page_info, False
        except json.JSONDecodeError:
            # 解析失败不重试，直接 failed
            return [], page_info, True

    return [], page_info, True


def _generate_questions_single_type(
    md_pair: Tuple,
    subcategories: List[str],
    q_type: QuestionType,
    count: int,
    ability_levels: List[AbilityLevelItem],
    target_ability: str | None,
    page_info: str,
    content: str,
    sc_str: str,
    subcat_to_cat: Dict[str, str],
    subcat_whitelist: Optional[Set[str]] = None,
    max_retries: int = 3,
    subject: str = "",
) -> List[dict]:
    """
    针对单一题型与（可选）目标能力子层级生成题目。当 target_ability 非空时，写死 ability_level 为该值。
    白名单校验：subcategory 必须在 subcat_whitelist 内；非法则重试最多 max_retries 次，仍失败返回 []。
    """
    whitelist = subcat_whitelist if subcat_whitelist is not None else (set(subcat_to_cat.keys()) | {"通用"})
    type_hint = _get_type_specific_instructions(q_type.name, subject)
    ability_hint = _get_ability_level_prompt_for_batch(ability_levels, target_ability)

    prompts = load_prompts(subject)
    prefix = prompts.get("question_generation_system_prefix", "你是学科习题命题专家。根据教材内容生成指定题型的习题。")
    sys_prompt = f"""{prefix}
【本题型】{q_type.name}
【本题型要求】{type_hint}
每题必须独立完整，题干中不得出现「根据上文」「文中提到」等指代。"""
    sys_prompt += ability_hint

    user_prompt = f"""【教材内容（第{page_info}页）】
{content[:8000]}

【知识小类】{sc_str}

请生成 {count} 道【{q_type.name}】习题，输出纯 JSON 数组，每道题格式：
{{"question": "题干", "answer": "标准答案", "type": "{q_type.name}", "subcategory": "小类名", "ability_level": "能力层级名或子层级名", "difficulty": "难/中/易"}}
type 固定为 "{q_type.name}"，ability_level 从配置的能力层级或子层级中选择。subcategory 必须从【知识小类】中选取。"""

    for attempt in range(max_retries + 1):
        result = call_llm(sys_prompt, user_prompt, max_tokens=4096, temperature=0.6)
        if not result:
            if attempt < max_retries:
                time.sleep(get_api_delay())
                continue
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
            invalid = False
            for q in arr:
                if not isinstance(q, dict) or not q.get("question"):
                    continue
                # 槽位已分配目标能力时写死；无槽位（ability_levels 为空）默认不发生，用「通用」
                final_level = target_ability if target_ability else "通用"
                sc_final = str(q.get("subcategory", sc_str)).strip()
                if sc_final not in whitelist:
                    invalid = True
                    break
                questions.append({
                    "question": str(q.get("question", "")).strip(),
                    "answer": str(q.get("answer", "")).strip() or "无",
                    "type": q_type.name,
                    "subcategory": sc_final,
                    "category": subcat_to_cat.get(sc_final, ""),
                    "ability_level": final_level,
                    "ability_main": _sublevel_to_main(final_level, ability_levels),
                    "difficulty": str(q.get("difficulty", "中")).strip(),
                    "source_page": page_info,
                })
            if invalid and attempt < max_retries:
                time.sleep(get_api_delay())
                continue
            if invalid:
                return []
            time.sleep(get_api_delay())
            return questions
        except json.JSONDecodeError:
            if attempt < max_retries:
                time.sleep(get_api_delay())
                continue
            return []


def generate_questions_for_balance(
    md_pair: Tuple,
    subcategories: List[str],
    q_type: QuestionType,
    target_ability_sublevel: str,
    count: int,
    subcat_to_cat: Dict[str, str],
    ability_levels: Optional[List[AbilityLevelItem]] = None,
    subject: str = "",
) -> List[dict]:
    """
    为 Balancing 定向生成题目：指定题型与能力子层级。
    供 2.2 Balancing Operator 补题时调用。
    白名单校验：subcategory 必须在 subcat_to_cat 或「通用」内；非法则重试最多 3 次，仍失败返回 []。

    Args:
        md_pair: 页面对 (path1, path2, page1, page2)
        subcategories: 知识小类
        q_type: 目标题型
        target_ability_sublevel: 目标能力子层级名（如「结构与功能观」）
        count: 生成数量
        subcat_to_cat: 小类->大类映射
        ability_levels: 能力层级配置，用于反查 ability_main
        subject: 学科名称，用于加载对应 prompt 模板

    Returns:
        题目列表，格式与 generate_questions 一致
    """
    path1, path2, page1, page2 = md_pair
    page_info = f"{page1}-{page2}" if page2 else str(page1)
    content = _read_md_content(md_pair)
    if not content.strip() or count <= 0:
        return []

    whitelist = set(subcat_to_cat.keys()) | {"通用"}
    sc_str = "、".join(subcategories) if subcategories else "通用"
    type_hint = _get_type_specific_instructions(q_type.name, subject)
    ability_hint = (
        f"\n\n【本批重点考察能力】{target_ability_sublevel}\n"
        "题目必须主要考察该能力子层级，答案需体现对应思维层次。"
    )

    prompts = load_prompts(subject)
    prefix = prompts.get("question_generation_system_prefix", "你是学科习题命题专家。根据教材内容生成指定题型的习题。")
    sys_prompt = f"""{prefix}
【本题型】{q_type.name}
【本题型要求】{type_hint}
每题必须独立完整，题干中不得出现「根据上文」「文中提到」等指代。"""
    sys_prompt += ability_hint

    user_prompt = f"""【教材内容（第{page_info}页）】
{content[:8000]}

【知识小类】{sc_str}

请生成 {count} 道【{q_type.name}】习题，输出纯 JSON 数组，每道题格式：
{{"question": "题干", "answer": "标准答案", "type": "{q_type.name}", "subcategory": "小类名", "difficulty": "难/中/易"}}
type 固定为 "{q_type.name}"。subcategory 必须从【知识小类】中选取。"""

    for attempt in range(4):  # 首次 + 3 次重试
        result = call_llm(sys_prompt, user_prompt, max_tokens=4096, temperature=0.6)
        if not result:
            if attempt < 3:
                time.sleep(get_api_delay())
                continue
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
            invalid = False
            for q in arr:
                if not isinstance(q, dict) or not q.get("question"):
                    continue
                sc_final = str(q.get("subcategory", sc_str)).strip()
                if sc_final not in whitelist:
                    invalid = True
                    break
                questions.append({
                    "question": str(q.get("question", "")).strip(),
                    "answer": str(q.get("answer", "")).strip() or "无",
                    "type": q_type.name,
                    "subcategory": sc_final,
                    "category": subcat_to_cat.get(sc_final, ""),
                    "ability_level": target_ability_sublevel,
                    "ability_main": _sublevel_to_main(target_ability_sublevel, ability_levels or []),
                    "difficulty": str(q.get("difficulty", "中")).strip(),
                    "source_page": page_info,
                })
            if invalid and attempt < 3:
                time.sleep(get_api_delay())
                continue
            if invalid:
                return []
            time.sleep(get_api_delay())
            return questions
        except json.JSONDecodeError:
            if attempt < 3:
                time.sleep(get_api_delay())
                continue
            return []


def generate_questions(
    md_pair: Tuple,
    subcategories: List[str],
    question_types: List[QuestionType],
    ability_levels: List[AbilityLevelItem],
    num_questions: int,
    allocation: Optional[
        List[Union[Tuple[QuestionType, int, Optional[str]], Tuple[QuestionType, int]]]
    ] = None,
    taxonomy: Optional[List[TaxonomyItem]] = None,
    subject: str = "",
) -> List[dict]:
    """
    阶段2：根据 content、小类、题型分配，使用题型与能力层级不同的 Prompt 生成题目。
    返回题目列表，每题含 question, answer, type, subcategory, ability_level, difficulty, source_page。
    若 allocation 为 None，退化为使用第一种题型生成 num_questions 道（兼容其他调用）。
    """
    path1, path2, page1, page2 = md_pair
    page_info = f"{page1}-{page2}" if page2 else str(page1)
    content = _read_md_content(md_pair)
    if not content.strip():
        return []

    sc_str = "、".join(subcategories) if subcategories else "通用"
    subcat_to_cat = _build_subcat_to_category(taxonomy or [])
    subcat_whitelist = _build_subcat_whitelist(taxonomy or [])
    if allocation is None or not allocation:
        if question_types:
            allocation = [(question_types[0], num_questions)]
        else:
            return []

    all_questions = []
    for item in allocation:
        q_type, count = item[0], item[1]
        target_ability = item[2] if len(item) >= 3 else None
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
            subcat_to_cat=subcat_to_cat,
            subcat_whitelist=subcat_whitelist,
            subject=subject,
        )
        all_questions.extend(qs)

    return all_questions


def process_page_pair_stage1(
    pair_data,
    taxonomy: List[TaxonomyItem],
    question_types: List[QuestionType],
    subject: str = "",
):
    """阶段1 单对处理。Returns: (subcategories, page_info, failed) for completed_pairs dict."""
    subcats, page_info, failed = analyze_content_taxonomy(pair_data, taxonomy, question_types, subject=subject)
    return subcats, page_info, failed


def process_page_pair_stage2(
    pair_data,
    subcategories: List[str],
    question_types: List[QuestionType],
    ability_levels: List[AbilityLevelItem],
    num_questions: int,
    allocation: Optional[
        List[Union[Tuple[QuestionType, int, Optional[str]], Tuple[QuestionType, int]]]
    ] = None,
    taxonomy: Optional[List[TaxonomyItem]] = None,
    subject: str = "",
):
    """阶段2 单对处理。Returns: (questions, page_info)."""
    if not subcategories:
        subcategories = ["通用"]
    questions = generate_questions(
        pair_data, subcategories, question_types, ability_levels, num_questions,
        allocation=allocation, taxonomy=taxonomy, subject=subject,
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

    subject = config.subject or ""

    def task(idx):
        pair = page_pairs[idx]
        subcats, page_info, failed = process_page_pair_stage1(pair, taxonomy, question_types, subject=subject)
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
        total_slots = len(indices_to_process) * questions_per_pair
        type_sequence = _build_shuffled_type_sequence(question_types, total_slots, seed=42)
        ability_sequence = _build_shuffled_ability_sequence(ability_levels or [], total_slots, seed=42)
        sorted_indices = sorted(indices_to_process)
        rank_of_idx = {idx: k for k, idx in enumerate(sorted_indices)}

        subject = config.subject or ""

        def task(idx: int):
            if idx >= len(page_pairs):
                return idx, []
            pair = page_pairs[idx]
            info = pairs_info.get(idx, {})
            subcats = info.get("subcategories", [])
            if info.get("failed", False) and not subcats:
                subcats = ["通用"]
            rank = rank_of_idx.get(idx, 0)
            offset = rank * questions_per_pair
            type_slice = type_sequence[offset : offset + questions_per_pair]
            ability_slice = ability_sequence[offset : offset + questions_per_pair]
            allocation = [(type_slice[i], 1, ability_slice[i]) for i in range(questions_per_pair)]
            qs, _ = process_page_pair_stage2(
                pair,
                subcats,
                question_types,
                ability_levels,
                questions_per_pair,
                allocation=allocation,
                taxonomy=config.taxonomy,
                subject=subject,
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

    # Excel：题目、标准答案、题型、知识大类、知识小类、能力层级、能力主层级、难度、来源页码
    rows = []
    for i, q in enumerate(all_questions, 1):
        rows.append({
            "序号": i,
            "题目": q.get("question", ""),
            "标准答案": q.get("answer", ""),
            "题型": q.get("type", ""),
            "知识大类": q.get("category", ""),
            "知识小类": q.get("subcategory", ""),
            "能力层级": q.get("ability_level", "通用"),
            "能力主层级": q.get("ability_main", ""),
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
