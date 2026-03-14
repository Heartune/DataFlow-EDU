"""
Generation Pipeline - 2.1 题目生成

串联 GenerationOperator，从 MinerU 解析后的 Markdown 进行两阶段习题生成。
半自动：运行时会交互式选择教材、配置 API、选择阶段。
"""

import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

_DATAFLOW_ROOT = os.path.join(_PROJECT_ROOT, "DataFlow")
if os.path.isdir(_DATAFLOW_ROOT) and _DATAFLOW_ROOT not in sys.path:
    sys.path.insert(0, _DATAFLOW_ROOT)

import dataflow_edu  # noqa: E402, F401
from dataflow_edu.config.loader import get_config_path, load_config  # noqa: E402
from dataflow_edu.config.schema import default_config  # noqa: E402
from dataflow_edu.operators import GenerationOperator  # noqa: E402


class GenerationPipeline:
    """2.1 Generation Pipeline：包装 GenerationOperator，两阶段题目生成。"""

    def __init__(self, md_dir: str, output_dir: str, **operator_kwargs):
        self.md_dir = md_dir
        self.output_dir = output_dir
        self.operator = GenerationOperator(
            md_dir=md_dir,
            output_dir=output_dir,
            **operator_kwargs,
        )

    def forward(self):
        """执行 Generation 流程（交互式选教材、API 配置、阶段执行）。"""
        self.operator.run(storage=None, md_dir=self.md_dir, output_dir=self.output_dir)


if __name__ == "__main__":
    config = load_config(project_root=_PROJECT_ROOT)
    path = get_config_path(_PROJECT_ROOT)
    if not os.path.isfile(path):
        config = default_config()

    gen = config.operators.get("generation") or default_config().operators["generation"]
    md_dir = gen.md_dir if os.path.isabs(gen.md_dir) else os.path.join(_PROJECT_ROOT, gen.md_dir)
    output_dir = gen.output_dir if os.path.isabs(gen.output_dir) else os.path.join(_PROJECT_ROOT, gen.output_dir)
    os.makedirs(output_dir, exist_ok=True)

    pl = GenerationPipeline(
        md_dir=md_dir,
        output_dir=output_dir,
        questions_per_pair=gen.questions_per_pair,
        max_workers=gen.max_workers,
    )
    pl.forward()
