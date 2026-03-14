# -*- coding: utf-8 -*-
"""
4.2 Judge Operator - 基于正确答案的 LLM-as-a-Judge 评分。
输入 4_1_executed JSON，输出带 judge_score 的 JSON 到 4_2_judged。
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

from dataflow_edu.config.schema import EduConfig, JudgeConfig
from dataflow_edu.operators.judge_rule_scoring import (
    LLM_TYPES,
    OBJECTIVE_TYPES,
    score_multiple_choice,
    score_single_choice,
    score_true_false,
)
from dataflow_edu.serving import llm_client

FLUSH_INTERVAL = 10


def _scan_judge_candidates(input_dir: str) -> List[Tuple[str, str]]]:
    """扫描 input_dir 下 4_1 产出的 JSON（排除 *_judged_*），返回 [(display_name, fullpath)]。"""
    if not os.path.isdir(input_dir):
        return []
    candidates = []
    for fname in sorted(os.listdir(input_dir)):
        if not fname.endswith(".json") or "_judged_" in fname or fname.startswith("."):
            continue
        fullpath = os.path.join(input_dir, fname)
        if os.path.isfile(fullpath):
            candidates.append((fname[:-5], fullpath))  # display_name = stem without .json
    return candidates


def _display_judge_table(candidates: List[Tuple[str, str]]) -> None:
    """交互展示可选文件列表。"""
    print(f"\n{'=' * 60}")
    print("4.2 Judge Operator - 可选文件")
    print("=" * 60)
    print(f" {'序号':>4} | 文件")
    print("-" * 60)
    for i, (name, _) in enumerate(candidates, 1):
        print(f" {i:>4} | {name}.json")
    print("=" * 60)


def _safe_model_id(model_name: str) -> str:
    """将模型名转为文件名安全字符串。"""
    return re.sub(r'[\\/:*?"<>|]', "_", model_name)


def _find_latest_resume_file(output_dir: str, stem: str, model_id_safe: str) -> str | None:
    """查找已存在的 judged 文件用于断点续传。"""
    pattern = os.path.join(output_dir, f"{stem}_*_judged_*.json")
    matches = glob.glob(pattern)
    # 进一步按 model_id 过滤（stem 可能含 model_id）
    filtered = [m for m in matches if f"_{model_id_safe}_judged_" in m]
    if not filtered:
        return None
    return max(filtered, key=os.path.getmtime)


def _build_llm_prompt(question: str, reference_answer: str, model_answer: str) -> str:
    """构建语义一致性评判 prompt（DataFlow AnswerJudgePrompt 风格）。"""
    return f"""你是答案评判专家。请判断模型答案与标准答案是否语义一致。

题目：{question}
标准答案：{reference_answer}
模型答案：{model_answer}

