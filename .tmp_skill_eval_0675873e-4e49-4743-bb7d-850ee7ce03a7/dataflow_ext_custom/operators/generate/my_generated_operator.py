from dataflow import get_logger
from dataflow.core import LLMServingABC, OperatorABC
from dataflow.utils.registry import OPERATOR_REGISTRY
from dataflow.utils.storage import DataFlowStorage

@OPERATOR_REGISTRY.register()
class MyGeneratedOperator(OperatorABC):
    """Generated DataFlow operator scaffold (generate)."""

    def __init__(
        self,

        llm_serving: LLMServingABC,
        system_prompt: str = "You are a helpful data generation assistant.",

    ):
        super().__init__()
        self.logger = get_logger()

        self.llm_serving = llm_serving
        self.system_prompt = system_prompt

    @staticmethod
    def get_desc(lang: str = "zh"):
        if lang == "zh":
            return "MyGeneratedOperator：读取输入列并生成新内容，写入输出列。"
        if lang == "en":
            return "MyGeneratedOperator: read input column and generate new content into output column."
        return "Generate content from one column to another."

    def _generate_text(self, text: str) -> str:
        outputs = self.llm_serving.generate_from_input(
            user_inputs=[text],
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
        input_key: str = "raw_content",
        output_key: str = "generated_content",
    ):
        dataframe = storage.read("dataframe")
        if input_key not in dataframe.columns:
            raise KeyError(f"Missing input column: {input_key}")

        values = dataframe[input_key].fillna("").astype(str).tolist()
        outputs = []
        for value in values:

            outputs.append(self._generate_text(value))

        dataframe[output_key] = outputs
        storage.write(dataframe)
        return output_key
