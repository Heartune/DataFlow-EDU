# -*- coding: utf-8 -*-
"""
DataFlow-EDU 主管线：命令行交互式选择并执行各 Workflow 步骤。

用户通过菜单选择要执行的算子，支持阶段一至阶段四的各步骤。
"""

import os
import sys

# 确保项目根目录在路径中
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# 优先使用本地 DataFlow 包（包含 get_logger、OperatorABC 等），避免使用 site-packages 中的其他 dataflow
_DATAFLOW_ROOT = os.path.join(_PROJECT_ROOT, "DataFlow")
if os.path.isdir(_DATAFLOW_ROOT) and _DATAFLOW_ROOT not in sys.path:
    sys.path.insert(0, _DATAFLOW_ROOT)

import dataflow_edu  # noqa: E402, F401
from dataflow_edu.config.loader import get_config_path, load_config
from dataflow_edu.config.manager_cli import run_config_manager
from dataflow_edu.config.schema import default_config
from dataflow_edu.operators import (  # noqa: E402
    AmbiguityCleaningOperator,
    AmbiguityRefinementOperator,
    BalancingOperator,
    DeduplicationOperator,
    DomainCleaningOperator,
    DomainRefinementOperator,
    MinerUOCROperator,
)
from dataflow_edu.pipelines import GenerationPipeline  # noqa: E402


def run_mineru_ocr():
    """阶段一 1.2：MinerU OCR Operator"""
    config = load_config(project_root=_PROJECT_ROOT)
    path = get_config_path(_PROJECT_ROOT)
    if not os.path.isfile(path):
        print("⚠ 配置文件不存在，使用内置 1.2 参数。可通过 1.1 配置并保存。")
        config = default_config()

    mp = config.operators.get("mineru_ocr")
    if not mp:
        mp = default_config().operators["mineru_ocr"]

    img_dir = mp.img_dir if os.path.isabs(mp.img_dir) else os.path.join(_PROJECT_ROOT, mp.img_dir)
    md_dir = mp.md_dir if os.path.isabs(mp.md_dir) else os.path.join(_PROJECT_ROOT, mp.md_dir)
    os.makedirs(md_dir, exist_ok=True)

    op = MinerUOCROperator(
        batch_size=mp.batch_size,
        poll_interval=mp.poll_interval,
        poll_timeout=mp.poll_timeout,
        skip_existing=mp.skip_existing,
        language=mp.language,
        enable_formula=mp.enable_formula,
        enable_table=mp.enable_table,
    )
    op.run(storage=None, img_dir=img_dir, md_dir=md_dir)


def run_generation():
    """阶段二 2.1：Generation Operator - 两阶段习题与答案生成"""
    config = load_config(project_root=_PROJECT_ROOT)
    path = get_config_path(_PROJECT_ROOT)
    if not os.path.isfile(path):
        print("⚠ 配置文件不存在，使用内置 2.1 参数。")
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


def run_ambiguity_cleaning():
    """阶段三 3.1：Ambiguity Cleaning Operator - 二义性检查与低质量样本剔除"""
    config = load_config(project_root=_PROJECT_ROOT)
    path = get_config_path(_PROJECT_ROOT)
    if not os.path.isfile(path):
        print("⚠ 配置文件不存在，使用内置 3.1 参数。")
        config = default_config()

    amb = config.operators.get("ambiguity_cleaning") or default_config().operators.get(
        "ambiguity_cleaning"
    )
    if amb is None:
        from dataflow_edu.config.schema import AmbiguityCleaningConfig

        amb = AmbiguityCleaningConfig()
    output_dir = amb.output_dir if os.path.isabs(amb.output_dir) else os.path.join(_PROJECT_ROOT, amb.output_dir)
    input_dir = amb.input_dir if os.path.isabs(amb.input_dir) else os.path.join(_PROJECT_ROOT, amb.input_dir)
    os.makedirs(output_dir, exist_ok=True)

    op = AmbiguityCleaningOperator(
        output_dir=output_dir,
        input_dir=input_dir,
        max_workers=getattr(amb, "max_workers", 8),
    )
    op.run(storage=None, output_dir=output_dir, input_dir=input_dir, config=config)


