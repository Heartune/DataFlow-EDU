"""
MinerU OCR Pipeline - 最小示例

展示如何串联 MinerUOCROperator，对教材图片进行批量 OCR 转 Markdown。
本 Pipeline 为半自动：运行时会交互式选择要处理的教材。

运行前需要：
- 准备 textbook/img 目录结构：img_dir 下每个子目录为一本教材，内含 png/jpg 图片
- 指定 md_dir 作为 Markdown 输出目录
- 确保 MinerU API Key 可用（见 utils_from_CNLaw-Bench/mineru_ocr.py）
"""

import os
import sys

# 确保项目根目录在路径中，以便导入 dataflow_edu
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# 导入 dataflow_edu 以触发算子注册
import dataflow_edu  # noqa: E402, F401
from dataflow_edu.operators import MinerUOCROperator  # noqa: E402


class MinerUOCRPipeline:
    """仅包含 MinerU OCR 算子的最小 Pipeline。"""

    def __init__(self, img_dir: str, md_dir: str, **operator_kwargs):
        self.img_dir = img_dir
        self.md_dir = md_dir
        self.operator = MinerUOCROperator(**operator_kwargs)

    def forward(self):
        """执行 MinerU 解析（含交互式选择教材）。"""
        self.operator.run(storage=None, img_dir=self.img_dir, md_dir=self.md_dir)


if __name__ == "__main__":
    # ===== 请根据实际路径修改 =====
    img_dir = os.path.join(_PROJECT_ROOT, "utils_from_CNLaw-Bench", "textbooks", "img")
    md_dir = os.path.join(_PROJECT_ROOT, "utils_from_CNLaw-Bench", "textbooks", "md")

    os.makedirs(md_dir, exist_ok=True)

    pl = MinerUOCRPipeline(
        img_dir=img_dir,
        md_dir=md_dir,
        batch_size=50,
        skip_existing=True,
    )
    pl.forward()
