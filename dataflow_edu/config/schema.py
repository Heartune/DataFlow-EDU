# -*- coding: utf-8 -*-
"""DataFlow-EDU 配置 Schema 定义。"""

from dataclasses import dataclass, field
from typing import List


@dataclass
class TaxonomyItem:
    """评估层级：大类及其小类列表。"""

    name: str
    subcategories: List[str] = field(default_factory=list)


@dataclass
class QuestionType:
    """题型：名称 + 权重（用于后续 Balancing）。"""

    name: str
    weight: float = 0.25


@dataclass
class AbilityLevelItem:
    """考察能力层级：名称、描述、子层级（双层架构）及权重（用于 Generation 分布控制）。"""

    name: str
    description: str = ""
    sublevels: List[str] = field(default_factory=list)
    weight: float = 0.25


@dataclass
class MinerUOCRConfig:
    """1.2 MinerU OCR Operator 参数。"""

    img_dir: str = "dataflow_edu/data/resources/img"
    md_dir: str = "dataflow_edu/data/resources/md"
    batch_size: int = 50
    poll_interval: int = 5
    poll_timeout: int = 600
    skip_existing: bool = True
    language: str = "ch"
    enable_formula: bool = True
    enable_table: bool = True


@dataclass
class GenerationConfig:
    """2.1 Generation Operator 参数。"""

    md_dir: str = "dataflow_edu/data/resources/md"
    output_dir: str = "dataflow_edu/data/generation_and_balancing"
    questions_per_pair: int = 5
    max_workers: int = 8
    api_delay: float = 0.3
    request_timeout: int = 120
    max_retries: int = 3
    save_interval: int = 5


@dataclass
class BalancingConfig:
    """2.2 Balancing Operator 参数。"""

    output_dir: str = "dataflow_edu/data/generation_and_balancing"
    sample_size: int = 32
    max_iterations: int = 30
    questions_per_round: int = 10
    max_per_sublevel_iterations: int = 2
    tolerance: float = 0.03
    excluded_ability_sublevels: List[str] = field(default_factory=list)


@dataclass
class AmbiguityCleaningConfig:
    """3.1 Ambiguity Cleaning Operator 参数。"""

    output_dir: str = "dataflow_edu/data/cleaning_and_refinement/3_1_ambiguity_cleaned"
    input_dir: str = "dataflow_edu/data/generation_and_balancing/2_2_balanced"
    max_workers: int = 8
    max_retries: int = 3
    threshold_remove: int = 1  # 1 分剔除


@dataclass
class AmbiguityRefinementConfig:
    """3.2 Ambiguity Refinement Operator 参数。"""

    input_dir: str = "dataflow_edu/data/cleaning_and_refinement/3_1_ambiguity_cleaned"
    output_dir: str = "dataflow_edu/data/cleaning_and_refinement/3_2_ambiguity_refined"
    max_workers: int = 8
    max_retries: int = 3
    target_scores: List[int] = field(default_factory=lambda: [2, 3])  # 2–3 分题做 LLM 优化
    threshold_discard: int = 2  # 精修后重评，≤此分丢弃（与 ambiguity cleaning 一致）


@dataclass
class DomainCleaningConfig:
    """3.3 Domain Cleaning Operator 参数。"""

    input_dir: str = "dataflow_edu/data/cleaning_and_refinement/3_2_ambiguity_refined"
    output_dir: str = "dataflow_edu/data/cleaning_and_refinement/3_3_domain_cleaned"
    max_workers: int = 8
    max_retries: int = 3
    threshold_remove: int = 1  # 1 分剔除
    domain_name: str = "生物学"


@dataclass
class DomainRefinementConfig:
    """3.4 Domain Refinement Operator 参数。"""

    input_dir: str = "dataflow_edu/data/cleaning_and_refinement/3_3_domain_cleaned"
    output_dir: str = "dataflow_edu/data/cleaning_and_refinement/3_4_domain_refined"
    max_workers: int = 8
    max_retries: int = 3
    target_scores: List[int] = field(default_factory=lambda: [2, 3])  # 2–3 分题做 LLM 优化
    threshold_discard: int = 1  # 精修后重评，≤此分丢弃（与 domain cleaning 一致）
    domain_name: str = "生物学"


@dataclass
class DeduplicationConfig:
    """3.5 Deduplication Operator 参数。"""

    input_dir: str = "dataflow_edu/data/cleaning_and_refinement/3_4_domain_refined"
    output_dir: str = "dataflow_edu/data/cleaning_and_refinement/3_5_deduplicated"
    threshold: float = 0.9  # MinHash 相似度阈值
    num_perm: int = 128  # MinHash 排列数
    n_gram: int = 5  # 字符级 n-gram 大小


@dataclass
class SynthesisConfig:
    """3.6 Synthesis Operator 参数：基于 question + answer 生成 explanation 字段。"""

    input_dir: str = "dataflow_edu/data/cleaning_and_refinement/3_5_deduplicated"
    output_dir: str = "dataflow_edu/data/cleaning_and_refinement/3_6_synthesized"
    max_workers: int = 8
    max_retries: int = 3
    max_tokens: int = 2000
    temperature: float = 0.3
    skip_existing: bool = True  # 默认跳过已有 explanation 的题目


