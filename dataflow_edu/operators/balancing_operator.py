# -*- coding: utf-8 -*-
"""
Balancing Operator - 2.2 能力层级与题型分布均衡补题

基于 configuration，对能力子层级、题型分布不均衡时进行补题。
知识方向仅分析并打印建议，不强制补题。
"""

import os

from dataflow import get_logger
from dataflow.core import OperatorABC
from dataflow.utils.registry import OPERATOR_REGISTRY

from dataflow_edu.balancing.balancing_core import run_balancing
from dataflow_edu.config.schema import BalancingConfig, EduConfig
from dataflow_edu.generation.generation_core import get_stage1_dir, get_stage2_dir, get_balanced_dir
from dataflow_edu.serving import get_max_workers, interactive_config_llm


def _scan_balancing_candidates(output_dir: str) -> list:
    """扫描 2_1_generated_stage_2 下有 generated 结果的教材（有 stage1 + stage2 的）。"""
    stage2_dir = get_stage2_dir(output_dir)
    stage1_dir = get_stage1_dir(output_dir)
    if not os.path.isdir(stage2_dir):
        return []
    candidates = []
    for fname in sorted(os.listdir(stage2_dir)):
        if fname.endswith("_generated_questions.json"):
            folder_name = fname.replace("_generated_questions.json", "")
            stage1_file = os.path.join(stage1_dir, f"{folder_name}_stage1_taxonomy.json")
            if os.path.isfile(stage1_file):
                candidates.append(folder_name)
    return candidates


def _check_balanced_status(folder_name: str, output_dir: str) -> bool:
    balanced_dir = get_balanced_dir(output_dir)
    path = os.path.join(balanced_dir, f"{folder_name}_balanced_questions.xlsx")
    return os.path.isfile(path)


def _display_balancing_table(candidates: list, output_dir: str):
    print(f"\n{'=' * 60}")
    print("2.2 Balancing Operator - 可选教材")
    print(f"{'=' * 60}")
    print(f" {'序号':>4} | {'Balanced':^8} | 教材名称")
    print("-" * 60)
    for i, name in enumerate(candidates, 1):
        is_balanced = _check_balanced_status(name, output_dir)
        m = "Y" if is_balanced else "-"
        print(f" {i:>4} |   {m}     | {name}")
    print("=" * 60)


