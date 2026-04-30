import argparse

from dataflow.utils.storage import FileStorage

from dataflow.serving import APILLMServing_request

from dataflow_edu_ops.operators.generate.edu_synthesis_operator import (
    EduSynthesisOperator,
    _DEFAULT_SYSTEM_PROMPT,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="CLI wrapper for EduSynthesisOperator: generate question analysis/explanation via LLM.",
    )
    parser.add_argument("--input", required=True, help="Path to input dataset file.")
    parser.add_argument("--input-key", default="question", help="Input column: question text.")
    parser.add_argument("--output-key", default="analysis", help="Output column: generated analysis.")
    parser.add_argument("--answer-key", default="answer", help="Column containing reference answers.")
    parser.add_argument("--type-key", default="type", help="Column containing question type.")
    parser.add_argument("--options-key", default="options", help="Column containing MCQ options (optional).")
    parser.add_argument("--cache-path", default="./cache", help="Cache directory for intermediate files.")
    parser.add_argument("--cache-prefix", default="edu_synthesis_operator", help="Output cache file prefix.")
    parser.add_argument(
        "--cache-type",
        default="jsonl",
        help="Cache file format: json, jsonl, csv, parquet, or pickle.",
    )
    # original: default="https://api.openai.com/v1/chat/completions"
    parser.add_argument("--api-url", default="https://api.bltcy.ai", help="LLM API URL.")
    # original: default="gpt-4o-mini"
    parser.add_argument("--model-name", default="gemini-3-flash-preview-nothinking", help="LLM model name.")
    parser.add_argument("--system-prompt", default=_DEFAULT_SYSTEM_PROMPT, help="System prompt for analysis generation.")
    parser.add_argument("--temperature", type=float, default=0.3, help="Sampling temperature for LLM.")
    return parser


def main() -> None:
    args = build_parser().parse_args()

    storage = FileStorage(
        first_entry_file_name=args.input,
        cache_path=args.cache_path,
        file_name_prefix=args.cache_prefix,
        cache_type=args.cache_type,
    )

    llm_serving = APILLMServing_request(
        api_url=args.api_url,
        model_name=args.model_name,
        temperature=args.temperature,
    )
    operator = EduSynthesisOperator(
        llm_serving=llm_serving,
        system_prompt=args.system_prompt,
    )

    result_key = operator.run(
        storage=storage.step(),
        input_key=args.input_key,
        output_key=args.output_key,
        answer_key=args.answer_key,
        type_key=args.type_key,
        options_key=args.options_key,
    )

    print(f"Done. output_key={result_key}")


if __name__ == "__main__":
    main()