@dataclass
class TranslationConfig:
    """3.7 Translation Operator 参数：默认翻译 question/answer/explanation/options 到英、法。"""

    input_dir: str = "dataflow_edu/data/cleaning_and_refinement/3_6_synthesized"
    output_dir: str = "dataflow_edu/data/cleaning_and_refinement/3_7_translated"
    target_languages: List[str] = field(default_factory=lambda: ["en", "fr"])
    translate_fields: List[str] = field(
        default_factory=lambda: ["question", "answer", "output", "explanation", "options"]
    )
    max_workers: int = 8
    max_retries: int = 3
    residual_pattern_zh: bool = True  # 任意中文字符 [\u4e00-\u9fff] 即视为残留
    fix_french_option_letter: bool = True  # 法语翻译完成后做 bé/bê → B 修复


@dataclass
class MCQVerifyConfig:
    """3.8 MCQ Verify Operator 参数：选择题结构校验 + LLM 修复（补选项/规范答案字母）。"""

    input_dir: str = "dataflow_edu/data/cleaning_and_refinement/3_7_translated"
    output_dir: str = "dataflow_edu/data/cleaning_and_refinement/3_8_mcq_verified"
    target_languages: List[str] = field(default_factory=lambda: ["zh", "en", "fr"])
    max_workers: int = 8
    max_retries: int = 3
    max_tokens: int = 2000
    temperature: float = 0.3


@dataclass
class ExecuteConfig:
    """4.1 Execute Operator 参数。"""

    input_dir: str = "dataflow_edu/data/cleaning_and_refinement/3_5_deduplicated"
    output_dir: str = "dataflow_edu/data/execute_and_judge/4_1_executed"


@dataclass
class JudgeConfig:
    """4.2 Judge Operator 参数。"""

    input_dir: str = "dataflow_edu/data/execute_and_judge/4_1_executed"
    output_dir: str = "dataflow_edu/data/execute_and_judge/4_2_judged"


@dataclass
class EduConfig:
    """DataFlow-EDU 完整配置。"""

    taxonomy: List[TaxonomyItem] = field(default_factory=list)
    question_types: List[QuestionType] = field(default_factory=list)
    ability_levels: List[AbilityLevelItem] = field(default_factory=list)
    operators: dict = field(default_factory=dict)  # {"mineru_ocr": MinerUOCRConfig}


def default_config() -> EduConfig:
    """生成默认配置（含示例 taxonomy、题型、能力层级、1.2 参数）。"""
    return EduConfig(
        taxonomy=[
            TaxonomyItem(name="生物竞赛", subcategories=["遗传学", "细胞生物学", "生态学"]),
            TaxonomyItem(name="化学竞赛", subcategories=["有机化学", "无机化学"]),
        ],
        question_types=[
            QuestionType(name="单选题", weight=0.3),
            QuestionType(name="多选题", weight=0.2),
            QuestionType(name="计算题", weight=0.3),
            QuestionType(name="简答题", weight=0.2),
        ],
        ability_levels=[
            AbilityLevelItem(
                name="生命观念",
                description="对观察到的生命现象及相互关系或特性进行解释后的抽象，是经过实证后的想法或观点，是能够理解或解释相关事件和现象的品格和能力",
                sublevels=["结构与功能观", "物质与能量观", "稳态与平衡观", "进化与适应观"],
                weight=0.25,
            ),
            AbilityLevelItem(
                name="理性思维",
                description="尊重事实和证据，崇尚严谨和务实的求知态度，运用科学的思维方法认识事物、解决实际问题的思维习惯和思维能力",
                sublevels=["归纳与概括", "演绎与推理", "模型与建模", "批判性思维"],
                weight=0.25,
            ),
            AbilityLevelItem(
                name="科学探究",
                description="能发现现实世界中的生物学问题，针对特定的生物学现象，进行观察、提问、实验设计、方案实施以及结果的交流与讨论的能力",
                sublevels=["提出问题与假设", "设计实验方案", "实施与观察", "分析与交流"],
                weight=0.25,
            ),
            AbilityLevelItem(
                name="社会责任",
                description="基于生物学的认识，参与个人与社会事务的讨论，作出理性解释和判断，尝试解决生产生活中的生物学问题的担当和能力",
                sublevels=["参与社会事务讨论", "理性判断与解释", "参与环境保护", "健康生活倡导"],
                weight=0.25,
            ),
        ],
        operators={
            "mineru_ocr": MinerUOCRConfig(),
            "generation": GenerationConfig(),
            "balancing": BalancingConfig(),
            "ambiguity_cleaning": AmbiguityCleaningConfig(),
            "ambiguity_refinement": AmbiguityRefinementConfig(),
            "domain_cleaning": DomainCleaningConfig(),
            "domain_refinement": DomainRefinementConfig(),
            "deduplication": DeduplicationConfig(),
            "synthesis": SynthesisConfig(),
            "translation": TranslationConfig(),
            "mcq_verify": MCQVerifyConfig(),
            "execute": ExecuteConfig(),
            "judge": JudgeConfig(),
        },
    )
