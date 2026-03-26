from dataflow import get_logger
from dataflow.core import LLMServingABC, OperatorABC
from dataflow.utils.registry import OPERATOR_REGISTRY
from dataflow.utils.storage import DataFlowStorage

_DEFAULT_SYSTEM_PROMPT = (
    "你是一位专业的教育内容编辑。请根据提供的题目和参考答案，生成一段清晰、准确、有教学价值的题目解析。"
    "解析应包含：解题思路、关键知识点说明、步骤推导（如适用）。"
    "不要重复题干，直接输出解析正文，语言与题目保持一致。"
)


@OPERATOR_REGISTRY.register()
class EduSynthesisOperator(OperatorABC):
    """3.6 Synthesis Operator：为题目生成详细解析。"""

    def __init__(
        self,
        llm_serving: LLMServingABC,
        system_prompt: str = _DEFAULT_SYSTEM_PROMPT,
    ):
        super().__init__()
        self.logger = get_logger()
        self.llm_serving = llm_serving
        self.system_prompt = system_prompt

    @staticmethod
    def get_desc(lang: str = "zh"):
        if lang == "zh":
            return "3.6 EduSynthesisOperator：读取题目、答案及题型，调用 LLM 生成题目解析，写入 analysis 列。"
        if lang == "en":
            return "3.6 EduSynthesisOperator: read question/answer/type columns, generate explanation via LLM into analysis column."
        return "Generate educational question explanations using LLM."

    def _build_user_prompt(
        self,
        question: str,
        answer: str,
        question_type: str,
        options: str,
    ) -> str:
        parts = []
        if question_type:
            parts.append(f"【题型】{question_type}")
        parts.append(f"【题目】{question}")
        if options:
            parts.append(f"【选项】{options}")
        parts.append(f"【参考答案】{answer}")
        parts.append("\n请根据以上信息，生成一段详细的题目解析。")
        return "\n".join(parts)

    def _generate_analysis(self, user_prompt: str) -> str:
        outputs = self.llm_serving.generate_from_input(
            user_inputs=[user_prompt],
            system_prompt=self.system_prompt,
        )
        if isinstance(outputs, list) and outputs:
            return str(outputs[0]).strip()
        if isinstance(outputs, str):
            return outputs.strip()
        return ""

    def run(
        self,
        storage: DataFlowStorage,
        input_key: str = "question",
        output_key: str = "analysis",
        answer_key: str = "answer",
        type_key: str = "type",
        options_key: str = "options",
    ):
        dataframe = storage.read("dataframe")
        if input_key not in dataframe.columns:
            available_columns = ", ".join(map(str, dataframe.columns.tolist())) or "<empty>"
            raise KeyError(f"Missing input column: {input_key}. Available columns: {available_columns}")

        questions = dataframe[input_key].fillna("").astype(str).tolist()
        answers = dataframe[answer_key].fillna("").astype(str).tolist() if answer_key in dataframe.columns else [""] * len(questions)
        types = dataframe[type_key].fillna("").astype(str).tolist() if type_key in dataframe.columns else [""] * len(questions)
        options_list = dataframe[options_key].fillna("").astype(str).tolist() if options_key in dataframe.columns else [""] * len(questions)

        outputs = []
        for question, answer, q_type, options in zip(questions, answers, types, options_list):
            user_prompt = self._build_user_prompt(
                question=question,
                answer=answer,
                question_type=q_type,
                options=options,
            )
            outputs.append(self._generate_analysis(user_prompt))

        dataframe[output_key] = outputs
        storage.write(dataframe)
        return output_key
