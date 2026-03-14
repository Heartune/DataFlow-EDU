# -*- coding: utf-8 -*-
"""
3.3 Domain Cleaning Operator - 领域相关性检查与低质量样本剔除

基于 LLM 5 点制领域相关性评估，剔除 1 分样本，保留 2–5 分题目。
"""

import json
import os

from dataflow import get_logger
from dataflow.core import OperatorABC
from dataflow.utils.registry import OPERATOR_REGISTRY

from dataflow_edu.domain_cleaning.core import (
    _print_domain_relevance_distribution,
    _scan_cleaning_candidates,
    run_domain_cleaning,
)
from dataflow_edu.config.schema import DomainCleaningConfig, EduConfig
from dataflow_edu.serving import get_max_workers, interactive_config_llm


def _check_cleaned_status(folder_name: str, output_dir: str) -> bool:
    """检查该教材是否已完成领域相关性清洗。"""
    path = os.path.join(output_dir, f"{folder_name}_domain_cleaned.json")
    return os.path.isfile(path)


def _display_cleaning_table(candidates: list, input_dir: str, output_dir: str):
    print(f"\n{'=' * 60}")
    print("3.3 Domain Cleaning Operator - 可选教材")
    print(f"{'=' * 60}")
    print(f" {'序号':>4} | {'Cleaned':^8} | 教材名称")
    print("-" * 60)
    for i, name in enumerate(candidates, 1):
        done = _check_cleaned_status(name, output_dir)
        m = "Y" if done else "-"
        print(f" {i:>4} |   {m}     | {name}")
    print("=" * 60)


@OPERATOR_REGISTRY.register()
class DomainCleaningOperator(OperatorABC):
    """
    3.3 Domain Cleaning Operator：检查领域相关性并剔除低质量样本。
    基于 LLM 5 点制评分，剔除 1 分样本；支持 resume、用户确认、单独保存剔除样本。
    """

    def __init__(
        self,
        input_dir: str = "dataflow_edu/data/cleaning_and_refinement/3_2_ambiguity_refined",
        output_dir: str = "dataflow_edu/data/cleaning_and_refinement/3_3_domain_cleaned",
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
                "3.3 Domain Cleaning Operator：基于 LLM 5 点制领域相关性评估，"
                "剔除低质量样本（1 分）。支持 resume、用户确认、单独保存剔除样本。"
            )
        return "3.3 Domain Cleaning Operator: remove low-quality samples by domain relevance score."

    def run(
        self,
        storage=None,
        input_dir: str | None = None,
        output_dir: str | None = None,
        config: EduConfig | None = None,
        no_confirm: bool = False,
    ):
        """
        执行领域相关性清洗：扫描 3_2_ambiguity_refined -> 交互选择 -> API 配置 -> 评估与剔除 -> 保存。
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

        dom_cfg = config.operators.get("domain_cleaning")
        if isinstance(dom_cfg, dict):
            dom_cfg = DomainCleaningConfig(
                input_dir=str(dom_cfg.get("input_dir", self.input_dir)),
                output_dir=str(dom_cfg.get("output_dir", self.output_dir)),
                max_workers=int(dom_cfg.get("max_workers", self.max_workers)),
                max_retries=int(dom_cfg.get("max_retries", 3)),
                threshold_remove=int(
                    dom_cfg.get("threshold_remove", DomainCleaningConfig().threshold_remove)
                ),
                domain_name=str(dom_cfg.get("domain_name", "生物学")),
            )
        elif not isinstance(dom_cfg, DomainCleaningConfig):
            dom_cfg = DomainCleaningConfig(
                input_dir=input_dir,
                output_dir=output_dir,
                max_workers=self.max_workers,
            )

        input_dir_resolved = dom_cfg.input_dir
        if not os.path.isabs(input_dir_resolved):
            input_dir_resolved = os.path.join(root, input_dir_resolved)
        output_dir_resolved = dom_cfg.output_dir
        if not os.path.isabs(output_dir_resolved):
            output_dir_resolved = os.path.join(root, output_dir_resolved)

        candidates = _scan_cleaning_candidates(input_dir_resolved)
        if not candidates:
            self.logger.warning("没有找到可清洗的教材（需先完成 3.2 Ambiguity Refinement）")
            print("未找到教材，请先运行 3.2 Ambiguity Refinement 完成 3_2_ambiguity_refined。")
            return False, None, None

        _display_cleaning_table(candidates, input_dir_resolved, output_dir_resolved)

        print()
        choice = input("请输入序号选择教材（输入 q 退出）: ").strip()
        if choice.lower() == "q":
            return False, None, None
        try:
            idx = int(choice)
            if idx < 1 or idx > len(candidates):
                print("无效序号。")
                return False, None, None
        except ValueError:
            print("无效输入。")
            return False, None, None

        selected = candidates[idx - 1]
        input_path = os.path.join(input_dir_resolved, f"{selected}_ambiguity_refined.json")
        if not os.path.isfile(input_path):
            print(f"输入文件不存在: {input_path}")
            return False, None, None

        if not interactive_config_llm(gen_config_max_workers=dom_cfg.max_workers):
            return False, None, None

        resume_input = input("是否从上次进度继续？(y/N): ").strip().lower()
        resume = resume_input in ("y", "yes")

        max_workers = get_max_workers()
        print(f"\n教材: {selected}")
        print(f"领域: {dom_cfg.domain_name}")
        print(f"输入: {input_path}")
        print(f"输出: {output_dir_resolved}")
        print("=" * 60)

        ok, cleaned_path, removed_path = run_domain_cleaning(
            input_path=input_path,
            output_dir=output_dir_resolved,
            folder_name=selected,
            domain_name=dom_cfg.domain_name,
            max_workers=max_workers,
            max_retries=dom_cfg.max_retries,
            threshold_remove=dom_cfg.threshold_remove,
            resume=resume,
            no_confirm=no_confirm,
        )
        if ok and cleaned_path and os.path.isfile(cleaned_path):
            try:
                with open(cleaned_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                _print_domain_relevance_distribution(data.get("questions", []))
            except Exception:
                pass
            print(f"\n3.3 Domain Cleaning 完成: {cleaned_path}")
        return ok, cleaned_path, removed_path
