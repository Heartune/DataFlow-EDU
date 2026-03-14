# -*- coding: utf-8 -*-
"""
4.1 Execute Operator - 将待测大模型接入系统进行作答，记录其答案。
"""

import copy
import json
import os
from datetime import datetime

from dataflow import get_logger
from dataflow.core import OperatorABC
from dataflow.utils.registry import OPERATOR_REGISTRY

from dataflow_edu.config.schema import EduConfig, ExecuteConfig
from dataflow_edu.execute.core import (
    display_execute_table,
    find_latest_resume_file,
    run_execute,
    scan_execute_candidates,
    safe_model_id,
)
from dataflow_edu.serving import llm_client


@OPERATOR_REGISTRY.register()
class ExecuteOperator(OperatorABC):
    """
    4.1 Execute Operator：将待测大模型接入系统进行作答，记录其答案。
    输入 3_5_deduplicated 的 JSON，输出带 model_answer 的完整 JSON 到 4_1_executed。
    """

    def __init__(
        self,
        input_dir: str = "dataflow_edu/data/cleaning_and_refinement/3_5_deduplicated",
        output_dir: str = "dataflow_edu/data/execute_and_judge/4_1_executed",
    ):
        super().__init__()
        self.logger = get_logger()
        self.input_dir = input_dir
        self.output_dir = output_dir

    @staticmethod
    def get_desc(lang: str = "zh"):
        if lang == "zh":
            return "4.1 Execute Operator：将待测大模型接入系统进行作答，记录其答案。"
        return "4.1 Execute Operator: run model to answer questions and record answers."

    def run(
        self,
        storage=None,
        input_dir: str | None = None,
        output_dir: str | None = None,
        config: EduConfig | None = None,
        no_confirm: bool = False,
    ):
        """
        执行作答：扫描 3_5_deduplicated -> 交互选择 -> 配置 LLM -> 可选 Tiny/续传 -> 并发调用 -> 保存。
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

        exec_cfg = config.operators.get("execute")
        if isinstance(exec_cfg, dict):
            exec_cfg = ExecuteConfig(
                input_dir=str(exec_cfg.get("input_dir", self.input_dir)),
                output_dir=str(exec_cfg.get("output_dir", self.output_dir)),
            )
        elif not isinstance(exec_cfg, ExecuteConfig):
            exec_cfg = ExecuteConfig(input_dir=input_dir, output_dir=output_dir)

        input_dir_resolved = exec_cfg.input_dir
        if not os.path.isabs(input_dir_resolved):
            input_dir_resolved = os.path.join(root, input_dir_resolved)
        output_dir_resolved = exec_cfg.output_dir
        if not os.path.isabs(output_dir_resolved):
            output_dir_resolved = os.path.join(root, output_dir_resolved)

        os.makedirs(output_dir_resolved, exist_ok=True)

        candidates = scan_execute_candidates(input_dir_resolved)
        if not candidates:
            self.logger.warning("未找到可执行的教材（需先完成 3.5 Deduplication）")
            print("未找到 *_deduplicated.json，请先运行 3.5 Deduplication。")
            return False, None

        display_execute_table(candidates, output_dir_resolved)

        print()
        choice = input("请输入序号选择教材（输入 q 退出）: ").strip()
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

        # 配置 LLM
        if not llm_client.interactive_config_llm():
            print("LLM 配置失败或已取消。")
            return False, None

        model_name = llm_client.get_model_name()
        model_id_safe = safe_model_id(model_name)
        max_workers = llm_client.get_max_workers()
        api_delay = llm_client.get_api_delay()

        with open(input_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        questions = data.get("questions", [])
        if not questions:
            print("题目列表为空。")
            return False, None

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

        work_questions = questions

        # 断点续传（仅当题目数量一致时）
        resume_path = find_latest_resume_file(output_dir_resolved, stem, model_id_safe)
        do_resume = False
        if resume_path and os.path.isfile(resume_path):
            print(f"\n检测到已有结果: {os.path.basename(resume_path)}")
            with open(resume_path, "r", encoding="utf-8") as f:
                resume_data = json.load(f)
            resume_questions = resume_data.get("questions", [])
            if len(resume_questions) == len(questions):
                done_count = sum(1 for q in resume_questions if q.get("model_answer"))
                pending_count = len(questions) - done_count
                print(f"  已完成: {done_count} 题，待处理: {pending_count} 题")
                resume_choice = input("是否断点续传? (1: 续传  2: 新建) [默认: 1]: ").strip()
                if resume_choice in ("", "1", "y", "yes"):
                    do_resume = True
                    work_questions = [copy.deepcopy(q) for q in resume_questions]

        if not do_resume:
            work_questions = [copy.deepcopy(q) for q in work_questions]
            for q in work_questions:
                q.pop("model_answer", None)

        pending_indices = [
            i for i in range(len(work_questions))
            if not work_questions[i].get("model_answer")
        ]

        if not pending_indices:
            print("所有题目已作答完成。")
            return True, resume_path if do_resume else None

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(
            output_dir_resolved,
            f"{stem}_{model_id_safe}_{timestamp}.json",
        )
        if do_resume:
            output_path = resume_path

        system_prompt = "请根据题目要求作答，给出准确、简洁的答案。"

        print(f"\n待处理: {len(pending_indices)} 题")
        print(f"输出: {output_path}")
        print("=" * 60)

        return run_execute(
            input_path=input_path,
            output_path=output_path,
            stem=stem,
            model_name=model_name,
            model_id_safe=model_id_safe,
            work_questions=work_questions,
            pending_indices=pending_indices,
            max_workers=max_workers,
            api_delay=api_delay,
            system_prompt=system_prompt,
        )
