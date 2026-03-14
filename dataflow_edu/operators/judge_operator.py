# -*- coding: utf-8 -*-
"""
4.2 Judge Operator - 基于正确答案的 LLM-as-a-Judge 评分。
"""

import copy
import json
import os
from datetime import datetime

from dataflow import get_logger
from dataflow.core import OperatorABC
from dataflow.utils.registry import OPERATOR_REGISTRY

from dataflow_edu.config.schema import EduConfig, JudgeConfig
from dataflow_edu.judge.core import (
    display_judge_table,
    find_latest_resume_file,
    run_judge,
    safe_model_id,
    scan_judge_candidates,
)
from dataflow_edu.serving import llm_client


@OPERATOR_REGISTRY.register()
class JudgeOperator(OperatorABC):
    """
    4.2 Judge Operator：基于 4.1 Execute 产出，调用大模型作为裁判评分。
    输入 4_1_executed JSON，输出带 judge_score 的 JSON 到 4_2_judged。
    """

    def __init__(
        self,
        input_dir: str = "dataflow_edu/data/execute_and_judge/4_1_executed",
        output_dir: str = "dataflow_edu/data/execute_and_judge/4_2_judged",
    ):
        super().__init__()
        self.logger = get_logger()
        self.input_dir = input_dir
        self.output_dir = output_dir

    @staticmethod
    def get_desc(lang: str = "zh"):
        if lang == "zh":
            return "4.2 Judge Operator：基于正确答案调用大模型作为裁判评分。"
        return "4.2 Judge Operator: LLM-as-a-Judge scoring based on reference answers."

    def run(
        self,
        storage=None,
        input_dir: str | None = None,
        output_dir: str | None = None,
        config: EduConfig | None = None,
        no_confirm: bool = False,
    ):
        """
        执行评分：扫描 4_1 -> 选文件 -> judge_mode -> (mode=1 时) LLM 配置 -> Tiny/续传 -> 并发 -> 保存。
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

        judge_cfg = config.operators.get("judge")
        if isinstance(judge_cfg, dict):
            judge_cfg = JudgeConfig(
                input_dir=str(judge_cfg.get("input_dir", self.input_dir)),
                output_dir=str(judge_cfg.get("output_dir", self.output_dir)),
            )
        elif not isinstance(judge_cfg, JudgeConfig):
            judge_cfg = JudgeConfig(input_dir=input_dir, output_dir=output_dir)

        input_dir_resolved = judge_cfg.input_dir
        if not os.path.isabs(input_dir_resolved):
            input_dir_resolved = os.path.join(root, input_dir_resolved)
        output_dir_resolved = judge_cfg.output_dir
        if not os.path.isabs(output_dir_resolved):
            output_dir_resolved = os.path.join(root, output_dir_resolved)

        os.makedirs(output_dir_resolved, exist_ok=True)

        candidates = scan_judge_candidates(input_dir_resolved)
        if not candidates:
            self.logger.warning("未找到可评分的文件（需先完成 4.1 Execute）")
            print("未找到 4_1_executed 下的 JSON 文件，请先运行 4.1 Execute。")
            return False, None

        display_judge_table(candidates)

        print()
        choice = input("请输入序号选择文件（输入 q 退出）: ").strip()
        if choice.lower() == "q":
            return False, None
        try:
            idx_sel = int(choice)
            if idx_sel < 1 or idx_sel > len(candidates):
                print("无效序号。")
                return False, None
        except ValueError:
            print("无效输入。")
            return False, None

        stem, input_path = candidates[idx_sel - 1]
        if not os.path.isfile(input_path):
            print(f"输入文件不存在: {input_path}")
            return False, None

        print("\n请选择评分模式:")
        print("  0: 仅客观题（单选题、多选题、判断题 - 规则评分，不调用 LLM）")
        print("  1: 全部题型（含填空题、简答题、计算题、综合题 - 需 LLM）")
        mode_choice = input("请输入 (0/1) [默认: 1]: ").strip()
        judge_mode = 1 if mode_choice != "0" else 0

        need_llm = judge_mode == 1
        if need_llm:
            if not llm_client.interactive_config_llm():
                print("LLM 配置失败或已取消。")
                return False, None
            model_name = llm_client.get_model_name()
        else:
            model_name = "rule_based"
        model_id_safe = safe_model_id(model_name)
        max_workers = llm_client.get_max_workers() if need_llm else 1
        api_delay = llm_client.get_api_delay() if need_llm else 0

        with open(input_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        questions = data.get("questions", [])
        model_id_from_file = data.get("model_id", model_id_safe)
        source_file = data.get("source_file", os.path.basename(input_path))

        if not questions:
            print("题目列表为空。")
            return False, None

        base = os.path.basename(input_path)
        if base.endswith(".json"):
            base = base[:-5]
        out_stem = base

        # Tiny 模式
        tiny_choice = input(
            "\n是否启用 Tiny 模式（随机抽取部分题目快速验证）? (输入数量 / N:全部处理) [默认: N]: "
        ).strip()
        if tiny_choice and tiny_choice.lower() not in ("n", "no"):
            try:
                tiny_n = int(tiny_choice)
                if tiny_n > 0 and tiny_n < len(questions):
                    seed_in = input("随机种子 [默认: 42]: ").strip()
                    tiny_seed = 42
                    if seed_in:
                        try:
                            tiny_seed = int(seed_in)
                        except ValueError:
                            pass
                    import random

                    rng = random.Random(tiny_seed)
                    indices_sampled = sorted(rng.sample(range(len(questions)), tiny_n))
                    questions = [questions[i] for i in indices_sampled]
                    print(f"  [Tiny] 从 {len(data['questions'])} 题中抽取 {tiny_n} 题 (seed={tiny_seed})")
            except ValueError:
                pass

        work_questions = [copy.deepcopy(q) for q in questions]

        # 断点续传
        resume_path = find_latest_resume_file(output_dir_resolved, out_stem)
        do_resume = False
        if resume_path and os.path.isfile(resume_path):
            print(f"\n检测到已有评分结果: {os.path.basename(resume_path)}")
            with open(resume_path, "r", encoding="utf-8") as f:
                resume_data = json.load(f)
            resume_questions = resume_data.get("questions", [])
            if len(resume_questions) == len(work_questions):
                done_count = sum(1 for q in resume_questions if "judge_score" in q)
                pending_count = len(work_questions) - done_count
                print(f"  已评分: {done_count} 题，待评分: {pending_count} 题")
                resume_choice = input("是否断点续传? (1: 续传  2: 新建) [默认: 1]: ").strip()
                if resume_choice in ("", "1", "y", "yes"):
                    do_resume = True
                    work_questions = [copy.deepcopy(q) for q in resume_questions]

        pending_indices = [
            i for i in range(len(work_questions))
            if "judge_score" not in work_questions[i]
        ]

        if not pending_indices:
            print("所有题目已评分完成。")
            return True, resume_path if do_resume else None

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(
            output_dir_resolved,
            f"{out_stem}_judged_{timestamp}.json",
        )
        if do_resume:
            output_path = resume_path

        system_prompt = "你是答案评判专家。请判断模型答案与标准答案是否语义一致，输出 JSON 格式结果。"

        print(f"\n待评分: {len(pending_indices)} 题")
        print(f"输出: {output_path}")
        print("=" * 60)

        return run_judge(
            output_path=output_path,
            model_id_from_file=model_id_from_file,
            source_file=source_file,
            judge_mode=judge_mode,
            work_questions=work_questions,
            pending_indices=pending_indices,
            max_workers=max_workers,
            api_delay=api_delay,
            system_prompt=system_prompt,
        )