@OPERATOR_REGISTRY.register()
class BalancingOperator(OperatorABC):
    """
    2.2 Balancing Operator：能力子层级与题型分布均衡补题。
    基于 Markdown + 纯文本 LLM，闭环迭代直到分布达标或达到最大迭代次数。
    """

    def __init__(
        self,
        output_dir: str = "dataflow_edu/data/generation_and_balancing",
        md_dir: str = "dataflow_edu/data/resources/md",
        max_workers: int = 8,
    ):
        super().__init__()
        self.logger = get_logger()
        self.output_dir = output_dir
        self.md_dir = md_dir
        self.max_workers = max_workers

    @staticmethod
    def get_desc(lang: str = "zh"):
        if lang == "zh":
            return (
                "2.2 Balancing Operator：基于 configuration，对能力子层级、题型分布不均衡时补题。"
                "知识方向仅分析并打印建议。支持交互选教材、均衡维度、排除子层级、resume。"
            )
        return "2.2 Balancing Operator for ability and question-type distribution."

    def run(
        self,
        storage=None,
        output_dir: str | None = None,
        md_dir: str | None = None,
        config: EduConfig | None = None,
    ):
        """
        执行 Balancing 流程：扫描教材 -> 交互选择 -> API 配置 -> 均衡维度 -> 执行。
        """
        output_dir = output_dir or self.output_dir
        md_dir = md_dir or self.md_dir
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        if not os.path.isabs(output_dir):
            output_dir = os.path.join(root, output_dir)
        if not os.path.isabs(md_dir):
            md_dir = os.path.join(root, md_dir)

        if config is None:
            from dataflow_edu.config.loader import load_config

            config = load_config(project_root=root)

        bal_cfg = config.operators.get("balancing")
        if isinstance(bal_cfg, dict):
            bal_cfg = BalancingConfig(
                output_dir=bal_cfg.get("output_dir", "dataflow_edu/data/generation_and_balancing"),
                sample_size=int(bal_cfg.get("sample_size", 32)),
                max_iterations=int(bal_cfg.get("max_iterations", 30)),
                questions_per_round=int(bal_cfg.get("questions_per_round", 10)),
                max_per_sublevel_iterations=int(bal_cfg.get("max_per_sublevel_iterations", 2)),
                tolerance=float(bal_cfg.get("tolerance", 0.03)),
                excluded_ability_sublevels=list(bal_cfg.get("excluded_ability_sublevels", [])),
            )
        elif not isinstance(bal_cfg, BalancingConfig):
            bal_cfg = BalancingConfig()

        candidates = _scan_balancing_candidates(output_dir)
        if not candidates:
            self.logger.warning("没有找到可均衡的教材（需先完成 2.1 Generation 阶段1+2）")
            print("未找到教材，请先运行 2.1 Generation 完成阶段1和阶段2。")
            return False, None, None

        _display_balancing_table(candidates, output_dir)

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
        md_folder = os.path.join(md_dir, selected)
        if not os.path.isdir(md_folder):
            print(f"Markdown 目录不存在: {md_folder}")
            return False, None, None

        if not interactive_config_llm(gen_config_max_workers=self.max_workers):
            return False, None, None

        print("\n均衡维度选择:")
        print("  1) 只均衡能力子层级")
        print("  2) 只均衡题型")
        print("  3) 两者都均衡 (推荐)")
        dim_input = input("请选择 (1/2/3) (直接回车使用：3): ").strip() or "3"
        if dim_input == "1":
            balance_ability, balance_type = True, False
        elif dim_input == "2":
            balance_ability, balance_type = False, True
        else:
            balance_ability, balance_type = True, True

        excluded_override = None
        if bal_cfg.excluded_ability_sublevels:
            print(f"\n当前配置排除的子层级: {bal_cfg.excluded_ability_sublevels}")
        excl_input = input("是否临时增加排除子层级？(逗号分隔，直接回车跳过): ").strip()
        if excl_input:
            excluded_override = [s.strip() for s in excl_input.split(",") if s.strip()]
            if excluded_override:
                base = list(bal_cfg.excluded_ability_sublevels or [])
                base.extend(excluded_override)
                excluded_override = base

        resume_input = input("是否从上次进度继续？(y/N): ").strip().lower()
        resume = resume_input in ("y", "yes")

        max_workers = get_max_workers()
        stage1_file = os.path.join(get_stage1_dir(output_dir), f"{selected}_stage1_taxonomy.json")
        stage2_json = os.path.join(get_stage2_dir(output_dir), f"{selected}_generated_questions.json")

        if not os.path.isfile(stage1_file):
            print(f"阶段1 结果不存在: {stage1_file}")
            return False, None, None
        if not os.path.isfile(stage2_json):
            print(f"阶段2 结果不存在: {stage2_json}")
            return False, None, None

        print(f"\n教材: {selected}")
        print(f"均衡: 能力={'Y' if balance_ability else 'N'} 题型={'Y' if balance_type else 'N'}")
        print("=" * 60)

        ok, excel_path, json_path = run_balancing(
            md_folder=md_folder,
            output_dir=output_dir,
            config=config,
            stage1_file=stage1_file,
            stage2_json_file=stage2_json,
            balancing_config=bal_cfg,
            balance_ability=balance_ability,
            balance_type=balance_type,
            excluded_override=excluded_override,
            max_workers=max_workers,
            resume=resume,
        )
        if ok:
            print(f"\n2.2 Balancing 完成: {excel_path}")
        return ok, excel_path, json_path
