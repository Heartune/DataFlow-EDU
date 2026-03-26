import pandas as pd
import pytest

from custom_operators.operators.refine.difficulty_refinement_operator import DifficultyRefinementOperator

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

    return DifficultyRefinementOperator(llm_serving=_DummyLLM())

def test_run_writes_output_and_expected_row_count():
    storage = _MemoryStorage(pd.DataFrame({"questions": ["alpha", ""]}))
    op = _build_operator()

    out = op.run(storage=storage, input_key="questions", output_key="questions_refined")
    assert out == "questions_refined"
    assert "questions_refined" in storage.dataframe.columns
    assert len(storage.dataframe) == 2

def test_run_raises_when_input_key_missing():
    storage = _MemoryStorage(pd.DataFrame({"other": ["x"]}))
    op = _build_operator()
    with pytest.raises(KeyError) as exc:

        op.run(storage=storage, input_key="questions", output_key="questions_refined")

    message = str(exc.value)
    assert "Missing input column" in message
    assert "Available columns" in message
