"""
DataFlow-EDU: 学科数据集与评测基准生产管线扩展包

包含 MinerU OCR Operator 等教材解析与题库生成相关算子。
"""

import os
from pathlib import Path

# 供 WebUI 配置校验脚本使用：仅加载配置模块，跳过算子等重量级导入
if os.environ.get("DATAFLOW_EDU_CONFIG_ONLY"):
    __all__ = []
else:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")

    from dataflow_edu.operators.generation_operator import GenerationOperator
    from dataflow_edu.operators.mineru_ocr_operator import MinerUOCROperator

    __all__ = ["GenerationOperator", "MinerUOCROperator"]
