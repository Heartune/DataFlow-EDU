import argparse

from dataflow.utils.storage import FileStorage

from dataflow.serving import APILLMServing_request

from dataflow_edu_ops.operators.generate.edu_socratic_hint_generator import EduSocraticHintGenerator

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CLI wrapper for EduSocraticHintGenerator")
    parser.add_argument("--input", required=True, help="Input file path")
    parser.add_argument("--input-key", default="question", help="Input column name")
    parser.add_argument("--output-key", default="socratic_hint", help="Output column name")
    parser.add_argument("--cache-path", default="./cache", help="Cache directory")
    parser.add_argument("--cache-prefix", default="edu_socratic_hint_generator", help="Cache file prefix")
    parser.add_argument("--cache-type", default="jsonl", help="Cache type: json/jsonl/csv/parquet/pickle")

    parser.add_argument("--api-url", default="https://api.openai.com/v1/chat/completions", help="LLM API URL")
    parser.add_argument("--model-name", default="gpt-4o-mini", help="LLM model name")
    parser.add_argument(
        "--system-prompt",
        default=(
            "You are an educational tutor. Given a student's question, provide a short "
            "Socratic hint in the same language. Do not provide the final answer. "
            "Guide with one or two questions or a single next-step clue."
        ),
        help="System prompt for Socratic hint generation",
    )
    parser.add_argument("--temperature", type=float, default=0.2, help="Sampling temperature for LLM")

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
    operator = EduSocraticHintGenerator(
        llm_serving=llm_serving,
        system_prompt=args.system_prompt,
    )

    result_key = operator.run(
        storage=storage.step(),
        input_key=args.input_key,
        output_key=args.output_key,
    )

    print(f"Done. output_key={result_key}")

if __name__ == "__main__":
    main()
