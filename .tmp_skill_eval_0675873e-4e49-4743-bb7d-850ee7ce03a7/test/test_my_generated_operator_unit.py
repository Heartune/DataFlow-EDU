import pandas as pd
import pytest

from dataflow_ext_custom.operators.generate.my_generated_operator import MyGeneratedOperator

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

    return MyGeneratedOperator(llm_serving=_DummyLLM())

def test_run_adds_output_column():
    storage = _MemoryStorage(pd.DataFrame({"raw_content": ["a", "b"]}))
    op = _build_operator()

    out = op.run(storage=storage, input_key="raw_content", output_key="generated_content")

    assert out == "generated_content"
    assert "generated_content" in storage.dataframe.columns

def test_run_raises_when_input_key_missing():
    storage = _MemoryStorage(pd.DataFrame({"other": ["x"]}))
    op = _build_operator()
    with pytest.raises(KeyError):

        op.run(storage=storage, input_key="raw_content", output_key="generated_content")