def run_ambiguity_refinement():
    """阶段三 3.2：Ambiguity Refinement Operator - 对中质量（2–3 分）题目优化二义性"""
    config = load_config(project_root=_PROJECT_ROOT)
    path = get_config_path(_PROJECT_ROOT)
    if not os.path.isfile(path):
        print("⚠ 配置文件不存在，使用内置 3.2 参数。")
        config = default_config()

    ref = config.operators.get("ambiguity_refinement") or default_config().operators.get(
        "ambiguity_refinement"
    )
    if ref is None:
        from dataflow_edu.config.schema import AmbiguityRefinementConfig

        ref = AmbiguityRefinementConfig()
    output_dir = ref.output_dir if os.path.isabs(ref.output_dir) else os.path.join(_PROJECT_ROOT, ref.output_dir)
    input_dir = ref.input_dir if os.path.isabs(ref.input_dir) else os.path.join(_PROJECT_ROOT, ref.input_dir)
    os.makedirs(output_dir, exist_ok=True)

    op = AmbiguityRefinementOperator(
        input_dir=input_dir,
        output_dir=output_dir,
        max_workers=getattr(ref, "max_workers", 8),
    )
    op.run(storage=None, input_dir=input_dir, output_dir=output_dir, config=config)


def run_domain_cleaning():
    """阶段三 3.3：Domain Cleaning Operator - 领域相关性检查与低质量样本剔除"""
    config = load_config(project_root=_PROJECT_ROOT)
    path = get_config_path(_PROJECT_ROOT)
    if not os.path.isfile(path):
        print("⚠ 配置文件不存在，使用内置 3.3 参数。")
        config = default_config()

    dom = config.operators.get("domain_cleaning") or default_config().operators.get(
        "domain_cleaning"
    )
    if dom is None:
        from dataflow_edu.config.schema import DomainCleaningConfig

        dom = DomainCleaningConfig()
    output_dir = dom.output_dir if os.path.isabs(dom.output_dir) else os.path.join(_PROJECT_ROOT, dom.output_dir)
    input_dir = dom.input_dir if os.path.isabs(dom.input_dir) else os.path.join(_PROJECT_ROOT, dom.input_dir)
    os.makedirs(output_dir, exist_ok=True)

    op = DomainCleaningOperator(
        input_dir=input_dir,
        output_dir=output_dir,
        max_workers=getattr(dom, "max_workers", 8),
    )
    op.run(storage=None, input_dir=input_dir, output_dir=output_dir, config=config)


def run_domain_refinement():
    """阶段三 3.4：Domain Refinement Operator - 对中质量（2–3 分）题目优化领域相关性"""
    config = load_config(project_root=_PROJECT_ROOT)
    path = get_config_path(_PROJECT_ROOT)
    if not os.path.isfile(path):
        print("⚠ 配置文件不存在，使用内置 3.4 参数。")
        config = default_config()

    ref = config.operators.get("domain_refinement") or default_config().operators.get(
        "domain_refinement"
    )
    if ref is None:
        from dataflow_edu.config.schema import DomainRefinementConfig

        ref = DomainRefinementConfig()
    output_dir = ref.output_dir if os.path.isabs(ref.output_dir) else os.path.join(_PROJECT_ROOT, ref.output_dir)
    input_dir = ref.input_dir if os.path.isabs(ref.input_dir) else os.path.join(_PROJECT_ROOT, ref.input_dir)
    os.makedirs(output_dir, exist_ok=True)

    op = DomainRefinementOperator(
        input_dir=input_dir,
        output_dir=output_dir,
        max_workers=getattr(ref, "max_workers", 8),
    )
    op.run(storage=None, input_dir=input_dir, output_dir=output_dir, config=config)


def run_deduplication():
    """阶段三 3.5：Deduplication Operator - 基于 MinHash + LSH 对题目题干去重"""
    config = load_config(project_root=_PROJECT_ROOT)
    path = get_config_path(_PROJECT_ROOT)
    if not os.path.isfile(path):
        print("⚠ 配置文件不存在，使用内置 3.5 参数。")
        config = default_config()

    dedup = config.operators.get("deduplication") or default_config().operators.get(
        "deduplication"
    )
    if dedup is None:
        from dataflow_edu.config.schema import DeduplicationConfig

        dedup = DeduplicationConfig()
    output_dir = dedup.output_dir if os.path.isabs(dedup.output_dir) else os.path.join(_PROJECT_ROOT, dedup.output_dir)
    input_dir = dedup.input_dir if os.path.isabs(dedup.input_dir) else os.path.join(_PROJECT_ROOT, dedup.input_dir)
    os.makedirs(output_dir, exist_ok=True)

    op = DeduplicationOperator(
        input_dir=input_dir,
        output_dir=output_dir,
        threshold=getattr(dedup, "threshold", 0.9),
        num_perm=getattr(dedup, "num_perm", 128),
        n_gram=getattr(dedup, "n_gram", 5),
    )
    op.run(storage=None, input_dir=input_dir, output_dir=output_dir, config=config)


