"""
一个简单的示例 Pipeline：

从 JSONL 文件中读取包含 question/answer 的数据，
调用 RoboticsRelevanceSampleEvaluator 对每条样本进行：
- 机器人学相关性打分
- 机器人学细分小类划分

运行前，你需要：
- 准备好一个 JSONL 文件，每行包含至少字段：question, answer
- 根据自己的环境配置 APILLMServing_request（或其他 LLMServing）
"""

import os

from dataflow.serving import APILLMServing_request
from dataflow.utils.storage import FileStorage
from dataflow.core import LLMServingABC
from dataflow.operators.reasoning.eval.robotics_relevance_sample_evaluator import (
    RoboticsRelevanceSampleEvaluator,
)


class RoboticsRelevancePipeline:
    def __init__(
        self,
        first_entry_file_name: str,
        cache_path: str,
        llm_serving: LLMServingABC,
    ):
        self.storage = FileStorage(
            first_entry_file_name=first_entry_file_name,
            cache_path=cache_path,
            file_name_prefix="robotics_relevance_step",
            cache_type="jsonl",
        )

        self.eval_step = RoboticsRelevanceSampleEvaluator(
            llm_serving=llm_serving,
            max_categories=3,
        )

    def forward(self):
        """
        仅包含一个算子步骤的最小闭环 Pipeline。
        """
        self.eval_step.run(storage=self.storage.step())


if __name__ == "__main__":
    # ===== 根据你的实际环境配置 LLM Serving =====
    llm_serving = APILLMServing_request(
        api_url="YOUR_LLM_API_URL",
        model_name="YOUR_MODEL_NAME",
        max_workers=8,
    )

    # ===== 输入/缓存路径示例（请按需修改） =====
    input_jsonl = "../example_data/core_text_data/bench_eval_data.jsonl"
    cache_dir = "../bench_result/robotics_relevance_demo"

    os.makedirs(cache_dir, exist_ok=True)

    pl = RoboticsRelevancePipeline(
        first_entry_file_name=input_jsonl,
        cache_path=cache_dir,
        llm_serving=llm_serving,
    )
    pl.forward()

