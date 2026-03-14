# -*- coding: utf-8 -*-
"""
3.4 Domain Refinement Operator - 对中质量（2–3 分）题目优化领域相关性

从 3.3 清洗结果中筛选 2–3 分题，通过 LLM 优化题干与答案，并与 4-5 分题合并输出。
"""

import os

from dataflow import get_logger
from dataflow.core import OperatorABC
from dataflow.utils.registry import OPERATOR_REGISTRY

import json

from dataflow_edu.domain_refinement.core import (
    _print_domain_relevance_distribution,
    _scan_refinement_candidates,
    run_domain_refinement,
)
from dataflow_edu.config.schema import DomainRefinementConfig, EduConfig
from dataflow_edu.serving import get_max_workers, interactive_config_llm


def _check_refined_status(folder_name: str, output_dir: str) -> bool:
    """检查该教材是否已完成领域相关性精修。"""
    path = os.path.join(output_dir, f"{folder_name}_domain_refined.json")
    return os.path.isfile(path)


def _display_refinement_table(candidates: list, input_dir: str, output_dir: str):
    print(f"\n{'=' * 60}")
    print("3.4 Domain Refinement Operator - 可选教材")
    print(f"{'=' * 60}")
    print(f" {'序号':>4} | {'Refined':^8} | 教材名称")
    print("-" * 60)
    for i, name in enumerate(candidates, 1):
        done = _check_refined_status(name, output_dir)
        m = "Y" if done else "-"
        print(f" {i:>4} |   {m}     | {name}")
    print("=" * 60)


@OPERATOR_REGISTRY.register()
class DomainRefinementOperator(OperatorABC):
    """
    3.4 Domain Refinement Operator：对中质量（2–3 分）样本优化领域相关性。
    从 3.3 清洗结果筛选 2–3 分题，LLM 优化题干与答案，与 4-5 分题合并输出。
    """

    def __init__(
        self,
        input_dir: str = "dataflow_edu/data/cleaning_and_refinement/3_3_domain_cleaned",
        output_dir: str = "dataflow_edu/data/cleaning_and_refinement/3_4_domain_refined",
        max_workers: int = 8,
    ):
        super().__init__()
        self.logger = get_logger()
        self.input_dir = input_dir
        self.output_dir = output_dir
        self.max_workers = max_workers

    @staticmethod
    def get_desc(lang: str = "zh"):
        if lang == "zh":
            return (
                "3.4 Domain Refinement Operator：对中质量（2–3 分）样本优化领域相关性。"
                "从 3.3 清洗结果筛选 2–3 分题，LLM 优化题干与答案，与 4-5 分题合并输出。"
            )
        return "3.4 Domain Refinement Operator: refine medium-quality (domain score 2-3) samples."

    def run(
        self,
        storage=None,
        input_dir: str | None = None,
        output_dir: str | None = None,
        config: EduConfig | None = None,
    ):
        """
        执行领域相关性精修：扫描 3_3_domain_cleaned -> 交互选择 -> API 配置 -> 优化 -> 保存。
        """
        input_dir = input_dir or self.input_dir
        output_dir = output_dir or self.output_dir
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        if not os.path.isabs(input_dir):
            input_dir = os.path.join(root, input_dir)
        if not os.path.isabs(output_dir):
            output_dir = os.path.join(root, output_dir)

        if config is None:
            from dataflow_edu.config.loader import load_config

            config = load_config(project_root=root)

        ref_cfg = config.operators.get("domain_refinement")
        if isinstance(ref_cfg, dict):
            ref_defaults = DomainRefinementConfig()
            raw_ts = ref_cfg.get("target_scores", ref_defaults.target_scores)
            ts = [int(x) for x in raw_ts] if isinstance(raw_ts, (list, tuple)) else ref_defaults.target_scores
            ref_cfg = DomainRefinementConfig(
                input_dir=str(ref_cfg.get("input_dir", self.input_dir)),
                output_dir=str(ref_cfg.get("output_dir", self.output_dir)),
                max_workers=int(ref_cfg.get("max_workers", self.max_workers)),
                max_retries=int(ref_cfg.get("max_retries", 3)),
                target_scores=ts,
                threshold_discard=int(ref_cfg.get("threshold_discard", 1)),
                domain_name=str(ref_cfg.get("domain_name", "生物学")),
            )
        elif not isinstance(ref_cfg, DomainRefinementConfig):
            ref_cfg = DomainRefinementConfig(
                input_dir=input_dir,
                output_dir=output_dir,
                max_workers=self.max_workers,
            )

        input_dir_resolved = ref_cfg.input_dir
        if not os.path.isabs(input_dir_resolved):
            input_dir_resolved = os.path.join(root, input_dir_resolved)
        output_dir_resolved = ref_cfg.output_dir
        if not os.path.isabs(output_dir_resolved):
            output_dir_resolved = os.path.join(root, output_dir_resolved)

        candidates = _scan_refinement_candidates(input_dir_resolved)
        if not candidates:
            self.logger.warning("没有找到可精修的教材（需先完成 3.3 Domain Cleaning）")
            print("未找到教材，请先运行 3.3 Domain Cleaning 完成 3_3_domain_cleaned。")
            return False, None

        _display_refinement_table(candidates, input_dir_resolved, output_dir_resolved)

        print()
        choice = input("请输入序号选择教材（输入 q 退出）: ").strip()
        if choice.lower() == "q":
            return False, None
        try:
            idx = int(choice)
            if idx < 1 or idx > len(candidates):
                print("无效序号。")
                return False, None
        except ValueError:
            print("无效输入。")
            return False, None

        selected = candidates[idx - 1]
        input_path = os.path.join(input_dir_resolved, f"{selected}_domain_cleaned.json")
        if not os.path.isfile(input_path):
            print(f"输入文件不存在: {input_path}")
            return False, None

        if not interactive_config_llm(gen_config_max_workers=ref_cfg.max_workers):
            return False, None

        resume_input = input("是否从上次进度继续？(y/N): ").strip().lower()
        resume = resume_input in ("y", "yes")

        max_workers = get_max_workers()
        taxonomy_items = list(config.taxonomy) if config and config.taxonomy else []
        print(f"\n教材: {selected}")
        print(f"领域: {ref_cfg.domain_name}")
        print(f"输入: {input_path}")
        print(f"输出: {output_dir_resolved}")
        print("=" * 60)

        ok, refined_path = run_domain_refinement(
            input_path=input_path,
            output_dir=output_dir_resolved,
            folder_name=selected,
            domain_name=ref_cfg.domain_name,
            taxonomy_items=taxonomy_items,
            max_workers=max_workers,
            max_retries=ref_cfg.max_retries,
            target_scores=ref_cfg.target_scores,
            threshold_discard=ref_cfg.threshold_discard,
            resume=resume,
        )
        if ok and refined_path and os.path.isfile(refined_path):
            try:
                with open(refined_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                _print_domain_relevance_distribution(data.get("questions", []))
            except Exception:
                pass
            print(f"\n3.4 Domain Refinement 完成: {refined_path}")
        return ok, refined_path
