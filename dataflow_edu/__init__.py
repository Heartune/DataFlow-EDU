"""
DataFlow-EDU: 学科数据集与评测基准生产管线扩展包

包含 MinerU OCR Operator 等教材解析与题库生成相关算子。
"""

from pathlib import Path

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")

__all__ = ["GenerationOperator", "MinerUOCROperator"]


def __getattr__(name):
    if name == "GenerationOperator":
        from dataflow_edu.operators.generation_operator import GenerationOperator

        return GenerationOperator
    if name == "MinerUOCROperator":
        from dataflow_edu.operators.mineru_ocr_operator import MinerUOCROperator

        return MinerUOCROperator
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
