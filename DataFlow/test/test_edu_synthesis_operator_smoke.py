import json
from pathlib import Path

from dataflow_edu_ops.operators.generate.edu_synthesis_operator import EduSynthesisOperator

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

    op = EduSynthesisOperator(llm_serving=_DummyLLM())

    result_key = op.run(storage=storage.step(), input_key="question", output_key="analysis")

    assert result_key in {"analysis", None}

    output_file = Path(tmp_path) / "smoke_cache_step1.jsonl"
    assert output_file.exists()

    lines = [line for line in output_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert lines, "Smoke output file should not be empty"

    first_record = json.loads(lines[0])
    assert "analysis" in first_record