请仅比较答案语义是否一致，不比较解题过程。若语义一致则判正确。
请以 JSON 格式输出：{{"judgement_result": true}} 或 {{"judgement_result": false}}
"""


def _extract_judgement_result(llm_output: str) -> float:
    """从 LLM 返回中解析 judgement_result，true→1.0，false→0.0。"""
    if not llm_output or not isinstance(llm_output, str):
        return 0.0
    s = llm_output.strip()
    try:
        # 尝试提取 JSON
        m = re.search(r'\{[^{}]*"judgement_result"[^{}]*\}', s)
        if m:
            obj = json.loads(m.group(0))
            val = obj.get("judgement_result")
            if val is True:
                return 1.0
            if val is False:
                return 0.0
        # 回退：匹配 true/false
        if re.search(r'"judgement_result"\s*:\s*true', s, re.I):
            return 1.0
        if re.search(r'"judgement_result"\s*:\s*false', s, re.I):
            return 0.0
    except (json.JSONDecodeError, TypeError):
        pass
    return 0.0


def _process_one(
    idx: int,
    q: dict,
    judge_mode: int,
    system_prompt: str,
) -> Tuple[int, float, str]:
    """
    单题评分。返回 (idx, score, method)。
    method: "rule" | "llm"
    """
    qtype = str(q.get("type", "")).strip()
    model_answer = q.get("model_answer", "")
    standard_answer = q.get("answer", "")

    if not model_answer or not str(model_answer).strip():
        return (idx, 0.0, "skip")

    model_out = str(model_answer).strip()
    std_ans = str(standard_answer).strip() if standard_answer else ""

    # 规则评分（客观题）
    if qtype in ("单选题", "选择题"):
        score, _ = score_single_choice(model_out, std_ans)
        return (idx, score, "rule")
    if qtype == "多选题":
        score, _ = score_multiple_choice(model_out, std_ans)
        return (idx, score, "rule")
    if qtype == "判断题":
        score, _ = score_true_false(model_out, std_ans)
        return (idx, score, "rule")

    # mode 0：仅客观题，其他题型跳过
    if judge_mode == 0:
        return (idx, 0.0, "skip")

    # mode 1：主观题用 LLM
    if qtype in LLM_TYPES or qtype not in OBJECTIVE_TYPES:
        question_text = q.get("question", "")
        user_prompt = _build_llm_prompt(question_text, std_ans, model_out)
        result = llm_client.call_llm(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=512,
            temperature=0.0,
        )
        score = _extract_judgement_result(result) if result else 0.0
        return (idx, score, "llm")

    return (idx, 0.0, "skip")


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

        candidates = _scan_judge_candidates(input_dir_resolved)
        if not candidates:
            self.logger.warning("未找到可评分的文件（需先完成 4.1 Execute）")
            print("未找到 4_1_executed 下的 JSON 文件，请先运行 4.1 Execute。")
            return False, None

        _display_judge_table(candidates)

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

        # judge_mode
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
        model_id_safe = _safe_model_id(model_name)
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

        # 解析 stem：用于输出命名。4_1 文件名为 {stem}_{model_id}_{timestamp}.json
        base = os.path.basename(input_path)
        if base.endswith(".json"):
            base = base[:-5]
        parts = base.rsplit("_", 2)  # 最后两段为 timestamp (YYYYMMDD_HHMMSS)
        out_stem = parts[0] if len(parts) >= 3 else base

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
        resume_path = _find_latest_resume_file(output_dir_resolved, out_stem, model_id_safe)
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
            f"{out_stem}_{model_id_safe}_judged_{timestamp}.json",
        )
        if do_resume:
            output_path = resume_path

        system_prompt = "你是答案评判专家。请判断模型答案与标准答案是否语义一致，输出 JSON 格式结果。"

        print(f"\n待评分: {len(pending_indices)} 题")
        print(f"输出: {output_path}")
        print("=" * 60)

        start_time = time.time()
        rule_count = 0
        llm_count = 0
        correct_count = 0

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(
                    _process_one, i, work_questions[i], judge_mode, system_prompt
                ): i
                for i in pending_indices
            }

            flush_count = 0
            with tqdm(total=len(pending_indices), desc="评分中", unit="题") as pbar:
                for future in as_completed(futures):
                    idx, score, method = future.result()
                    work_questions[idx]["judge_score"] = score
                    if method == "rule":
                        rule_count += 1
                    elif method == "llm":
                        llm_count += 1
                    if score >= 0.99:
                        correct_count += 1
                    if method == "llm":
                        work_questions[idx]["judgement_result"] = bool(score >= 0.5)
                    flush_count += 1
                    if flush_count >= FLUSH_INTERVAL:
                        out = {
                            "model_id": model_id_from_file,
                            "source_file": source_file,
                            "judge_mode": judge_mode,
                            "questions": work_questions,
                        }
                        with open(output_path, "w", encoding="utf-8") as f:
                            json.dump(out, f, ensure_ascii=False, indent=2)
                        flush_count = 0
                    if api_delay > 0:
                        time.sleep(api_delay)
                    pbar.update(1)
                    pbar.set_postfix(
                        规则=rule_count,
                        LLM=llm_count,
                        正确=correct_count,
                    )

        out = {
            "model_id": model_id_from_file,
            "source_file": source_file,
            "judge_mode": judge_mode,
            "questions": work_questions,
        }
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)

        elapsed = time.time() - start_time
        total_scored = rule_count + llm_count
        print(f"\n完成: {output_path}")
        print(f"已评分: {total_scored} 题（规则={rule_count}, LLM={llm_count}）")
        print(f"正确: {correct_count}/{total_scored}")
        print(f"耗时: {elapsed:.2f}s")
        return True, output_path
