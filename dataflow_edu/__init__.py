"""
DataFlow-EDU: 学科数据集与评测基准生产管线扩展包

包含 MinerU Parsing Operator 等教材解析与题库生成相关算子。
"""

from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from dataflow_edu.operators.generation_operator import GenerationOperator
from dataflow_edu.operators.mineru_parsing_operator import MinerUParsingOperator

__all__ = ["GenerationOperator", "MinerUParsingOperator"]
