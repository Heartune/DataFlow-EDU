# -*- coding: utf-8 -*-
"""
Generation Operator - 两阶段题目生成：内容分类分析 + 习题与答案生成

基于 MinerU 输出的 Markdown 文本，按每两页一组作为 Context，
调用 LLM 进行批量化的习题与答案生成。使用 edu_config 的 taxonomy 与 question_types。
"""

import os
import unicodedata

from dataflow import get_logger


def _display_width(s: str) -> int:
    """CJK 等宽：中文等宽字符计 2，ASCII 计 1"""
    return sum(2 if unicodedata.east_asian_width(c) in ("F", "W") else 1 for c in s)


def _rjust_display(s: str, width: int) -> str:
    """按显示宽度右对齐"""
    return " " * max(0, width - _display_width(s)) + s
from dataflow.core import OperatorABC
from dataflow.utils.registry import OPERATOR_REGISTRY

from dataflow_edu.config.schema import EduConfig, GenerationConfig
from dataflow_edu.generation.generation_core import (
    get_stage1_output_path,
    load_md_from_folder,
    run_stage1,
    run_stage2,
)
from dataflow_edu.serving import (
    get_max_workers,
    init_client,
    interactive_config_llm,
)


def _scan_textbooks(md_dir: str) -> list:
    """扫描 md_dir 下教材子目录。"""
    if not os.path.isdir(md_dir):
        return []
    folders = []
    for name in sorted(os.listdir(md_dir)):
        path = os.path.join(md_dir, name)
        if os.path.isdir(path):
            try:
                load_md_from_folder(path)
                folders.append(name)
            except (FileNotFoundError, ValueError):
                pass
    return folders


def _check_stage_status(folder_name: str, output_dir: str) -> tuple:
    from dataflow_edu.generation.generation_core import get_stage1_dir, get_stage2_dir

    stage1_file = os.path.join(get_stage1_dir(output_dir), f"{folder_name}_stage1_taxonomy.json")
    stage2_excel = os.path.join(get_stage2_dir(output_dir), f"{folder_name}_generated_questions.xlsx")
    s1 = os.path.exists(stage1_file)
    s2 = os.path.exists(stage2_excel)
    return s1, s2


def _display_textbook_table(textbooks: list, output_dir: str) -> list:
    print(f"\n{'=' * 60}")
    print("2.1 Generation Operator - 教材列表")
    print(f"{'=' * 60}")
    print(f" {_rjust_display('序号', 4)} | {'阶段1':^3} | {'阶段2':^3} | 教材名称")
    print("-" * 60)
    statuses = []
    for i, name in enumerate(textbooks, 1):
        s1, s2 = _check_stage_status(name, output_dir)
        statuses.append((s1, s2))
        m1 = "Y" if s1 else "-"
        m2 = "Y" if s2 else "-"
        print(f" {i:>4} |   {m1}   |   {m2}   | {name}")
    print("=" * 60)
    return statuses


