from dataflow import get_logger
from dataflow.core import LLMServingABC, OperatorABC
from dataflow.utils.registry import OPERATOR_REGISTRY
from dataflow.utils.storage import DataFlowStorage

@OPERATOR_REGISTRY.register()
class DifficultyRefinementOperator(OperatorABC):
    """Generated DataFlow operator scaffold (refine)."""

    def __init__(
        self,

        llm_serving: LLMServingABC,
        system_prompt: str = "Please refine the text and keep original meaning.",

    ):
        super().__init__()
        self.logger = get_logger()

        self.llm_serving = llm_serving
        self.system_prompt = system_prompt

    @staticmethod
    def get_desc(lang: str = "zh"):
        if lang == "zh":
            return "DifficultyRefinementOperator：对文本进行规范化与精修。"
        if lang == "en":
            return "DifficultyRefinementOperator: normalize and refine text content."
        return "Refine text in a stable and reproducible way."

    def _refine_text(self, text: str) -> str:
        outputs = self.llm_serving.generate_from_input(
            user_inputs=[text],
            system_prompt=self.system_prompt,
        )
        if isinstance(outputs, list) and outputs:
            return str(outputs[0]).strip()
        if isinstance(outputs, str):
            return outputs.strip()
        return text

    def run(
        self,
        storage: DataFlowStorage,
        input_key: str = "questions",
        output_key: str = "questions_refined",
        strip_spaces: bool = True,
    ):
        dataframe = storage.read("dataframe")
        if input_key not in dataframe.columns:
            available_columns = ", ".join(map(str, dataframe.columns.tolist())) or "<empty>"
            raise KeyError(f"Missing input column: {input_key}. Available columns: {available_columns}")

        values = dataframe[input_key].fillna("").astype(str).tolist()
        outputs = []
        for value in values:
            base = value.strip() if strip_spaces else value

            outputs.append(self._refine_text(base))

        dataframe[output_key] = outputs
        storage.write(dataframe)
        return output_key
