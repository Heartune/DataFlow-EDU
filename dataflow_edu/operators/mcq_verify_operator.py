# -*- coding: utf-8 -*-
"""
3.8 MCQ Verify Operator - 选择题结构校验 + LLM 修复

接在 3.7 Translation 之后，对 type ∈ {选择题/单选题/多选题} 的题目做 5 维结构校验，
失败题目尝试一次 LLM 修复（补缺失选项 + 规范答案字母），修复后复跑校验仍失败则剔除。
多语言独立校验（zh/en/fr，zh 必选），任一选中语言修不好整题剔除。

输出：
- 主文件 3_8_mcq_verified/{name}_mcq_verified.json
- 失败清单 {name}_mcq_failed.json（仅当存在被剔除题时落盘）
- 进度文件 {name}_mcq_verify_progress.json（支持 resume）
"""

import os

from dataflow import get_logger
from dataflow.core import OperatorABC
from dataflow.utils.registry import OPERATOR_REGISTRY

from dataflow_edu.config.schema import EduConfig, MCQVerifyConfig
from dataflow_edu.mcq_verify.core import (
    _scan_mcq_candidates,
    run_mcq_verify,
)
from dataflow_edu.serving import get_max_workers, interactive_config_llm

VERIFIED_SUFFIX = "_mcq_verified.json"


def _check_verified_status(folder_name: str, output_dir: str) -> bool:
    """检查该教材是否已完成 3.8 校验。"""
    return os.path.isfile(os.path.join(output_dir, f"{folder_name}{VERIFIED_SUFFIX}"))


def _display_mcq_table(candidates: list, output_dir: str):
    print(f"\n{'=' * 60}")
    print("3.8 MCQ Verify Operator - 可选教材")
    print(f"{'=' * 60}")
    print(f" {'序号':>4} | {'Verify':^6} | 教材名称")
    print("-" * 60)
    for i, name in enumerate(candidates, 1):
        done = _check_verified_status(name, output_dir)
        m = "Y" if done else "-"
        print(f" {i:>4} |   {m}    | {name}")
    print("=" * 60)


def _ask_target_languages(default_langs: list) -> list:
    """
    交互式选校验语言（zh 始终必选）。

    支持输入：
      - 回车: 沿用 default_langs（去重并保证含 zh）
      - 逗号分隔: 如 "zh,en" 或 "en,fr"（zh 自动补上）
      - "all": 等价 zh,en,fr
    """
    valid = ("zh", "en", "fr")
    default_langs = list(default_langs) if default_langs else list(valid)
    if "zh" not in default_langs:
        default_langs.insert(0, "zh")
    print("\n请选择要校验的语言（zh 必选；多选用逗号分隔，回车=默认，输入 all 选全部）")
    print(f"  可选: {','.join(valid)}    默认: [{','.join(default_langs)}]")
    raw = input("> ").strip().lower()
    if not raw:
        return default_langs
    if raw == "all":
        return list(valid)
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    picked = [p for p in parts if p in valid]
    if "zh" not in picked:
        picked.insert(0, "zh")
    if not picked:
        print("⚠ 输入无效，使用默认。")
        return default_langs
    # 去重保序
    seen = []
    for p in picked:
        if p not in seen:
            seen.append(p)
    return seen


