# -*- coding: utf-8 -*-
"""
2.2 Balancing 核心逻辑：能力子层级与题型分布闭环补题。
基于 Markdown 文本与纯文本 LLM，参考 optimize_answers 2.2 均衡补题闭环迭代结构。
"""

import json
import os
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

import pandas as pd

from dataflow_edu.config.schema import (
    AbilityLevelItem,
    BalancingConfig,
    EduConfig,
    QuestionType,
    TaxonomyItem,
)
from dataflow_edu.generation.generation_core import (
    _build_subcat_to_category,
    _read_md_content,
    generate_questions_for_balance,
    get_md_pairs,
    get_balanced_dir,
    load_md_from_folder,
)
from dataflow_edu.serving import call_llm

PROGRESS_FILE = "balanced_progress.json"


def _build_sublevel_targets(ability_levels: List[AbilityLevelItem]) -> List[Tuple[str, str, float]]:
    """
    从 ability_levels 展开子层级及目标占比。
    Returns: [(sublevel_id, sublevel_name, target_ratio), ...]
    sublevel_id 格式: "major::sub" 或 "major"（无子层级时）
    """
    result = []
    total_weight = sum(a.weight for a in ability_levels)
    if total_weight <= 0:
        total_weight = 1.0
    for a in ability_levels:
        if a.sublevels:
            per_sub = (a.weight / total_weight) / len(a.sublevels)
            for sub in a.sublevels:
                result.append((f"{a.name}::{sub}", sub, per_sub))
        else:
            result.append((a.name, a.name, a.weight / total_weight))
    return result


def _build_question_type_targets(question_types: List[QuestionType]) -> Dict[str, float]:
    """题型名 -> 目标占比"""
    total = sum(q.weight for q in question_types)
    if total <= 0:
        total = 1.0
    return {q.name: q.weight / total for q in question_types}


def _build_taxonomy_targets(taxonomy: List[TaxonomyItem]) -> Dict[str, float]:
    """知识小类 -> 目标占比（等权）"""
    all_subs = []
    for t in taxonomy:
        if t.subcategories:
            all_subs.extend(t.subcategories)
        else:
            all_subs.append(t.name)
    if not all_subs:
        return {}
    return {s: 1.0 / len(all_subs) for s in all_subs}


def _analyze_knowledge_direction(
    questions: List[dict],
    taxonomy: List[TaxonomyItem],
) -> None:
    """
    知识方向分布分析，打印到终端并给出建议。
    """
    if not questions:
        return
    targets = _build_taxonomy_targets(taxonomy)
    if not targets:
        return
    total = len(questions)
    counts: Dict[str, int] = {}
    for q in questions:
        sc = str(q.get("subcategory", "")).strip() or "通用"
        counts[sc] = counts.get(sc, 0) + 1

    print("\n" + "=" * 60)
    print("📊 知识方向分布分析（仅供参考，建议通过增加语料均衡）")
    print("-" * 60)
    for sub, target_ratio in targets.items():
        cnt = counts.get(sub, 0)
        ratio = cnt / total if total > 0 else 0
        gap = target_ratio - ratio
        diff_str = f"+{gap:.1%}" if gap > 0 else f"{gap:.1%}"
        status = "✓" if abs(gap) <= 0.05 else "✗"
        print(f"  {status} {sub}: {cnt}道 ({ratio:.1%}) | 目标: {target_ratio:.0%} | 差距: {diff_str}")
    print("-" * 60)
    under = [s for s, tr in targets.items() if counts.get(s, 0) / total < tr - 0.05]
    if under:
        print("建议：以下知识方向题目偏少，可考虑增加对应教材/语料后再运行 2.1 Generation：")
        for s in under:
            print(f"  - {s}")
    print("=" * 60)


def _pair_info_to_md_pair(pair_info: dict) -> Optional[Tuple]:
    """将 stage1 pair 转为 (path1, path2, page1, page2) 元组。"""
    p1 = pair_info.get("md1_path")
    p2 = pair_info.get("md2_path")
    page_info = str(pair_info.get("page_info", ""))
    if not p1:
        return None
    if "-" in page_info:
        parts = page_info.split("-")
        try:
            page1, page2 = int(parts[0]), int(parts[1])
        except (ValueError, IndexError):
            return (p1, p2, 1, 2 if p2 else None)
    else:
        try:
            page1 = int(page_info) if page_info else 1
        except ValueError:
            page1 = 1
        page2 = 2 if p2 else None
    return (p1, p2, page1, page2)


