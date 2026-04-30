import argparse

from dataflow.utils.storage import FileStorage

from dataflow.serving import APILLMServing_request

from custom_operators.operators.refine.difficulty_refinement_operator import DifficultyRefinementOperator

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run DifficultyRefinementOperator on a DataFlow dataset.",
    )
    parser.add_argument("--input", required=True, help="Path to input dataset file.")
    parser.add_argument("--input-key", default="questions", help="Input column name.")
    parser.add_argument("--output-key", default="questions_refined", help="Output column name.")
    parser.add_argument("--cache-path", default="./cache", help="Cache directory for intermediate files.")
    parser.add_argument("--cache-prefix", default="difficulty_refinement_operator", help="Output cache file prefix.")
    parser.add_argument(
        "--cache-type",
        default="jsonl",
        help="Cache file format: json, jsonl, csv, parquet, or pickle.",
    )

    # original: default="https://api.openai.com/v1/chat/completions"
    parser.add_argument("--api-url", default="https://api.bltcy.ai", help="LLM API URL.")
    # original: default="gpt-4o-mini"
    parser.add_argument("--model-name", default="gemini-3-flash-preview-nothinking", help="LLM model name.")

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
    )
    operator = DifficultyRefinementOperator(llm_serving=llm_serving)

    result_key = operator.run(
        storage=storage.step(),
        input_key=args.input_key,
        output_key=args.output_key,
    )

    print(f"Done. output_key={result_key}")

if __name__ == "__main__":
    main()
