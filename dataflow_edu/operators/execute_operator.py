# -*- coding: utf-8 -*-
"""
4.1 Execute Operator - 将待测大模型接入系统进行作答，记录其答案。
"""

import copy
import glob
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import List, Tuple

from dataflow import get_logger
from dataflow.core import OperatorABC
from dataflow.utils.registry import OPERATOR_REGISTRY
from tqdm import tqdm

from dataflow_edu.config.schema import EduConfig, ExecuteConfig
from dataflow_edu.serving import llm_client

FLUSH_INTERVAL = 10  # 每完成 N 题刷新一次到磁盘


def _scan_execute_candidates(input_dir: str) -> List[Tuple[str, str]]:
    """扫描 input_dir 下 *_deduplicated.json，返回 [(stem, fullpath)]。"""
    if not os.path.isdir(input_dir):
        return []
    candidates = []
    for fname in sorted(os.listdir(input_dir)):
        if fname.endswith("_deduplicated.json"):
            stem = fname[: -len("_deduplicated.json")]
            if stem:
                candidates.append((stem, os.path.join(input_dir, fname)))
    return candidates


def _safe_model_id(model_name: str) -> str:
    """将模型名转为文件名安全字符串。"""
    return re.sub(r'[\\/:*?"<>|]', "_", model_name)


def _build_prompt(question: str, qtype: str) -> str:
    """根据题型构建学科通用作答 Prompt。"""
    qtype = str(qtype).strip() if qtype else ""
    qtext = str(question).strip()

    if qtype in ("单选题", "选择题"):
        return f"""请回答以下单选题。只输出选项字母（A、B、C 或 D），不要输出其他内容。

{qtext}"""
    if qtype in ("多选题",):
        return f"""请回答以下多选题。只输出正确选项的字母组合（如 ABC），不要输出其他内容。

{qtext}"""
    if qtype in ("填空题",):
        return f"""请对以下填空题作答，给出简洁准确的答案。

{qtext}"""
    if qtype in ("判断题",):
        return f"""请对以下判断题作答，只输出"对"或"错"。

{qtext}"""
    if qtype in ("简答题",):
        return f"""请回答以下简答题。

{qtext}"""
    if qtype in ("计算题",):
        return f"""请解答以下计算题，并给出解题过程和最终答案。

{qtext}"""
    if qtype in ("综合题",):
        return f"""请按要求回答以下综合题。

{qtext}"""
    # 未知题型
    return f"""请回答以下问题。

{qtext}"""


def _find_latest_resume_file(output_dir: str, stem: str, model_id_safe: str) -> str | None:
    """查找同一教材+model_id 的最新答案文件。"""
    pattern = os.path.join(output_dir, f"{stem}_{model_id_safe}_*.json")
    matches = glob.glob(pattern)
    if not matches:
        return None
    return max(matches, key=os.path.getmtime)


def _process_one(
    idx: int,
    question: dict,
    system_prompt: str,
) -> Tuple[int, str]:
    """处理单题，返回 (idx, model_answer)。"""
    qtext = question.get("question", "")
    qtype = question.get("type", "")
    if not qtext or not str(qtext).strip():
        return (idx, "")
    user_prompt = _build_prompt(qtext, qtype)
    result = llm_client.call_llm(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        max_tokens=8192,
        temperature=0.0,
    )
    return (idx, result.strip() if result else "")


def _display_execute_table(candidates: List[Tuple[str, str]], output_dir: str):
    """显示可选教材列表。"""
    print(f"\n{'=' * 60}")
    print("4.1 Execute Operator - 可选教材")
    print(f"{'=' * 60}")
    print(f" {'序号':>4} | 教材名称")
    print("-" * 60)
    for i, (stem, _) in enumerate(candidates, 1):
        print(f" {i:>4} | {stem}")
    print("=" * 60)


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

        candidates = _scan_execute_candidates(input_dir_resolved)
        if not candidates:
            self.logger.warning("未找到可执行的教材（需先完成 3.5 Deduplication）")
            print("未找到 *_deduplicated.json，请先运行 3.5 Deduplication。")
            return False, None

        _display_execute_table(candidates, output_dir_resolved)

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
        model_id_safe = _safe_model_id(model_name)
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
        resume_path = _find_latest_resume_file(output_dir_resolved, stem, model_id_safe)
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
                    # 用 resume 的数据作为工作副本
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

        start_time = time.time()
        success_count = 0

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(
                    _process_one, i, work_questions[i], system_prompt
                ): i
                for i in pending_indices
            }

            flush_count = 0
            with tqdm(total=len(pending_indices), desc="作答中", unit="题") as pbar:
                for future in as_completed(futures):
                    idx, answer = future.result()
                    if answer:
                        work_questions[idx]["model_answer"] = answer
                        success_count += 1
                    flush_count += 1
                    if flush_count >= FLUSH_INTERVAL:
                        out = {
                            "model_id": model_id_safe,
                            "model_name": model_name,
                            "source_file": os.path.basename(input_path),
                            "questions": work_questions,
                        }
                        with open(output_path, "w", encoding="utf-8") as f:
                            json.dump(out, f, ensure_ascii=False, indent=2)
                        flush_count = 0
                    if api_delay > 0:
                        time.sleep(api_delay)
                    pbar.update(1)
                    pbar.set_postfix(成功=f"{success_count}/{pbar.n}")

        out = {
            "model_id": model_id_safe,
            "model_name": model_name,
            "source_file": os.path.basename(input_path),
            "questions": work_questions,
        }
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)

        elapsed = time.time() - start_time
        print(f"\n完成: {output_path}")
        print(f"成功: {success_count}/{len(pending_indices)} ({success_count / len(pending_indices) * 100:.1f}%)")
        print(f"耗时: {elapsed:.2f}s")
        return True, output_path