def _check_suitability_md(
    content: str,
    sublevel_name: str,
    q_type_name: str,
    page_info: str,
) -> bool:
    """基于 Markdown 内容，LLM 判断是否适合生成指定子层级+题型的题目。"""
    sys_prompt = """你是学科教材分析专家。判断给定教材内容是否适合用于生成指定能力层级和题型的习题。
只回答「适合」或「不适合」，不要解释。"""
    user_prompt = f"""【教材内容（第{page_info}页）】
{content[:6000]}

【目标】生成「{sublevel_name}」能力层级、「{q_type_name}」题型的习题。

该内容是否适合？请只回答：适合 / 不适合"""

    result = call_llm(sys_prompt, user_prompt, max_tokens=64, temperature=0.1)
    if not result:
        return False
    r = result.strip()
    return "适合" in r and "不适合" not in r[:r.find("适合") + 2] if "适合" in r else False


class BalancingBalancer:
    """
    能力子层级与题型分布闭环补题器。
    基于 Markdown + 纯文本 LLM，参考 optimize_answers 2.2 配额均衡补题器。
    """

    def __init__(
        self,
        stage1_data: dict,
        questions: List[dict],
        config: EduConfig,
        balancing_config: BalancingConfig,
        balance_ability: bool = True,
        balance_type: bool = True,
        max_workers: int = 8,
    ):
        self.stage1_data = stage1_data
        self.questions = list(questions)
        self.config = config
        self.bal_cfg = balancing_config
        self.balance_ability = balance_ability
        self.balance_type = balance_type
        self.max_workers = max_workers

        self.pairs_data = stage1_data.get("pairs", [])
        self.total_pairs = len(self.pairs_data)
        self.sublevel_targets = _build_sublevel_targets(config.ability_levels)
        self.qtype_targets = _build_question_type_targets(config.question_types)
        self.excluded = set(balancing_config.excluded_ability_sublevels or [])

        # 已询问: (sublevel_id, q_type_name) -> set(pair_index)
        self.asked_pairs: Dict[Tuple[str, str], Set[int]] = {}
        for sid, sname, _ in self.sublevel_targets:
            if sid in self.excluded or sname in self.excluded:
                continue
            for qt in self.qtype_targets:
                self.asked_pairs[(sid, qt)] = set()

        self.iteration = 0
        self.bu_ti_count = 0
        self.sublevel_iterations: Dict[str, int] = {
            sid: 0 for sid, sname, _ in self.sublevel_targets
            if sid not in self.excluded and sname not in self.excluded
        }

    def calculate_distribution(self) -> dict:
        """统计当前题目在子层级、题型上的分布。"""
        total = len(self.questions)
        sublevel_counts: Dict[str, int] = {}
        qtype_counts: Dict[str, int] = {}

        for q in self.questions:
            al = str(q.get("ability_level", "")).strip() or "通用"
            # 匹配子层级：可能存储的是子层级名或 "大类::子层级"
            matched = False
            for sid, sname, _ in self.sublevel_targets:
                if sid in self.excluded:
                    continue
                if al == sname or al == sid or sid.endswith("::" + al):
                    sublevel_counts[sid] = sublevel_counts.get(sid, 0) + 1
                    matched = True
                    break
            if not matched:
                for sid, sname, _ in self.sublevel_targets:
                    if sname == al:
                        sublevel_counts[sid] = sublevel_counts.get(sid, 0) + 1
                        break

            qt = str(q.get("type", "")).strip() or "未知"
            qtype_counts[qt] = qtype_counts.get(qt, 0) + 1

        return {
            "total": total,
            "sublevels": sublevel_counts,
            "qtypes": qtype_counts,
        }

    def _count_sublevel_qtype(self, sublevel_id: str, sublevel_name: str, q_type_name: str) -> int:
        """统计满足 (sublevel, qtype) 的题目数。"""
        cnt = 0
        for q in self.questions:
            al = str(q.get("ability_level", "")).strip()
            qt = str(q.get("type", "")).strip()
            if qt != q_type_name:
                continue
            if al == sublevel_name or al == sublevel_id or sublevel_id.endswith("::" + al):
                cnt += 1
        return cnt

    def get_gaps(self) -> List[Tuple[str, str, int]]:
        """
        获取需要补题的 (sublevel_id, q_type_name, gap_count) 列表，按缺口降序。
        行/列约束：若子层级总量或题型总量已超过目标+容差，则该子层级/题型不再补题。
        """
        dist = self.calculate_distribution()
        total = dist["total"]
        tolerance = self.bal_cfg.tolerance

        if total <= 0:
            gaps = []
            for sid, sname, tr in self.sublevel_targets:
                if sid in self.excluded or sname in self.excluded:
                    continue
                for qt, qtr in self.qtype_targets.items():
                    target = max(1, int(10 * tr * qtr))
                    gaps.append((sid, qt, target))
            gaps.sort(key=lambda x: -x[2])
            return gaps

        # 计算已超标的子层级、题型（当前占比 > 目标占比 + 容差）
        over_sublevels: Set[str] = set()
        if self.balance_ability:
            for sid, _, tr in self.sublevel_targets:
                if sid in self.excluded:
                    continue
                cur_ratio = dist["sublevels"].get(sid, 0) / total
                if cur_ratio > tr + tolerance:
                    over_sublevels.add(sid)

        over_qtypes: Set[str] = set()
        if self.balance_type:
            for qt, qtr in self.qtype_targets.items():
                cur_ratio = dist["qtypes"].get(qt, 0) / total
                if cur_ratio > qtr + tolerance:
                    over_qtypes.add(qt)

        first_sid = next(
            (s for s, sn, _ in self.sublevel_targets if s not in self.excluded and sn not in self.excluded),
            None,
        )
        first_qt = next(iter(self.qtype_targets.keys()), None) if self.qtype_targets else None

        gaps = []
        if self.balance_ability and self.balance_type:
            for sid, sname, tr in self.sublevel_targets:
                if sid in self.excluded or sname in self.excluded or sid in over_sublevels:
                    continue
                for qt, qtr in self.qtype_targets.items():
                    if qt in over_qtypes:
                        continue
                    target_count = max(1, int(total * tr * qtr))
                    current = self._count_sublevel_qtype(sid, sname, qt)
                    gap = target_count - current
                    if gap > 0:
                        gaps.append((sid, qt, gap))
        elif self.balance_ability and not self.balance_type:
            for sid, sname, tr in self.sublevel_targets:
                if sid in self.excluded or sname in self.excluded or sid in over_sublevels:
                    continue
                target_count = max(1, int(total * tr))
                current = dist["sublevels"].get(sid, 0)
                gap = target_count - current
                if gap > 0 and first_qt:
                    gaps.append((sid, first_qt, gap))
        elif not self.balance_ability and self.balance_type:
            for qt, qtr in self.qtype_targets.items():
                if qt in over_qtypes:
                    continue
                target_count = max(1, int(total * qtr))
                current = dist["qtypes"].get(qt, 0)
                gap = target_count - current
                if gap > 0 and first_sid:
                    sname = first_sid.split("::")[-1] if "::" in first_sid else first_sid
                    gaps.append((first_sid, qt, gap))
        gaps.sort(key=lambda x: -x[2])
        return gaps

    def get_available_pairs(self, sublevel_id: str, q_type_name: str) -> List[int]:
        asked = self.asked_pairs.get((sublevel_id, q_type_name), set())
        return [i for i in range(self.total_pairs) if i not in asked]

    def _check_suitability_impl(
        self, pair_index: int, sublevel_name: str, q_type_name: str
    ) -> bool:
        """仅执行 LLM 适宜性判断，不修改 asked_pairs。"""
        pair_info = self.pairs_data[pair_index]
        md_pair = _pair_info_to_md_pair(pair_info)
        if not md_pair:
            return False
        content = _read_md_content(md_pair)
        if not content.strip():
            return False
        page_info = str(pair_info.get("page_info", ""))
        return _check_suitability_md(content, sublevel_name, q_type_name, page_info)

    def check_suitability(self, pair_index: int, sublevel_id: str, sublevel_name: str, q_type_name: str) -> bool:
        self.asked_pairs.setdefault((sublevel_id, q_type_name), set()).add(pair_index)
        return self._check_suitability_impl(pair_index, sublevel_name, q_type_name)

    def sample_and_check(
        self,
        sublevel_id: str,
        sublevel_name: str,
        q_type_name: str,
        sample_size: int,
    ) -> List[int]:
        available = self.get_available_pairs(sublevel_id, q_type_name)
        if not available:
            return []
        sample_count = min(sample_size, len(available))
        sampled = random.sample(available, sample_count)

        def task(idx: int) -> tuple:
            ok = self._check_suitability_impl(idx, sublevel_name, q_type_name)
            return idx, ok

        suitable = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as ex:
            futures = {ex.submit(task, idx): idx for idx in sampled}
            for fut in as_completed(futures):
                try:
                    idx, ok = fut.result()
                    if ok:
                        suitable.append(idx)
                except Exception:
                    pass

        for idx in sampled:
            self.asked_pairs.setdefault((sublevel_id, q_type_name), set()).add(idx)
        return suitable

    def generate_bu_ti(
        self,
        pair_index: int,
        sublevel_id: str,
        sublevel_name: str,
        q_type: QuestionType,
        count: int,
    ) -> List[dict]:
        pair_info = self.pairs_data[pair_index]
        md_pair = _pair_info_to_md_pair(pair_info)
        if not md_pair:
            return []
        subcats = pair_info.get("subcategories", []) or ["通用"]
        subcat_to_cat = _build_subcat_to_category(self.config.taxonomy or [])
        return generate_questions_for_balance(
            md_pair=md_pair,
            subcategories=subcats,
            q_type=q_type,
            target_ability_sublevel=sublevel_name,
            count=count,
            subcat_to_cat=subcat_to_cat,
            ability_levels=self.config.ability_levels or [],
            subject=self.config.subject or "",
        )

    def should_stop(self) -> Tuple[bool, str]:
        if self.iteration >= self.bal_cfg.max_iterations:
            return True, "达到最大迭代次数"
        gaps = self.get_gaps()
        if not gaps:
            return True, "没有需要补题的子层级/题型"
        all_exhausted = True
        for sid, qt, _ in gaps:
            if self.get_available_pairs(sid, qt):
                all_exhausted = False
                break
        if all_exhausted:
            return True, "所有缺口组合的页面池已耗尽"

        dist = self.calculate_distribution()
        total = dist["total"]
        if total == 0:
            return False, ""
        tolerance = self.bal_cfg.tolerance
        all_ok = True
        for sid, _, tr in self.sublevel_targets:
            if sid in self.excluded:
                continue
            if not self.balance_ability:
                break
            cur = dist["sublevels"].get(sid, 0) / total if total > 0 else 0
            if abs(cur - tr) > tolerance:
                all_ok = False
                break
        if all_ok and self.balance_type:
            for qt, qtr in self.qtype_targets.items():
                cur = dist["qtypes"].get(qt, 0) / total if total > 0 else 0
                if abs(cur - qtr) > tolerance:
                    all_ok = False
                    break
        if all_ok:
            return True, "达到目标配额（容差范围内）"
        return False, ""

    def print_distribution(self):
        dist = self.calculate_distribution()
        total = dist["total"]
        print(f"\n📊 当前分布（总题目数: {total}）")
        print("-" * 60)
        if self.balance_ability:
            for sid, sname, tr in self.sublevel_targets:
                if sid in self.excluded or sname in self.excluded:
                    continue
                cnt = dist["sublevels"].get(sid, 0)
                ratio = cnt / total if total > 0 else 0
                diff = ratio - tr
                diff_str = f"+{diff:.1%}" if diff > 0 else f"{diff:.1%}"
                ok = "✓" if abs(diff) <= self.bal_cfg.tolerance else "✗"
                print(f"  {ok} {sname}: {cnt}道 ({ratio:.1%}) | 目标: {tr:.0%} | 差距: {diff_str}")
        if self.balance_type:
            print("-" * 40)
            for qt, qtr in self.qtype_targets.items():
                cnt = dist["qtypes"].get(qt, 0)
                ratio = cnt / total if total > 0 else 0
                diff = ratio - qtr
                diff_str = f"+{diff:.1%}" if diff > 0 else f"{diff:.1%}"
                ok = "✓" if abs(diff) <= self.bal_cfg.tolerance else "✗"
                print(f"  {ok} {qt}: {cnt}道 ({ratio:.1%}) | 目标: {qtr:.0%} | 差距: {diff_str}")
        print("-" * 60)

    def run(self) -> List[dict]:
        sample_size = self.bal_cfg.sample_size
        max_per = self.bal_cfg.max_per_sublevel_iterations
        q_type_map = {q.name: q for q in self.config.question_types}

        print(f"\n{'=' * 70}")
        print("2.2 Balancing：能力子层级与题型闭环补题")
        print(f"{'=' * 70}")
        print(f"初始题目数: {len(self.questions)}")
        print(f"最大迭代: {self.bal_cfg.max_iterations} | 每轮补题: {self.bal_cfg.questions_per_round} | 采样数: {sample_size}")
        print(f"容差: {self.bal_cfg.tolerance:.0%}")
        print(f"排除子层级: {list(self.excluded) or '无'}")
        self.print_distribution()

        while True:
            self.iteration += 1
            print(f"\n{'=' * 60}")
            print(f"🔄 第 {self.iteration} 轮迭代")
            print(f"{'=' * 60}")

            stop, reason = self.should_stop()
            if stop:
                print(f"✅ 停止: {reason}")
                break

            gaps = self.get_gaps()
            if not gaps:
                break

            sid, qt, gap = None, None, None
            for s, q, g in gaps:
                if self.sublevel_iterations.get(s, 0) >= max_per:
                    sn = s.split("::")[-1] if "::" in s else s
                    print(f"⏭️ {sn} 已达单子层级最大轮数，改用下一个缺口")
                    continue
                sid, qt, gap = s, q, g
                break
            if sid is None:
                for s in self.sublevel_iterations:
                    self.sublevel_iterations[s] = 0
                print("⏭️ 所有缺口子层级已达单子层级最大轮数，重置后下轮继续")
                continue

            sublevel_name = sid.split("::")[-1] if "::" in sid else sid
            q_type = q_type_map.get(qt)
            if not q_type:
                continue

            cap = min(gap, self.bal_cfg.questions_per_round)
            print(f"🎯 目标: 【{sublevel_name}】+【{qt}】 缺口 {gap} 道 | 本轮补 {cap} 道")

            suitable = self.sample_and_check(sid, sublevel_name, qt, sample_size)
            if not suitable:
                print("  ⚠️ 无适合页面")
                continue

            per_pair = min(2, max(1, cap // len(suitable) + 1))
            tasks_built = min(len(suitable), (cap + per_pair - 1) // per_pair)
            print(f"  ✓ 适宜性筛选: 采样 {sample_size} 对 → 适合 {len(suitable)} 对 | 每对最多生成 {per_pair} 道 | 启用 {tasks_built} 对生成")

            self.sublevel_iterations[sid] = self.sublevel_iterations.get(sid, 0) + 1
            tasks = []
            remaining = cap
            for idx in suitable:
                if remaining <= 0:
                    break
                n = min(per_pair, remaining)
                tasks.append((idx, n))
                remaining -= n

            def task(t: tuple):
                i, cnt = t
                return self.generate_bu_ti(i, sid, sublevel_name, q_type, cnt)

            added = 0
            with ThreadPoolExecutor(max_workers=self.max_workers) as ex:
                futures = {ex.submit(task, t): t for t in tasks}
                for fut in as_completed(futures):
                    try:
                        qs = fut.result()
                        if qs:
                            self.questions.extend(qs)
                            added += len(qs)
                            self.bu_ti_count += len(qs)
                    except Exception:
                        pass

            print(f"  本轮补题: {added} 道")
            self.print_distribution()

        return self.questions

    def get_progress(self) -> dict:
        return {
            "iteration": self.iteration,
            "bu_ti_count": self.bu_ti_count,
            "sublevel_iterations": dict(self.sublevel_iterations),
            "asked_pairs": {f"{k[0]}|{k[1]}": list(v) for k, v in self.asked_pairs.items()},
        }

    def restore_progress(self, progress: dict):
        self.iteration = progress.get("iteration", 0)
        self.bu_ti_count = progress.get("bu_ti_count", 0)
        self.sublevel_iterations = progress.get("sublevel_iterations", {})
        ap = progress.get("asked_pairs", {})
        for k, v in ap.items():
            parts = k.split("|", 1)
            if len(parts) == 2:
                self.asked_pairs[(parts[0], parts[1])] = set(v)


def _save_progress(progress_path: str, balancer: BalancingBalancer, questions: List[dict]):
    data = {
        "last_update": datetime.now().isoformat(),
        "balancer_progress": balancer.get_progress(),
        "questions": questions,
    }
    with open(progress_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _load_progress(progress_path: str) -> Optional[dict]:
    if not os.path.isfile(progress_path):
        return None
    try:
        with open(progress_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def run_balancing(
    md_folder: str,
    output_dir: str,
    config: EduConfig,
    stage1_file: str,
    stage2_json_file: str,
    balancing_config: Optional[BalancingConfig] = None,
    balance_ability: bool = True,
    balance_type: bool = True,
    excluded_override: Optional[List[str]] = None,
    max_workers: int = 8,
    resume: bool = False,
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    运行 2.2 Balancing 流程。
    Returns: (success, excel_path, json_path)
    """
    bal_cfg = balancing_config or config.operators.get("balancing")
    if isinstance(bal_cfg, dict):
        bal_cfg = BalancingConfig(
            output_dir=bal_cfg.get("output_dir", "dataflow_edu/data/generation_and_balancing"),
            sample_size=int(bal_cfg.get("sample_size", 32)),
            max_iterations=int(bal_cfg.get("max_iterations", 5)),
            questions_per_round=int(bal_cfg.get("questions_per_round", 10)),
            max_per_sublevel_iterations=int(bal_cfg.get("max_per_sublevel_iterations", 2)),
            tolerance=float(bal_cfg.get("tolerance", 0.03)),
            excluded_ability_sublevels=excluded_override or list(bal_cfg.get("excluded_ability_sublevels", [])),
        )
    else:
        bal_cfg = bal_cfg or BalancingConfig()
        if excluded_override is not None:
            bal_cfg = BalancingConfig(
                output_dir=bal_cfg.output_dir,
                sample_size=bal_cfg.sample_size,
                max_iterations=bal_cfg.max_iterations,
                questions_per_round=bal_cfg.questions_per_round,
                max_per_sublevel_iterations=bal_cfg.max_per_sublevel_iterations,
                tolerance=bal_cfg.tolerance,
                excluded_ability_sublevels=excluded_override,
            )

    with open(stage1_file, "r", encoding="utf-8") as f:
        stage1_data = json.load(f)

    with open(stage2_json_file, "r", encoding="utf-8") as f:
        stage2_data = json.load(f)
    questions = stage2_data.get("questions", [])

    folder_name = os.path.basename(os.path.normpath(md_folder))
    balanced_dir = get_balanced_dir(output_dir)
    excel_path = os.path.join(balanced_dir, f"{folder_name}_balanced_questions.xlsx")
    json_path = os.path.join(balanced_dir, f"{folder_name}_balanced_questions.json")
    progress_path = os.path.join(balanced_dir, f"{folder_name}_{PROGRESS_FILE}")

    _analyze_knowledge_direction(questions, config.taxonomy)

    balancer = BalancingBalancer(
        stage1_data=stage1_data,
        questions=questions,
        config=config,
        balancing_config=bal_cfg,
        balance_ability=balance_ability,
        balance_type=balance_type,
        max_workers=max_workers,
    )
    if excluded_override is not None:
        balancer.excluded = set(excluded_override)

    if resume:
        prog = _load_progress(progress_path)
        if prog:
            print("✓ 从进度恢复 Balancing...")
            balancer.restore_progress(prog.get("balancer_progress", {}))
            saved = prog.get("questions", [])
            if saved:
                balancer.questions = saved

    try:
        final_questions = balancer.run()

        rows = []
        for i, q in enumerate(final_questions, 1):
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
        meta = {"source": md_folder, "stage1": stage1_file, "stage2": stage2_json_file, "total": len(final_questions)}
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump({"questions": final_questions, "metadata": meta}, f, ensure_ascii=False, indent=2)

        if os.path.isfile(progress_path):
            os.remove(progress_path)

        print(f"\n📄 结果已保存: {excel_path}")
        return True, excel_path, json_path
    except Exception as e:
        print(f"❌ Balancing 失败: {e}")
        try:
            _save_progress(progress_path, balancer, balancer.questions)
            print("⚠ 进度已保存，可使用 resume 继续")
        except Exception:
            pass
        return False, None, None
