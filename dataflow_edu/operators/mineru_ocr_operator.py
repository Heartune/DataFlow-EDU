# -*- coding: utf-8 -*-
"""
MinerU OCR Operator - 教材图片批量解析为 Markdown

沿用 textbook/img 目录结构，调用 MinerU 云服务 API，
将教材图片解析为标准化 Markdown 格式并落盘。
支持交互式选择教材（半自动 Pipeline，人工介入）。
"""

import os
import sys

from dataflow import get_logger
from dataflow.core import OperatorABC
from dataflow.utils.registry import OPERATOR_REGISTRY

# 将 utils_from_CNLaw-Bench 加入路径，以便导入 mineru_ocr
_OCR_MODULE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "utils_from_CNLaw-Bench",
)
if _OCR_MODULE_DIR not in sys.path:
    sys.path.insert(0, _OCR_MODULE_DIR)

import mineru_ocr  # noqa: E402


@OPERATOR_REGISTRY.register()
class MinerUOCROperator(OperatorABC):
    """
    教材图片批量解析算子：扫描 img_dir 下教材子目录，交互式选择后，
    调用 MinerU API 将图片转为 Markdown，保存到 md_dir。
    """

    def __init__(
        self,
        batch_size: int = 50,
        poll_interval: int = 5,
        poll_timeout: int = 600,
        skip_existing: bool = True,
        language: str = "ch",
        enable_formula: bool = True,
        enable_table: bool = True,
    ):
        super().__init__()
        self.logger = get_logger()
        self.batch_size = batch_size
        self.poll_interval = poll_interval
        self.poll_timeout = poll_timeout
        self.skip_existing = skip_existing
        self.language = language
        self.enable_formula = enable_formula
        self.enable_table = enable_table
        self.logger.info(
            f"Initializing {self.__class__.__name__} with batch_size={batch_size}, "
            f"skip_existing={skip_existing}"
        )

    @staticmethod
    def get_desc(lang: str = "zh"):
        if lang == "zh":
            return (
                "MinerU OCR Operator：批量输入教材图片，调用 MinerU 云服务 API，"
                "提取文本、表格和复杂图文对，输出标准化 Markdown 文件。\n\n"
                "输入形式：沿用 textbook/img 目录结构，算子接收 img_dir、md_dir 两个路径，"
                "自动扫描子目录（每本教材一个子目录，内含 png/jpg 图片）。\n\n"
                "输出形式：仅落盘 Markdown 到 md_dir，下游 Generation 算子自行读取目录。\n\n"
                "交互式：当 img_dir 下有多本教材时，run() 会提示用户输入编号选择，选完再处理。\n\n"
                "初始化参数（__init__）：\n"
                "- batch_size: 每批提交图片数量，默认 50\n"
                "- poll_interval: 轮询 MinerU 任务状态的间隔（秒），默认 5\n"
                "- poll_timeout: 轮询超时（秒），默认 600\n"
                "- skip_existing: 是否跳过已有 .md 的图片，默认 True\n"
                "- language: OCR 语言 (ch/en)，默认 ch\n"
                "- enable_formula: 是否启用公式识别，默认 True\n"
                "- enable_table: 是否启用表格识别，默认 True\n\n"
                "运行参数（run）：\n"
                "- storage: DataFlowStorage 或 None（本算子不读写 DataFrame）\n"
                "- img_dir: 教材图片根目录（含各教材子目录）\n"
                "- md_dir: 输出 Markdown 根目录"
            )
        elif lang == "en":
            return (
                "MinerU OCR Operator: Batch input of textbook images, calls MinerU cloud API "
                "to extract text, tables, and complex image-text pairs into standardized Markdown.\n\n"
                "Input: textbook/img directory structure; operator receives img_dir and md_dir.\n\n"
                "Output: Markdown files written to md_dir; downstream operators read the directory.\n\n"
                "Interactive: When multiple books exist, run() prompts user to select by index.\n\n"
                "__init__ params: batch_size, poll_interval, poll_timeout, skip_existing, "
                "language, enable_formula, enable_table\n\n"
                "run params: storage, img_dir, md_dir"
            )
        return "MinerU OCR Operator for textbook images to Markdown."

    def run(
        self,
        storage=None,
        img_dir: str = None,
        md_dir: str = None,
    ):
        """
        执行 MinerU 解析流程：扫描 -> 交互选择 -> 按批提交 -> 轮询 -> 保存结果。

        Args:
            storage: DataFlowStorage 或 None。本算子不读写 DataFrame，storage 可为占位。
            img_dir: 教材图片根目录（如 textbooks/img）
            md_dir: 输出 Markdown 根目录（如 textbooks/md）

        Returns:
            tuple: (total_success, total_fail) 成功/失败图片数量
        """
        if not img_dir or not md_dir:
            raise ValueError("img_dir 和 md_dir 为必填参数")

        if not os.path.isdir(img_dir):
            raise FileNotFoundError(f"目录不存在: {img_dir}")

        # 1. 扫描教材
        books = mineru_ocr.scan_textbooks(img_dir, md_dir)
        if not books:
            self.logger.warning("没有找到任何教材图片目录")
            return 0, 0

        self.logger.info(f"扫描到 {len(books)} 个教材")

        # 2. 交互式选择
        selected = mineru_ocr.interactive_select_textbooks(books)
        if not selected:
            self.logger.warning("用户未选择任何教材")
            return 0, 0

        self.logger.info(f"已选择 {len(selected)} 个教材")

        total_success = 0
        total_fail = 0

        # 3. 处理每个选中的教材
        for book_idx, (img_book_dir, md_book_dir) in enumerate(selected, 1):
            book_name = os.path.basename(img_book_dir)
            self.logger.info(f"处理教材 {book_idx}/{len(selected)}: {book_name}")

            pending_images = mineru_ocr.get_pending_images(
                img_book_dir, md_book_dir, skip_existing=self.skip_existing
            )
            if not pending_images:
                self.logger.info("  所有图片已处理，跳过")
                continue

            self.logger.info(f"  待处理图片: {len(pending_images)} 张")

            num_batches = (len(pending_images) + self.batch_size - 1) // self.batch_size

            for batch_idx in range(num_batches):
                batch_start = batch_idx * self.batch_size
                batch_end = min(batch_start + self.batch_size, len(pending_images))
                batch_images = pending_images[batch_start:batch_end]

                self.logger.info(f"  [{batch_idx + 1}/{num_batches}] 处理第 {batch_start + 1}-{batch_end} 张")

                # 提交任务
                submit_ret = mineru_ocr.submit_batch(
                    batch_images,
                    language=self.language,
                    enable_formula=self.enable_formula,
                    enable_table=self.enable_table,
                )
                if not submit_ret:
                    self.logger.error("  批次提交失败，跳过")
                    total_fail += len(batch_images)
                    continue

                batch_id, success_count = submit_ret

                # 轮询结果
                results = mineru_ocr.poll_batch(
                    batch_id,
                    interval=self.poll_interval,
                    timeout=self.poll_timeout,
                    expected_done_count=success_count,
                )
                if results is None:
                    self.logger.error("  任务查询失败，跳过")
                    total_fail += len(batch_images)
                    continue

                # 保存结果
                success, fail = mineru_ocr.save_results(
                    results, md_book_dir, image_paths=batch_images
                )
                total_success += success
                total_fail += fail

        self.logger.info(f"MinerU 解析完成: 成功 {total_success} 张, 失败 {total_fail} 张")
        return total_success, total_fail
