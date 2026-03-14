import json
import re
from typing import List, Dict, Any

import pandas as pd

from dataflow.utils.storage import DataFlowStorage
from dataflow.core import OperatorABC, LLMServingABC
from dataflow.utils.registry import OPERATOR_REGISTRY
from dataflow import get_logger

from dataflow.utils.reasoning.robotics_relevance_config import (
    get_default_robotics_relevance_config,
    build_robotics_relevance_prompt,
)


@OPERATOR_REGISTRY.register()
class RoboticsRelevanceSampleEvaluator(OperatorABC):
    """
    基于大模型的“机器人学相关性 + 小类划分”评估算子（样本级）。

    - 输入：包含题目与答案的 DataFrame（典型列名为 question / answer）
    - 输出：
        - 一列机器人学相关性分数（0–1），默认列名为 robotics_relevance
        - 若干列小类名称与置信度，例如：
            - robotics_category1_name / robotics_category1_confidence
            - robotics_category2_name / robotics_category2_confidence
            - robotics_category3_name / robotics_category3_confidence

    该算子依赖外部注入的 LLMServing 实例，不在内部管理具体的 API Key 或模型路径。
    """

    def __init__(
        self,
        llm_serving: LLMServingABC,
        max_categories: int = 3,
    ):
        self.logger = get_logger()
        self.llm_serving = llm_serving
        self.max_categories = max_categories
        self._default_cfg = get_default_robotics_relevance_config()

    @staticmethod
    def get_desc(lang: str = "zh"):
        if lang == "zh":
            return (
                "对每条问答对进行“是否属于机器人领域”相关性评估，并给出最多 3 个机器人学细分小类及其置信度。\n"
                "输入：DataFrame 中的问题列和答案列（默认列名为 question / answer）。\n"
                "输出：一列相关性分数（默认 robotics_relevance）以及若干小类名称与置信度列。"
            )
        else:
            return (
                "Evaluate how related each QA pair is to robotics, and assign up to three robotics sub-categories "
                "with confidence scores. Inputs: question/answer columns in a DataFrame. "
                "Outputs: a relevance score column plus several category/confidence columns."
            )

    def _validate_dataframe(
        self,
        dataframe: pd.DataFrame,
        input_question_key: str,
        input_answer_key: str,
        output_relevance_key: str,
        output_category_prefix: str,
    ):
        required_cols = [input_question_key, input_answer_key]
        missing = [c for c in required_cols if c not in dataframe.columns]
        if missing:
            raise ValueError(f"Missing required column(s): {missing}")

        # 避免无意覆盖已有列
        forbidden_cols = [output_relevance_key]
        for i in range(1, self.max_categories + 1):
            forbidden_cols.append(f"{output_category_prefix}{i}_name")
            forbidden_cols.append(f"{output_category_prefix}{i}_confidence")
        conflict = [c for c in forbidden_cols if c in dataframe.columns]
        if conflict:
            raise ValueError(
                f"The following column(s) already exist and would be overwritten: {conflict}"
            )

    def _build_prompts(
        self,
        dataframe: pd.DataFrame,
        input_question_key: str,
        input_answer_key: str,
        categories_text: str,
    ) -> List[str]:
        prompts: List[str] = []
        for _, row in dataframe.iterrows():
            question = str(row.get(input_question_key, "")).strip()
            answer = str(row.get(input_answer_key, "")).strip()
            prompts.append(build_robotics_relevance_prompt(question, answer, categories_text))
        return prompts

    def _clean_response_text(self, text: str) -> str:
        """
        去掉 Markdown 代码块、前后空白等，只保留 JSON 主体字符串。
        """
        s = text.strip()
        # 去除 ```json ``` 包裹
        s = re.sub(r"^```json\s*|\s*```$", "", s, flags=re.DOTALL)
        s = s.strip()
        return s

    def _parse_response(self, text: str) -> Dict[str, Any]:
        """
        将模型返回的字符串解析为约定的字典格式。
        解析失败时抛出异常，由上层决定如何降级处理。
        """
        cleaned = self._clean_response_text(text)
        data = json.loads(cleaned)

        relevance = float(data.get("robotics_relevance", 0.0))
        categories = data.get("categories", [])
        if not isinstance(categories, list):
            categories = []

        parsed_categories: List[Dict[str, Any]] = []
        for item in categories[: self.max_categories]:
            if not isinstance(item, dict):
                continue
            name = str(item.get("category_name", "")).strip()
            try:
                conf = float(item.get("confidence", 0.0))
            except Exception:
                conf = 0.0
            parsed_categories.append(
                {
                    "category_name": name,
                    "confidence": conf,
                }
            )

        return {
            "robotics_relevance": relevance,
            "categories": parsed_categories,
        }

    def run(
        self,
        storage: DataFlowStorage,
        input_question_key: str = None,
        input_answer_key: str = None,
        output_relevance_key: str = None,
        output_category_prefix: str = None,
    ):
        """
        对存储中的 DataFrame 逐行进行机器人领域相关性与小类评估。
        """
        cfg = self._default_cfg
        if input_question_key is None:
            input_question_key = cfg["input_question_key"]
        if input_answer_key is None:
            input_answer_key = cfg["input_answer_key"]
        if output_relevance_key is None:
            output_relevance_key = cfg["output_relevance_key"]
        if output_category_prefix is None:
            output_category_prefix = cfg["output_category_prefix"]

        dataframe = storage.read("dataframe")
        self._validate_dataframe(
            dataframe=dataframe,
            input_question_key=input_question_key,
            input_answer_key=input_answer_key,
            output_relevance_key=output_relevance_key,
            output_category_prefix=output_category_prefix,
        )

        prompts = self._build_prompts(
            dataframe=dataframe,
            input_question_key=input_question_key,
            input_answer_key=input_answer_key,
            categories_text=cfg["categories_text"],
        )

        self.logger.info(
            f"Start robotics relevance evaluation for {len(prompts)} samples "
            f"(question_key={input_question_key}, answer_key={input_answer_key})."
        )

        responses = self.llm_serving.generate_from_input(prompts)
        if len(responses) != len(dataframe):
            self.logger.warning(
                f"Number of responses ({len(responses)}) does not match number of rows ({len(dataframe)}). "
                f"Will align by index, extra items will be ignored."
            )

        relevances: List[float] = []
        parsed_categories_all: List[List[Dict[str, Any]]] = []

        for idx, (df_idx, row) in enumerate(dataframe.iterrows()):
            if idx >= len(responses):
                # 没有对应响应时用默认值填充
                relevances.append(0.0)
                parsed_categories_all.append([])
                continue

            raw_resp = responses[idx]
            try:
                parsed = self._parse_response(raw_resp)
                relevances.append(parsed["robotics_relevance"])
                parsed_categories_all.append(parsed["categories"])
            except Exception as e:
                self.logger.warning(
                    f"[RoboticsRelevanceSampleEvaluator] Failed to parse response for row {df_idx}: {e}. "
                    f"raw={repr(raw_resp)[:200]}"
                )
                relevances.append(0.0)
                parsed_categories_all.append([])

        dataframe[output_relevance_key] = relevances

        for i in range(self.max_categories):
            names: List[str] = []
            confs: List[float] = []
            for cats in parsed_categories_all:
                if i < len(cats):
                    names.append(cats[i]["category_name"])
                    confs.append(cats[i]["confidence"])
                else:
                    names.append("")
                    confs.append(0.0)
            dataframe[f"{output_category_prefix}{i+1}_name"] = names
            dataframe[f"{output_category_prefix}{i+1}_confidence"] = confs

        output_file = storage.write(dataframe)
        self.logger.info(
            f"Robotics relevance evaluation finished. Results saved to {output_file}. "
            f"New columns: {output_relevance_key}, "
            + ", ".join(
                [
                    f"{output_category_prefix}{i+1}_name/{output_category_prefix}{i+1}_confidence"
                    for i in range(self.max_categories)
                ]
            )
        )

        return [
            output_relevance_key,
            *[
                f"{output_category_prefix}{i+1}_name"
                for i in range(self.max_categories)
            ],
            *[
                f"{output_category_prefix}{i+1}_confidence"
                for i in range(self.max_categories)
            ],
        ]

