# -*- coding: utf-8 -*-
"""
3.6 Synthesis Operator - 解析生成

基于 question + answer 调用 LLM 为每条题目生成 explanation 字段。
默认跳过已有 explanation 的题目，支持 resume 与"强制重生成"。
"""

import json
import os

from dataflow import get_logger
from dataflow.core import OperatorABC
from dataflow.utils.registry import OPERATOR_REGISTRY

from dataflow_edu.config.schema import EduConfig, SynthesisConfig
from dataflow_edu.serving import get_max_workers, interactive_config_llm
from dataflow_edu.synthesis.core import (
    _print_explanation_coverage,
    _scan_synthesis_candidates,
    run_synthesis,
)


def _check_synthesized_status(folder_name: str, output_dir: str) -> bool:
    """检查该教材是否已完成解析生成。"""
    path = os.path.join(output_dir, f"{folder_name}_synthesized.json")
    return os.path.isfile(path)


def _display_synthesis_table(candidates: list, input_dir: str, output_dir: str):
    print(f"\n{'=' * 60}")
    print("3.6 Synthesis Operator - 可选教材")
    print(f"{'=' * 60}")
    print(f" {'序号':>4} | {'Synth':^6} | 教材名称")
    print("-" * 60)
    for i, name in enumerate(candidates, 1):
        done = _check_synthesized_status(name, output_dir)
        m = "Y" if done else "-"
        print(f" {i:>4} |   {m}    | {name}")
    print("=" * 60)


@OPERATOR_REGISTRY.register()
class SynthesisOperator(OperatorABC):
    """
    3.6 Synthesis Operator：基于 question + answer 调用 LLM 生成 explanation 字段。
    默认跳过已有 explanation 的题目，支持 resume 与强制重生成。
    """

    def __init__(
        self,
        input_dir: str = "dataflow_edu/data/cleaning_and_refinement/3_5_deduplicated",
        output_dir: str = "dataflow_edu/data/cleaning_and_refinement/3_6_synthesized",
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
                "3.6 Synthesis Operator：基于 question + answer 调用 LLM 生成 explanation。"
                "默认跳过已有 explanation 的题目，支持 resume 与强制重生成。"
            )
        return "3.6 Synthesis Operator: generate explanation field via LLM."

    def run(
        self,
        storage=None,
        input_dir: str | None = None,
        output_dir: str | None = None,
        config: EduConfig | None = None,
    ):
        """
        执行解析生成：扫描 3_5_deduplicated -> 交互选择 -> API 配置 -> 生成 -> 保存。
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

        synth_cfg = config.operators.get("synthesis")
        if isinstance(synth_cfg, dict):
            synth_defaults = SynthesisConfig()
            synth_cfg = SynthesisConfig(
                input_dir=str(synth_cfg.get("input_dir", self.input_dir)),
                output_dir=str(synth_cfg.get("output_dir", self.output_dir)),
                max_workers=int(synth_cfg.get("max_workers", self.max_workers)),
                max_retries=int(synth_cfg.get("max_retries", synth_defaults.max_retries)),
                max_tokens=int(synth_cfg.get("max_tokens", synth_defaults.max_tokens)),
                temperature=float(synth_cfg.get("temperature", synth_defaults.temperature)),
                skip_existing=bool(synth_cfg.get("skip_existing", synth_defaults.skip_existing)),
            )
        elif not isinstance(synth_cfg, SynthesisConfig):
            synth_cfg = SynthesisConfig(
                input_dir=input_dir,
                output_dir=output_dir,
                max_workers=self.max_workers,
            )

        input_dir_resolved = synth_cfg.input_dir
        if not os.path.isabs(input_dir_resolved):
            input_dir_resolved = os.path.join(root, input_dir_resolved)
        output_dir_resolved = synth_cfg.output_dir
        if not os.path.isabs(output_dir_resolved):
            output_dir_resolved = os.path.join(root, output_dir_resolved)
        os.makedirs(output_dir_resolved, exist_ok=True)

        candidates = _scan_synthesis_candidates(input_dir_resolved)
        if not candidates:
            self.logger.warning("没有找到可生成解析的教材（需先完成 3.5 Deduplication）")
            print("未找到教材，请先运行 3.5 Deduplication 完成 3_5_deduplicated。")
            return False, None

        _display_synthesis_table(candidates, input_dir_resolved, output_dir_resolved)

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
        input_path = os.path.join(input_dir_resolved, f"{selected}_deduplicated.json")
        if not os.path.isfile(input_path):
            print(f"输入文件不存在: {input_path}")
            return False, None

        if not interactive_config_llm(gen_config_max_workers=synth_cfg.max_workers):
            return False, None

        resume_input = input("是否从上次进度继续？(y/N): ").strip().lower()
        resume = resume_input in ("y", "yes")

        force_input = input(
            "是否强制重生成已有 explanation 的题目？(y/N): "
        ).strip().lower()
        force_regenerate = force_input in ("y", "yes")
        skip_existing = synth_cfg.skip_existing and not force_regenerate

        max_workers = get_max_workers()
        print(f"\n教材: {selected}")
        print(f"输入: {input_path}")
        print(f"输出: {output_dir_resolved}")
        print(
            f"参数: max_tokens={synth_cfg.max_tokens}, temperature={synth_cfg.temperature}, "
            f"skip_existing={skip_existing}, force_regenerate={force_regenerate}"
        )
        print("=" * 60)

        ok, synthesized_path = run_synthesis(
            input_path=input_path,
            output_dir=output_dir_resolved,
            folder_name=selected,
            max_workers=max_workers,
            max_retries=synth_cfg.max_retries,
            max_tokens=synth_cfg.max_tokens,
            temperature=synth_cfg.temperature,
            skip_existing=skip_existing,
            force_regenerate=force_regenerate,
            resume=resume,
        )
        if ok and synthesized_path and os.path.isfile(synthesized_path):
            try:
                with open(synthesized_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                _print_explanation_coverage(data.get("questions", []))
            except Exception:
                pass
            print(f"\n3.6 Synthesis 完成: {synthesized_path}")
        return ok, synthesized_path