@OPERATOR_REGISTRY.register()
class GenerationOperator(OperatorABC):
    """
    2.1 Generation Operator：基于 Markdown 文本，两阶段批量生成习题与答案。
    阶段1 内容分类分析，阶段2 按小类+题型生成题目。支持交互选教材、API 配置、resume、Tiny。
    """

    def __init__(
        self,
        md_dir: str = "dataflow_edu/data/resources/md",
        output_dir: str = "dataflow_edu/data/generation_and_balancing",
        questions_per_pair: int = 5,
        max_workers: int = 8,
        api_delay: float = 0.3,
        request_timeout: int = 120,
        max_retries: int = 3,
        save_interval: int = 5,
    ):
        super().__init__()
        self.logger = get_logger()
        self.md_dir = md_dir
        self.output_dir = output_dir
        self.questions_per_pair = questions_per_pair
        self.max_workers = max_workers
        self.api_delay = api_delay
        self.request_timeout = request_timeout
        self.max_retries = max_retries
        self.save_interval = save_interval

    @staticmethod
    def get_desc(lang: str = "zh"):
        if lang == "zh":
            return (
                "2.1 Generation Operator：将解析后的 Markdown 文本按每两页一组作为 Context，"
                "阶段1 判断最适合的考察知识方向，阶段2 按 question_types.weight 分配题型、"
                "按 ability_levels.weight 分配能力层级，针对不同题型与能力层级使用不同 Prompt "
                "进行批量习题生成。输出 Excel + JSON。"
            )
        return "2.1 Generation Operator for exercise generation from Markdown."

    def run(
        self,
        storage=None,
        md_dir: str | None = None,
        output_dir: str | None = None,
        config: EduConfig | None = None,
    ):
        """
        执行两阶段生成流程：扫描教材 -> 交互选择 -> API 配置 -> 阶段选择 -> 执行。

        Args:
            storage: 占位，本算子不读写 DataFrame
            md_dir: Markdown 根目录（可覆盖 __init__）
            output_dir: 输出根目录（可覆盖 __init__）
            config: EduConfig，含 taxonomy、question_types、generation 参数。若为 None 则从 loader 加载

        Returns:
            (success, excel_path, json_path) 或 (False, None, None)
        """
        md_dir = md_dir or self.md_dir
        output_dir = output_dir or self.output_dir
        if not os.path.isabs(md_dir):
            from dataflow_edu.config.loader import get_config_path

            root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            md_dir = os.path.join(root, md_dir)
        if not os.path.isabs(output_dir):
            root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            output_dir = os.path.join(root, output_dir)

        if config is None:
            from dataflow_edu.config.loader import get_config_path, load_config

            root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            config = load_config(project_root=root)

        gen_cfg = config.operators.get("generation")
        if isinstance(gen_cfg, GenerationConfig):
            questions_per_pair = gen_cfg.questions_per_pair
            max_workers = gen_cfg.max_workers
        else:
            questions_per_pair = self.questions_per_pair
            max_workers = self.max_workers

        textbooks = _scan_textbooks(md_dir)
        if not textbooks:
            self.logger.warning("没有找到任何教材 Markdown 子目录")
            print("未找到教材，请先运行 1.2 MinerU OCR。")
            return False, None, None

        statuses = _display_textbook_table(textbooks, output_dir)

        print()
        choice = input("请输入序号选择教材（输入 q 退出）: ").strip()
        if choice.lower() == "q":
            return False, None, None
        try:
            idx = int(choice)
            if idx < 1 or idx > len(textbooks):
                print("无效序号。")
                return False, None, None
        except ValueError:
            print("无效输入。")
            return False, None, None

        selected = textbooks[idx - 1]
        md_folder = os.path.join(md_dir, selected)
        s1, s2 = statuses[idx - 1]

        if not interactive_config_llm(gen_config_max_workers=max_workers):
            return False, None, None

        suggested = "1" if not s1 else ("2" if not s2 else "all")
        stage_hint = f"按回车运行{suggested}阶段，或输入 1/2/all: "
        stage_input = input(stage_hint).strip() or suggested
        if stage_input not in ("1", "2", "all"):
            stage_input = suggested
        stage = stage_input

        resume_input = input("是否从上次进度继续？(y/N): ").strip().lower()
        resume = resume_input in ("y", "yes")

        tiny_input = input("Tiny 模式（随机抽取 N 组验证，0=全部）(直接回车使用 0 表示全部): ").strip()
        tiny = int(tiny_input) if tiny_input.isdigit() else 0
        tiny_seed = 42

        print(f"\n教材: {selected}")
        print(f"阶段: {stage} | resume={resume} | tiny={tiny}")
        print("=" * 60)

        max_workers = get_max_workers()

        if stage == "1":
            ok, stage1_file = run_stage1(
                md_folder,
                output_dir,
                config,
                max_workers=max_workers,
                resume=resume,
                tiny=tiny,
                tiny_seed=tiny_seed,
            )
            if ok and stage1_file:
                print(f"\n阶段1 完成: {stage1_file}")
            return ok, None, None

        if stage == "2":
            stage1_file = get_stage1_output_path(md_folder, output_dir)
            if not os.path.exists(stage1_file):
                print(f"阶段1 结果不存在: {stage1_file}，请先运行阶段1。")
                return False, None, None
            ok, excel_path, json_path = run_stage2(
                md_folder,
                output_dir,
                config,
                stage1_file,
                questions_per_pair=questions_per_pair,
                max_workers=max_workers,
                resume=resume,
            )
            if ok:
                print(f"\n阶段2 完成: {excel_path}")
            return ok, excel_path, json_path

        if stage == "all":
            ok1, stage1_file = run_stage1(
                md_folder,
                output_dir,
                config,
                max_workers=max_workers,
                resume=resume,
                tiny=tiny,
                tiny_seed=tiny_seed,
            )
            if not ok1:
                return False, None, None
            ok2, excel_path, json_path = run_stage2(
                md_folder,
                output_dir,
                config,
                stage1_file,
                questions_per_pair=questions_per_pair,
                max_workers=max_workers,
                resume=False,
            )
            if ok2:
                print(f"\n全部完成: {excel_path}")
            return ok2, excel_path, json_path

        return False, None, None
