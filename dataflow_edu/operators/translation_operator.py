# -*- coding: utf-8 -*-
"""
3.7 Translation Operator - 多语言翻译

默认中→英 / 中→法翻译 question/answer/explanation/options 字段，
平铺到 *_en / *_fr 字段；支持残留中文重翻。
"""

import json
import os

from dataflow import get_logger
from dataflow.core import OperatorABC
from dataflow.utils.registry import OPERATOR_REGISTRY

from dataflow_edu.config.schema import EduConfig, TranslationConfig
from dataflow_edu.serving import get_max_workers, interactive_config_llm
from dataflow_edu.translation.core import (
    _print_translation_coverage,
    _scan_translation_candidates,
    run_translation,
)


def _check_translated_status(folder_name: str, output_dir: str) -> bool:
    """检查该教材是否已完成翻译。"""
    path = os.path.join(output_dir, f"{folder_name}_translated.json")
    return os.path.isfile(path)


def _display_translation_table(candidates: list, input_dir: str, output_dir: str):
    print(f"\n{'=' * 60}")
    print("3.7 Translation Operator - 可选教材")
    print(f"{'=' * 60}")
    print(f" {'序号':>4} | {'Trans':^6} | 教材名称")
    print("-" * 60)
    for i, name in enumerate(candidates, 1):
        done = _check_translated_status(name, output_dir)
        m = "Y" if done else "-"
        print(f" {i:>4} |   {m}    | {name}")
    print("=" * 60)


def _ask_target_languages(default_langs: list) -> list:
    """交互式确认目标语言。直接回车沿用，输入逗号分隔可临时覆盖。"""
    raw = input(
        f"目标语言（逗号分隔，回车使用 [{','.join(default_langs)}]): "
    ).strip()
    if not raw:
        return list(default_langs)
    parts = [p.strip().lower() for p in raw.split(",") if p.strip()]
    valid = [p for p in parts if p in ("en", "fr")]
    if not valid:
        print("⚠ 输入无效，将使用默认。")
        return list(default_langs)
    return valid


def _ask_mode() -> str:
    """交互式选模式。"""
    print("\n请选择翻译模式：")
    print("  1. 首次翻译（仅翻译尚未翻译/缺译的字段）")
    print("  2. 仅重翻残留（在已有翻译基础上检测并修复中文残留）")
    print("  3. 两者顺序执行（先 1 后 2）")
    while True:
        c = input("请输入 1/2/3 (回车=3): ").strip()
        if not c:
            return "both"
        if c == "1":
            return "first"
        if c == "2":
            return "residual"
        if c == "3":
            return "both"
        print("无效输入，请重试。")


@OPERATOR_REGISTRY.register()
class TranslationOperator(OperatorABC):
    """
    3.7 Translation Operator：默认中→英/法翻译 question/answer/explanation/options。
    输出平铺字段 *_en / *_fr；支持残留中文重翻；选项字母 A./B./... 保留。
    """

    def __init__(
        self,
        input_dir: str = "dataflow_edu/data/cleaning_and_refinement/3_6_synthesized",
        output_dir: str = "dataflow_edu/data/cleaning_and_refinement/3_7_translated",
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
                "3.7 Translation Operator：默认中→英/法翻译 question/answer/explanation/options，"
                "平铺到 *_en / *_fr；支持残留中文重翻。"
            )
        return "3.7 Translation Operator: translate Q/A/explanation/options to en/fr."

    def run(
        self,
        storage=None,
        input_dir: str | None = None,
        output_dir: str | None = None,
        config: EduConfig | None = None,
    ):
        """
        执行翻译：扫描 3_6_synthesized -> 交互选择 -> 选语言 -> 选模式 -> 翻译 -> 保存。
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

        trans_cfg = config.operators.get("translation")
        if isinstance(trans_cfg, dict):
            trans_defaults = TranslationConfig()
            raw_langs = trans_cfg.get("target_languages", trans_defaults.target_languages)
            langs = (
                [str(x) for x in raw_langs]
                if isinstance(raw_langs, (list, tuple))
                else list(trans_defaults.target_languages)
            )
            raw_fields = trans_cfg.get("translate_fields", trans_defaults.translate_fields)
            fields = (
                [str(x) for x in raw_fields]
                if isinstance(raw_fields, (list, tuple))
                else list(trans_defaults.translate_fields)
            )
            trans_cfg = TranslationConfig(
                input_dir=str(trans_cfg.get("input_dir", self.input_dir)),
                output_dir=str(trans_cfg.get("output_dir", self.output_dir)),
                target_languages=langs,
                translate_fields=fields,
                max_workers=int(trans_cfg.get("max_workers", self.max_workers)),
                max_retries=int(trans_cfg.get("max_retries", trans_defaults.max_retries)),
                residual_pattern_zh=bool(trans_cfg.get("residual_pattern_zh", trans_defaults.residual_pattern_zh)),
                fix_french_option_letter=bool(
                    trans_cfg.get("fix_french_option_letter", trans_defaults.fix_french_option_letter)
                ),
            )
        elif not isinstance(trans_cfg, TranslationConfig):
            trans_cfg = TranslationConfig(
                input_dir=input_dir,
                output_dir=output_dir,
                max_workers=self.max_workers,
            )

        input_dir_resolved = trans_cfg.input_dir
        if not os.path.isabs(input_dir_resolved):
            input_dir_resolved = os.path.join(root, input_dir_resolved)
        output_dir_resolved = trans_cfg.output_dir
        if not os.path.isabs(output_dir_resolved):
            output_dir_resolved = os.path.join(root, output_dir_resolved)
        os.makedirs(output_dir_resolved, exist_ok=True)

        candidates = _scan_translation_candidates(input_dir_resolved)
        if not candidates:
            self.logger.warning("没有找到可翻译的教材（需先完成 3.6 Synthesis）")
            print("未找到教材，请先运行 3.6 Synthesis 完成 3_6_synthesized。")
            return False, None, None

        _display_translation_table(candidates, input_dir_resolved, output_dir_resolved)

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
        input_path = os.path.join(input_dir_resolved, f"{selected}_synthesized.json")
        if not os.path.isfile(input_path):
            print(f"输入文件不存在: {input_path}")
            return False, None, None

        if not interactive_config_llm(gen_config_max_workers=trans_cfg.max_workers):
            return False, None, None

        target_languages = _ask_target_languages(trans_cfg.target_languages)
        mode = _ask_mode()

        max_workers = get_max_workers()
        print(f"\n教材: {selected}")
        print(f"输入: {input_path}")
        print(f"输出: {output_dir_resolved}")
        print(
            f"目标语言: {target_languages}  字段: {trans_cfg.translate_fields}  模式: {mode}"
        )
        print("=" * 60)

        ok, translated_path, failed_path = run_translation(
            input_path=input_path,
            output_dir=output_dir_resolved,
            folder_name=selected,
            mode=mode,
            target_languages=target_languages,
            translate_fields=trans_cfg.translate_fields,
            max_workers=max_workers,
            max_retries=trans_cfg.max_retries,
            fix_french_option_letter=trans_cfg.fix_french_option_letter,
            skip_existing=True,
        )

        if ok and translated_path and os.path.isfile(translated_path):
            try:
                with open(translated_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                _print_translation_coverage(
                    data.get("questions", []),
                    target_languages,
                    trans_cfg.translate_fields,
                )
            except Exception:
                pass
            print(f"\n3.7 Translation 完成: {translated_path}")
            if failed_path:
                print(f"  残留失败清单: {failed_path}")
        return ok, translated_path, failed_path