def run_balancing():
    """阶段二 2.2：Balancing Operator - 能力子层级与题型分布均衡补题"""
    config = load_config(project_root=_PROJECT_ROOT)
    path = get_config_path(_PROJECT_ROOT)
    if not os.path.isfile(path):
        print("⚠ 配置文件不存在，使用内置 2.2 参数。")
        config = default_config()

    gen = config.operators.get("generation") or default_config().operators["generation"]
    output_dir = gen.output_dir if os.path.isabs(gen.output_dir) else os.path.join(_PROJECT_ROOT, gen.output_dir)
    md_dir = gen.md_dir if os.path.isabs(gen.md_dir) else os.path.join(_PROJECT_ROOT, gen.md_dir)
    os.makedirs(output_dir, exist_ok=True)

    op = BalancingOperator(output_dir=output_dir, md_dir=md_dir, max_workers=gen.max_workers)
    op.run(storage=None, output_dir=output_dir, md_dir=md_dir, config=config)


def _stub(name: str):
    """占位：尚未实现的算子"""
    print(f"\n⚠ [{name}] 尚未实现，敬请期待。\n")


def show_menu():
    """显示 Pipeline 步骤菜单"""
    print()
    print("=" * 60)
    print("  DataFlow-EDU Pipeline - 请选择要执行的步骤")
    print("=" * 60)
    print()
    print("【阶段一：Taxonomy & OCR 分类与OCR】")
    print("  1.1  Configuration Manager 配置管理")
    print("  1.2  MinerU OCR Operator 多模态OCR算子")
    print()
    print("【阶段二：Generation & Balancing 生成与均衡】")
    print("  2.1  Generation Operator 生成算子")
    print("  2.2  Balancing Operator 均衡算子")
    print()
    print("【阶段三：Cleaning & Refinement 清洗与精修】")
    print("  3.1  Ambiguity Cleaning Operator 二义性清洗算子")
    print("  3.2  Ambiguity Refinement Operator 二义性精修算子")
    print("  3.3  Domain Cleaning Operator 领域相关性清洗算子")
    print("  3.4  Domain Refinement Operator 领域相关性精修算子")
    print("  3.5  Deduplication Operator 去重算子")
    print("  3.6  Synthesis Operator 解析生成算子")
    print("  3.7  Translation Operator 翻译算子")
    print("  3.8  MCQ Verify Operator 选择题验证算子")
    print()
    print("【阶段四：Execute & Judge 执行与评估】")
    print("  4.1  Execute Operator 执行算子")
    print("  4.2  Judge Operator 评估算子")
    print()
    print("  0    退出 Exit")
    print("=" * 60)


def main():
    handlers = {
        "1.1": run_config_manager,
        "1.2": run_mineru_ocr,
        "2.1": run_generation,
        "2.2": run_balancing,
        "3.1": run_ambiguity_cleaning,
        "3.2": run_ambiguity_refinement,
        "3.3": run_domain_cleaning,
        "3.4": run_domain_refinement,
        "3.5": run_deduplication,
        "3.6": lambda: _stub("3.6 Synthesis"),
        "3.7": lambda: _stub("3.7 Translation"),
        "3.8": lambda: _stub("3.8 MCQ Verify"),
        "4.1": lambda: _stub("4.1 Execute Operator"),
        "4.2": lambda: _stub("4.2 Judge Operator"),
    }

    while True:
        show_menu()
        choice = input("请输入选项：").strip()
        if choice == "0":
            print("退出。")
            break
        if choice in handlers:
            try:
                handlers[choice]()
            except Exception as e:
                print(f"\n❌ 执行出错: {e}\n")
        else:
            print("\n⚠ 无效选项，请重新输入。\n")


if __name__ == "__main__":
    main()
