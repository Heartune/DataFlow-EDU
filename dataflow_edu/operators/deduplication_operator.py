# -*- coding: utf-8 -*-
"""
3.5 Deduplication Operator - 基于 MinHash + LSH 对题目题干去重
"""

import json
import os

from dataflow import get_logger
from dataflow.core import OperatorABC
from dataflow.utils.registry import OPERATOR_REGISTRY

from dataflow_edu.deduplication.core import (
    _scan_deduplication_candidates,
    run_deduplication,
)
from dataflow_edu.config.schema import DeduplicationConfig, EduConfig


def _check_deduplicated_status(folder_name: str, output_dir: str) -> bool:
    """检查该教材是否已完成去重。"""
    path = os.path.join(output_dir, f"{folder_name}_deduplicated.json")
    return os.path.isfile(path)


def _display_deduplication_table(candidates: list, input_dir: str, output_dir: str):
    print(f"\n{'=' * 60}")
    print("3.5 Deduplication Operator - 可选教材")
    print(f"{'=' * 60}")
    print(f" {'序号':>4} | {'Deduped':^8} | 教材名称")
    print("-" * 60)
    for i, name in enumerate(candidates, 1):
        done = _check_deduplicated_status(name, output_dir)
        m = "Y" if done else "-"
        print(f" {i:>4} |   {m}     | {name}")
    print("=" * 60)


@OPERATOR_REGISTRY.register()
class DeduplicationOperator(OperatorABC):
    """
    3.5 Deduplication Operator：基于 MinHash + LSH 对题目题干去重。
    仅比较 question 字段，保留首次出现，剔除重复题单独保存。
    """

    def __init__(
        self,
        input_dir: str = "dataflow_edu/data/cleaning_and_refinement/3_4_domain_refined",
        output_dir: str = "dataflow_edu/data/cleaning_and_refinement/3_5_deduplicated",
        threshold: float = 0.9,
        num_perm: int = 128,
        n_gram: int = 5,
    ):
        super().__init__()
        self.logger = get_logger()
        self.input_dir = input_dir
        self.output_dir = output_dir
        self.threshold = threshold
        self.num_perm = num_perm
        self.n_gram = n_gram

    @staticmethod
    def get_desc(lang: str = "zh"):
        if lang == "zh":
            return (
                "3.5 Deduplication Operator：基于 MinHash + LSH 对题目题干去重，"
                "剔除高度重复的冗余题目，保留首次出现，剔除题单独保存。"
            )
        return "3.5 Deduplication Operator: remove duplicate questions by MinHash + LSH."

    def run(
        self,
        storage=None,
        input_dir: str | None = None,
        output_dir: str | None = None,
        config: EduConfig | None = None,
        no_confirm: bool = False,
    ):
        """
        执行去重：扫描 3_4_domain_refined -> 交互选择 -> MinHash+LSH 去重 -> 保存。
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

        dedup_cfg = config.operators.get("deduplication")
        if isinstance(dedup_cfg, dict):
            dedup_cfg = DeduplicationConfig(
                input_dir=str(dedup_cfg.get("input_dir", self.input_dir)),
                output_dir=str(dedup_cfg.get("output_dir", self.output_dir)),
                threshold=float(dedup_cfg.get("threshold", self.threshold)),
                num_perm=int(dedup_cfg.get("num_perm", self.num_perm)),
                n_gram=int(dedup_cfg.get("n_gram", self.n_gram)),
            )
        elif not isinstance(dedup_cfg, DeduplicationConfig):
            dedup_cfg = DeduplicationConfig(
                input_dir=input_dir,
                output_dir=output_dir,
                threshold=self.threshold,
                num_perm=self.num_perm,
                n_gram=self.n_gram,
            )

        input_dir_resolved = dedup_cfg.input_dir
        if not os.path.isabs(input_dir_resolved):
            input_dir_resolved = os.path.join(root, input_dir_resolved)
        output_dir_resolved = dedup_cfg.output_dir
        if not os.path.isabs(output_dir_resolved):
            output_dir_resolved = os.path.join(root, output_dir_resolved)

        candidates = _scan_deduplication_candidates(input_dir_resolved)
        if not candidates:
            self.logger.warning("没有找到可去重的教材（需先完成 3.4 Domain Refinement）")
            print("未找到教材，请先运行 3.4 Domain Refinement 完成 3_4_domain_refined。")
            return False, None, None

        _display_deduplication_table(candidates, input_dir_resolved, output_dir_resolved)

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
        input_path = os.path.join(input_dir_resolved, f"{selected}_domain_refined.json")
        if not os.path.isfile(input_path):
            print(f"输入文件不存在: {input_path}")
            return False, None, None

        print(f"\n教材: {selected}")
        print(f"输入: {input_path}")
        print(f"输出: {output_dir_resolved}")
        print("=" * 60)

        ok, deduplicated_path, removed_path = run_deduplication(
            input_path=input_path,
            output_dir=output_dir_resolved,
            folder_name=selected,
            threshold=dedup_cfg.threshold,
            num_perm=dedup_cfg.num_perm,
            n_gram=dedup_cfg.n_gram,
        )
        if ok and deduplicated_path and os.path.isfile(deduplicated_path):
            try:
                with open(deduplicated_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                n_kept = len(data.get("questions", []))
                n_removed = 0
                if removed_path and os.path.isfile(removed_path):
                    with open(removed_path, "r", encoding="utf-8") as f:
                        rem = json.load(f)
                    n_removed = len(rem.get("questions", []))
                print(f"\n【去重统计】保留 {n_kept} 题，剔除 {n_removed} 题")
            except Exception:
                pass
            print(f"\n3.5 Deduplication 完成: {deduplicated_path}")
        return ok, deduplicated_path, removed_path
