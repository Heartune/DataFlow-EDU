import json
from pathlib import Path

from dataflow_edu_ops.operators.generate.edu_socratic_hint_generator import EduSocraticHintGenerator

class _DummyLLM:
    def generate_from_input(self, user_inputs, system_prompt, json_schema=None):
        return [f"mock::{text}" for text in user_inputs]

from dataflow.utils.storage import FileStorage

def test_smoke_run_with_filestorage(tmp_path):
    input_path = tmp_path / "input.jsonl"
    input_path.write_text(json.dumps({"question": "hello"}) + "\n", encoding="utf-8")

    storage = FileStorage(
        first_entry_file_name=str(input_path),
        cache_path=str(tmp_path),
        file_name_prefix="smoke_cache",
        cache_type="jsonl",
    )

    op = EduSocraticHintGenerator(llm_serving=_DummyLLM())

    op.run(storage=storage.step(), input_key="question", output_key="socratic_hint")

    output_file = Path(tmp_path) / "smoke_cache_step1.jsonl"
    assert output_file.exists()
