import pandas as pd
import pytest

from dataflow_edu_ops.operators.generate.edu_synthesis_operator import EduSynthesisOperator


class _MemoryStorage:
    def __init__(self, dataframe: pd.DataFrame):
        self.dataframe = dataframe

    def read(self, output_type):
        assert output_type == "dataframe"
        return self.dataframe.copy()

    def write(self, data):
        self.dataframe = data.copy()
        return "ok"


class _DummyLLM:
    def generate_from_input(self, user_inputs, system_prompt, json_schema=None):
        return [f"mock::{text}" for text in user_inputs]


def _build_operator():
    return EduSynthesisOperator(llm_serving=_DummyLLM())


def test_run_adds_output_column():
    storage = _MemoryStorage(pd.DataFrame({
        "question": ["细胞膜的基本结构是什么？", "光合作用的产物有哪些？"],
        "answer": ["磷脂双分子层", "葡萄糖和氧气"],
        "type": ["简答题", "填空题"],
    }))
    op = _build_operator()

    out = op.run(storage=storage, input_key="question", output_key="analysis")

    assert out == "analysis"
    assert "analysis" in storage.dataframe.columns
    assert len(storage.dataframe) == 2


def test_run_raises_when_input_key_missing():
    storage = _MemoryStorage(pd.DataFrame({"other": ["x"]}))
    op = _build_operator()
    with pytest.raises(KeyError) as exc:
        op.run(storage=storage, input_key="question", output_key="analysis")

    message = str(exc.value)
    assert "Missing input column" in message
    assert "Available columns" in message


def test_run_works_without_optional_columns():
    # answer/type/options columns absent — operator should not crash
    storage = _MemoryStorage(pd.DataFrame({"question": ["What is ATP?"]}))
    op = _build_operator()

    out = op.run(storage=storage, input_key="question", output_key="analysis")

    assert out == "analysis"
    assert storage.dataframe.loc[0, "analysis"] != ""
