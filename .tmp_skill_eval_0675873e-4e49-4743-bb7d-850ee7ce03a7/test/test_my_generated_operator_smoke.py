import json
from pathlib import Path

from dataflow_ext_custom.operators.generate.my_generated_operator import MyGeneratedOperator

class _DummyLLM:
    def generate_from_input(self, user_inputs, system_prompt, json_schema=None):
        return [f"mock::{text}" for text in user_inputs]

from dataflow.utils.storage import FileStorage

def test_smoke_run_with_filestorage(tmp_path):
    input_path = tmp_path / "input.jsonl"
    input_path.write_text(json.dumps({"raw_content": "hello"}) + "\n", encoding="utf-8")

    storage = FileStorage(
        first_entry_file_name=str(input_path),
        cache_path=str(tmp_path),
        file_name_prefix="smoke_cache",
        cache_type="jsonl",
    )

    op = MyGeneratedOperator(llm_serving=_DummyLLM())

    op.run(storage=storage.step(), input_key="raw_content", output_key="generated_content")

    output_file = Path(tmp_path) / "smoke_cache_step1.jsonl"
    assert output_file.exists()