@OPERATOR_REGISTRY.register()
class MCQVerifyOperator(OperatorABC):
    """
    3.8 MCQ Verify Operator：对选择题做结构校验 + LLM 自动修复。
    非选择题原样保留写入输出；MCQ 失败题先尝试 LLM 修复，修不好则剔除。
    多语言独立校验，任一语言修不好整题剔除。
    """

    def __init__(
        self,
        input_dir: str = "dataflow_edu/data/cleaning_and_refinement/3_7_translated",
        output_dir: str = "dataflow_edu/data/cleaning_and_refinement/3_8_mcq_verified",
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
                "3.8 MCQ Verify Operator：对 type 含选择/单选/多选 的题目做"
                "结构校验 + LLM 修复（补选项 / 规范答案字母），多语言独立校验。"
            )
        return "3.8 MCQ Verify Operator: structural validation + LLM repair on MCQs."

    def run(
        self,
        storage=None,
        input_dir: str | None = None,
        output_dir: str | None = None,
        config: EduConfig | None = None,
    ):
        """
        执行 MCQ 校验：扫描 3_7_translated -> 选教材 -> 配 LLM -> 选语言 -> resume? -> 执行。
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

        mcq_cfg = config.operators.get("mcq_verify")
        if isinstance(mcq_cfg, dict):
            mcq_defaults = MCQVerifyConfig()
            raw_langs = mcq_cfg.get("target_languages", mcq_defaults.target_languages)
            langs = (
                [str(x) for x in raw_langs]
                if isinstance(raw_langs, (list, tuple))
                else list(mcq_defaults.target_languages)
            )
            mcq_cfg = MCQVerifyConfig(
                input_dir=str(mcq_cfg.get("input_dir", self.input_dir)),
                output_dir=str(mcq_cfg.get("output_dir", self.output_dir)),
                target_languages=langs,
                max_workers=int(mcq_cfg.get("max_workers", self.max_workers)),
                max_retries=int(mcq_cfg.get("max_retries", mcq_defaults.max_retries)),
                max_tokens=int(mcq_cfg.get("max_tokens", mcq_defaults.max_tokens)),
                temperature=float(mcq_cfg.get("temperature", mcq_defaults.temperature)),
            )
        elif not isinstance(mcq_cfg, MCQVerifyConfig):
            mcq_cfg = MCQVerifyConfig(
                input_dir=input_dir,
                output_dir=output_dir,
                max_workers=self.max_workers,
            )

        input_dir_resolved = mcq_cfg.input_dir
        if not os.path.isabs(input_dir_resolved):
            input_dir_resolved = os.path.join(root, input_dir_resolved)
        output_dir_resolved = mcq_cfg.output_dir
        if not os.path.isabs(output_dir_resolved):
            output_dir_resolved = os.path.join(root, output_dir_resolved)
        os.makedirs(output_dir_resolved, exist_ok=True)

        candidates = _scan_mcq_candidates(input_dir_resolved)
        if not candidates:
            self.logger.warning("没有找到可校验的教材（需先完成 3.7 Translation）")
            print("未找到教材，请先运行 3.7 Translation 完成 3_7_translated。")
            return False, None, None

        _display_mcq_table(candidates, output_dir_resolved)

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
        input_path = os.path.join(input_dir_resolved, f"{selected}_translated.json")
        if not os.path.isfile(input_path):
            print(f"输入文件不存在: {input_path}")
            return False, None, None

        if not interactive_config_llm(gen_config_max_workers=mcq_cfg.max_workers):
            return False, None, None

        target_languages = _ask_target_languages(mcq_cfg.target_languages)

        resume_input = input("\n是否从上次进度继续？(y/N): ").strip().lower()
        resume = resume_input in ("y", "yes")

        max_workers = get_max_workers()
        print(f"\n教材: {selected}")
        print(f"输入: {input_path}")
        print(f"输出: {output_dir_resolved}")
        print(
            f"参数: target_languages={target_languages}, "
            f"max_tokens={mcq_cfg.max_tokens}, temperature={mcq_cfg.temperature}, "
            f"max_workers={max_workers}, resume={resume}"
        )
        print("=" * 60)

        ok, verified_path, failed_path = run_mcq_verify(
            input_path=input_path,
            output_dir=output_dir_resolved,
            folder_name=selected,
            target_languages=target_languages,
            max_workers=max_workers,
            max_retries=mcq_cfg.max_retries,
            max_tokens=mcq_cfg.max_tokens,
            temperature=mcq_cfg.temperature,
            resume=resume,
        )
        if ok and verified_path and os.path.isfile(verified_path):
            print(f"\n3.8 MCQ Verify 完成: {verified_path}")
            if failed_path:
                print(f"  失败清单: {failed_path}")
        return ok, verified_path, failed_path
