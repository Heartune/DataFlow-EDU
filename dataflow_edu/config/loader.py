# -*- coding: utf-8 -*-
"""配置加载与保存（YAML）。"""

import os
from typing import Optional

import yaml

from dataflow_edu.config.schema import (
    AbilityLevelItem,
    AmbiguityCleaningConfig,
    AmbiguityRefinementConfig,
    BalancingConfig,
    DeduplicationConfig,
    DomainCleaningConfig,
    DomainRefinementConfig,
    EduConfig,
    ExecuteConfig,
    GenerationConfig,
    JudgeConfig,
    MCQVerifyConfig,
    MinerUOCRConfig,
    QuestionType,
    SynthesisConfig,
    TaxonomyItem,
    TranslationConfig,
    default_config,
)


def get_config_path(project_root: Optional[str] = None) -> str:
    """获取配置文件默认路径。"""
    if project_root is None:
        project_root = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
    return os.path.join(project_root, "dataflow_edu", "config", "edu_config.yaml")


def _config_to_dict(config: EduConfig) -> dict:
    """将 EduConfig 转为可序列化的 dict。"""
    return {
        "subject": config.subject,
        "grade": config.grade,
        "default_difficulty_distribution": dict(config.default_difficulty_distribution or {}),
        "taxonomy": [
            {"name": t.name, "subcategories": t.subcategories}
            for t in config.taxonomy
        ],
        "question_types": [
            {"name": q.name, "weight": q.weight}
            for q in config.question_types
        ],
        "ability_levels": [
            {"name": a.name, "weight": a.weight, "description": a.description, "sublevels": a.sublevels}
            for a in config.ability_levels
        ],
        "operators": {
            "mineru_ocr": {
                "img_dir": config.operators.get("mineru_ocr", MinerUOCRConfig()).img_dir,
                "md_dir": config.operators.get("mineru_ocr", MinerUOCRConfig()).md_dir,
                "batch_size": config.operators.get("mineru_ocr", MinerUOCRConfig()).batch_size,
                "poll_interval": config.operators.get("mineru_ocr", MinerUOCRConfig()).poll_interval,
                "poll_timeout": config.operators.get("mineru_ocr", MinerUOCRConfig()).poll_timeout,
                "skip_existing": config.operators.get("mineru_ocr", MinerUOCRConfig()).skip_existing,
                "language": config.operators.get("mineru_ocr", MinerUOCRConfig()).language,
                "enable_formula": config.operators.get("mineru_ocr", MinerUOCRConfig()).enable_formula,
                "enable_table": config.operators.get("mineru_ocr", MinerUOCRConfig()).enable_table,
            },
            "generation": {
                "md_dir": config.operators.get("generation", GenerationConfig()).md_dir,
                "output_dir": config.operators.get("generation", GenerationConfig()).output_dir,
                "questions_per_pair": config.operators.get("generation", GenerationConfig()).questions_per_pair,
                "max_workers": config.operators.get("generation", GenerationConfig()).max_workers,
                "api_delay": config.operators.get("generation", GenerationConfig()).api_delay,
                "request_timeout": config.operators.get("generation", GenerationConfig()).request_timeout,
                "max_retries": config.operators.get("generation", GenerationConfig()).max_retries,
                "save_interval": config.operators.get("generation", GenerationConfig()).save_interval,
            },
            "balancing": {
                "output_dir": config.operators.get("balancing", BalancingConfig()).output_dir,
                "sample_size": config.operators.get("balancing", BalancingConfig()).sample_size,
                "max_iterations": config.operators.get("balancing", BalancingConfig()).max_iterations,
                "questions_per_round": config.operators.get("balancing", BalancingConfig()).questions_per_round,
                "max_per_sublevel_iterations": config.operators.get("balancing", BalancingConfig()).max_per_sublevel_iterations,
                "tolerance": config.operators.get("balancing", BalancingConfig()).tolerance,
                "excluded_ability_sublevels": config.operators.get("balancing", BalancingConfig()).excluded_ability_sublevels,
            },
            "ambiguity_cleaning": {
                "output_dir": config.operators.get("ambiguity_cleaning", AmbiguityCleaningConfig()).output_dir,
                "input_dir": config.operators.get("ambiguity_cleaning", AmbiguityCleaningConfig()).input_dir,
                "max_workers": config.operators.get("ambiguity_cleaning", AmbiguityCleaningConfig()).max_workers,
                "max_retries": config.operators.get("ambiguity_cleaning", AmbiguityCleaningConfig()).max_retries,
                "threshold_remove": config.operators.get("ambiguity_cleaning", AmbiguityCleaningConfig()).threshold_remove,
            },
            "ambiguity_refinement": {
                "input_dir": config.operators.get("ambiguity_refinement", AmbiguityRefinementConfig()).input_dir,
                "output_dir": config.operators.get("ambiguity_refinement", AmbiguityRefinementConfig()).output_dir,
                "max_workers": config.operators.get("ambiguity_refinement", AmbiguityRefinementConfig()).max_workers,
                "max_retries": config.operators.get("ambiguity_refinement", AmbiguityRefinementConfig()).max_retries,
                "target_scores": config.operators.get("ambiguity_refinement", AmbiguityRefinementConfig()).target_scores,
            },
            "domain_cleaning": {
                "input_dir": config.operators.get("domain_cleaning", DomainCleaningConfig()).input_dir,
                "output_dir": config.operators.get("domain_cleaning", DomainCleaningConfig()).output_dir,
                "max_workers": config.operators.get("domain_cleaning", DomainCleaningConfig()).max_workers,
                "max_retries": config.operators.get("domain_cleaning", DomainCleaningConfig()).max_retries,
                "threshold_remove": config.operators.get("domain_cleaning", DomainCleaningConfig()).threshold_remove,
                "domain_name": config.operators.get("domain_cleaning", DomainCleaningConfig()).domain_name,
            },
            "domain_refinement": {
                "input_dir": config.operators.get("domain_refinement", DomainRefinementConfig()).input_dir,
                "output_dir": config.operators.get("domain_refinement", DomainRefinementConfig()).output_dir,
                "max_workers": config.operators.get("domain_refinement", DomainRefinementConfig()).max_workers,
                "max_retries": config.operators.get("domain_refinement", DomainRefinementConfig()).max_retries,
                "target_scores": config.operators.get("domain_refinement", DomainRefinementConfig()).target_scores,
                "domain_name": config.operators.get("domain_refinement", DomainRefinementConfig()).domain_name,
            },
            "deduplication": {
                "input_dir": config.operators.get("deduplication", DeduplicationConfig()).input_dir,
                "output_dir": config.operators.get("deduplication", DeduplicationConfig()).output_dir,
                "threshold": config.operators.get("deduplication", DeduplicationConfig()).threshold,
                "num_perm": config.operators.get("deduplication", DeduplicationConfig()).num_perm,
                "n_gram": config.operators.get("deduplication", DeduplicationConfig()).n_gram,
            },
            "synthesis": {
                "input_dir": config.operators.get("synthesis", SynthesisConfig()).input_dir,
                "output_dir": config.operators.get("synthesis", SynthesisConfig()).output_dir,
                "max_workers": config.operators.get("synthesis", SynthesisConfig()).max_workers,
                "max_retries": config.operators.get("synthesis", SynthesisConfig()).max_retries,
                "max_tokens": config.operators.get("synthesis", SynthesisConfig()).max_tokens,
                "temperature": config.operators.get("synthesis", SynthesisConfig()).temperature,
                "skip_existing": config.operators.get("synthesis", SynthesisConfig()).skip_existing,
            },
            "translation": {
                "input_dir": config.operators.get("translation", TranslationConfig()).input_dir,
                "output_dir": config.operators.get("translation", TranslationConfig()).output_dir,
                "target_languages": config.operators.get("translation", TranslationConfig()).target_languages,
                "translate_fields": config.operators.get("translation", TranslationConfig()).translate_fields,
                "max_workers": config.operators.get("translation", TranslationConfig()).max_workers,
                "max_retries": config.operators.get("translation", TranslationConfig()).max_retries,
                "residual_pattern_zh": config.operators.get("translation", TranslationConfig()).residual_pattern_zh,
                "fix_french_option_letter": config.operators.get("translation", TranslationConfig()).fix_french_option_letter,
            },
            "mcq_verify": {
                "input_dir": config.operators.get("mcq_verify", MCQVerifyConfig()).input_dir,
                "output_dir": config.operators.get("mcq_verify", MCQVerifyConfig()).output_dir,
                "target_languages": config.operators.get("mcq_verify", MCQVerifyConfig()).target_languages,
                "max_workers": config.operators.get("mcq_verify", MCQVerifyConfig()).max_workers,
                "max_retries": config.operators.get("mcq_verify", MCQVerifyConfig()).max_retries,
                "max_tokens": config.operators.get("mcq_verify", MCQVerifyConfig()).max_tokens,
                "temperature": config.operators.get("mcq_verify", MCQVerifyConfig()).temperature,
            },
            "execute": {
                "input_dir": config.operators.get("execute", ExecuteConfig()).input_dir,
                "output_dir": config.operators.get("execute", ExecuteConfig()).output_dir,
            },
            "judge": {
                "input_dir": config.operators.get("judge", JudgeConfig()).input_dir,
                "output_dir": config.operators.get("judge", JudgeConfig()).output_dir,
            },
        },
    }


def _dict_to_config(d: dict, project_root: Optional[str] = None) -> EduConfig:
    """将 dict 转为 EduConfig。"""
    if project_root is None:
        project_root = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )

    taxonomy = [
        TaxonomyItem(
            name=item.get("name", ""),
            subcategories=item.get("subcategories", []),
        )
        for item in d.get("taxonomy", [])
    ]

    question_types = [
        QuestionType(
            name=q.get("name", ""),
            weight=float(q.get("weight", 0.25)),
        )
        for q in d.get("question_types", [])
    ]

    ability_levels = [
        AbilityLevelItem(
            name=item.get("name", ""),
            description=str(item.get("description", "")),
            sublevels=item.get("sublevels", []),
            weight=float(item.get("weight", 0.25)),
        )
        for item in d.get("ability_levels", [])
    ]

    mp_defaults = MinerUOCRConfig()
    ops = d.get("operators", {}) or {}
    mp_op = ops.get("mineru_ocr") or ops.get("mineru_parsing", {})
    mp = MinerUOCRConfig(
        img_dir=mp_op.get("img_dir", mp_defaults.img_dir),
        md_dir=mp_op.get("md_dir", mp_defaults.md_dir),
        batch_size=int(mp_op.get("batch_size", mp_defaults.batch_size)),
        poll_interval=int(mp_op.get("poll_interval", mp_defaults.poll_interval)),
        poll_timeout=int(mp_op.get("poll_timeout", mp_defaults.poll_timeout)),
        skip_existing=bool(mp_op.get("skip_existing", mp_defaults.skip_existing)),
        language=str(mp_op.get("language", mp_defaults.language)),
        enable_formula=bool(mp_op.get("enable_formula", mp_defaults.enable_formula)),
        enable_table=bool(mp_op.get("enable_table", mp_defaults.enable_table)),
    )

    gen_defaults = GenerationConfig()
    gen_op = d.get("operators", {}).get("generation", {})
    gen = GenerationConfig(
        md_dir=str(gen_op.get("md_dir", gen_defaults.md_dir)),
        output_dir=str(gen_op.get("output_dir", gen_defaults.output_dir)),
        questions_per_pair=int(gen_op.get("questions_per_pair", gen_defaults.questions_per_pair)),
        max_workers=int(gen_op.get("max_workers", gen_defaults.max_workers)),
        api_delay=float(gen_op.get("api_delay", gen_defaults.api_delay)),
        request_timeout=int(gen_op.get("request_timeout", gen_defaults.request_timeout)),
        max_retries=int(gen_op.get("max_retries", gen_defaults.max_retries)),
        save_interval=int(gen_op.get("save_interval", gen_defaults.save_interval)),
    )

    bal_defaults = BalancingConfig()
    bal_op = d.get("operators", {}) or {}
    bal_op = bal_op.get("balancing")
    if not isinstance(bal_op, dict):
        bal_op = {}
    bal = BalancingConfig(
        output_dir=str(bal_op.get("output_dir", bal_defaults.output_dir)),
        sample_size=int(bal_op.get("sample_size", bal_defaults.sample_size)),
        max_iterations=int(bal_op.get("max_iterations", bal_defaults.max_iterations)),
        questions_per_round=int(bal_op.get("questions_per_round", bal_defaults.questions_per_round)),
        max_per_sublevel_iterations=int(bal_op.get("max_per_sublevel_iterations", bal_defaults.max_per_sublevel_iterations)),
        tolerance=float(bal_op.get("tolerance", bal_defaults.tolerance)),
        excluded_ability_sublevels=list(bal_op.get("excluded_ability_sublevels", bal_defaults.excluded_ability_sublevels)),
    )

    amb_defaults = AmbiguityCleaningConfig()
    amb_op = d.get("operators", {}) or {}
    amb_op = amb_op.get("ambiguity_cleaning")
    if not isinstance(amb_op, dict):
        amb_op = {}
    amb = AmbiguityCleaningConfig(
        output_dir=str(amb_op.get("output_dir", amb_defaults.output_dir)),
        input_dir=str(amb_op.get("input_dir", amb_defaults.input_dir)),
        max_workers=int(amb_op.get("max_workers", amb_defaults.max_workers)),
        max_retries=int(amb_op.get("max_retries", amb_defaults.max_retries)),
        threshold_remove=int(amb_op.get("threshold_remove", amb_defaults.threshold_remove)),
    )

    ref_defaults = AmbiguityRefinementConfig()
    ref_op = d.get("operators", {}) or {}
    ref_op = ref_op.get("ambiguity_refinement")
    if not isinstance(ref_op, dict):
        ref_op = {}
    raw_target_scores = ref_op.get("target_scores", ref_defaults.target_scores)
    target_scores_list = [int(x) for x in raw_target_scores] if isinstance(raw_target_scores, (list, tuple)) else [2, 3]
    ref = AmbiguityRefinementConfig(
        input_dir=str(ref_op.get("input_dir", ref_defaults.input_dir)),
        output_dir=str(ref_op.get("output_dir", ref_defaults.output_dir)),
        max_workers=int(ref_op.get("max_workers", ref_defaults.max_workers)),
        max_retries=int(ref_op.get("max_retries", ref_defaults.max_retries)),
        target_scores=target_scores_list,
    )

    dom_defaults = DomainCleaningConfig()
    dom_op = d.get("operators", {}) or {}
    dom_op = dom_op.get("domain_cleaning")
    if not isinstance(dom_op, dict):
        dom_op = {}
    dom = DomainCleaningConfig(
        input_dir=str(dom_op.get("input_dir", dom_defaults.input_dir)),
        output_dir=str(dom_op.get("output_dir", dom_defaults.output_dir)),
        max_workers=int(dom_op.get("max_workers", dom_defaults.max_workers)),
        max_retries=int(dom_op.get("max_retries", dom_defaults.max_retries)),
        threshold_remove=int(dom_op.get("threshold_remove", dom_defaults.threshold_remove)),
        domain_name=str(dom_op.get("domain_name", dom_defaults.domain_name)),
    )

    domref_defaults = DomainRefinementConfig()
    domref_op = d.get("operators", {}) or {}
    domref_op = domref_op.get("domain_refinement")
    if not isinstance(domref_op, dict):
        domref_op = {}
    raw_domref_target = domref_op.get("target_scores", domref_defaults.target_scores)
    domref_target_list = [int(x) for x in raw_domref_target] if isinstance(raw_domref_target, (list, tuple)) else [2, 3]
    domref = DomainRefinementConfig(
        input_dir=str(domref_op.get("input_dir", domref_defaults.input_dir)),
        output_dir=str(domref_op.get("output_dir", domref_defaults.output_dir)),
        max_workers=int(domref_op.get("max_workers", domref_defaults.max_workers)),
        max_retries=int(domref_op.get("max_retries", domref_defaults.max_retries)),
        target_scores=domref_target_list,
        domain_name=str(domref_op.get("domain_name", domref_defaults.domain_name)),
    )

    dedup_defaults = DeduplicationConfig()
    dedup_op = d.get("operators", {}) or {}
    dedup_op = dedup_op.get("deduplication")
    if not isinstance(dedup_op, dict):
        dedup_op = {}
    dedup = DeduplicationConfig(
        input_dir=str(dedup_op.get("input_dir", dedup_defaults.input_dir)),
        output_dir=str(dedup_op.get("output_dir", dedup_defaults.output_dir)),
        threshold=float(dedup_op.get("threshold", dedup_defaults.threshold)),
        num_perm=int(dedup_op.get("num_perm", dedup_defaults.num_perm)),
        n_gram=int(dedup_op.get("n_gram", dedup_defaults.n_gram)),
    )

    synth_defaults = SynthesisConfig()
    synth_op = d.get("operators", {}) or {}
    synth_op = synth_op.get("synthesis")
    if not isinstance(synth_op, dict):
        synth_op = {}
    synth = SynthesisConfig(
        input_dir=str(synth_op.get("input_dir", synth_defaults.input_dir)),
        output_dir=str(synth_op.get("output_dir", synth_defaults.output_dir)),
        max_workers=int(synth_op.get("max_workers", synth_defaults.max_workers)),
        max_retries=int(synth_op.get("max_retries", synth_defaults.max_retries)),
        max_tokens=int(synth_op.get("max_tokens", synth_defaults.max_tokens)),
        temperature=float(synth_op.get("temperature", synth_defaults.temperature)),
        skip_existing=bool(synth_op.get("skip_existing", synth_defaults.skip_existing)),
    )

    trans_defaults = TranslationConfig()
    trans_op = d.get("operators", {}) or {}
    trans_op = trans_op.get("translation")
    if not isinstance(trans_op, dict):
        trans_op = {}
    raw_target_langs = trans_op.get("target_languages", trans_defaults.target_languages)
    target_langs = [str(x) for x in raw_target_langs] if isinstance(raw_target_langs, (list, tuple)) else list(trans_defaults.target_languages)
    raw_trans_fields = trans_op.get("translate_fields", trans_defaults.translate_fields)
    trans_fields = [str(x) for x in raw_trans_fields] if isinstance(raw_trans_fields, (list, tuple)) else list(trans_defaults.translate_fields)
    trans = TranslationConfig(
        input_dir=str(trans_op.get("input_dir", trans_defaults.input_dir)),
        output_dir=str(trans_op.get("output_dir", trans_defaults.output_dir)),
        target_languages=target_langs,
        translate_fields=trans_fields,
        max_workers=int(trans_op.get("max_workers", trans_defaults.max_workers)),
        max_retries=int(trans_op.get("max_retries", trans_defaults.max_retries)),
        residual_pattern_zh=bool(trans_op.get("residual_pattern_zh", trans_defaults.residual_pattern_zh)),
        fix_french_option_letter=bool(trans_op.get("fix_french_option_letter", trans_defaults.fix_french_option_letter)),
    )

    mcq_defaults = MCQVerifyConfig()
    mcq_op = d.get("operators", {}) or {}
    mcq_op = mcq_op.get("mcq_verify")
    if not isinstance(mcq_op, dict):
        mcq_op = {}
    raw_mcq_langs = mcq_op.get("target_languages", mcq_defaults.target_languages)
    mcq_langs = (
        [str(x) for x in raw_mcq_langs]
        if isinstance(raw_mcq_langs, (list, tuple))
        else list(mcq_defaults.target_languages)
    )
    mcq_cfg = MCQVerifyConfig(
        input_dir=str(mcq_op.get("input_dir", mcq_defaults.input_dir)),
        output_dir=str(mcq_op.get("output_dir", mcq_defaults.output_dir)),
        target_languages=mcq_langs,
        max_workers=int(mcq_op.get("max_workers", mcq_defaults.max_workers)),
        max_retries=int(mcq_op.get("max_retries", mcq_defaults.max_retries)),
        max_tokens=int(mcq_op.get("max_tokens", mcq_defaults.max_tokens)),
        temperature=float(mcq_op.get("temperature", mcq_defaults.temperature)),
    )

    exec_defaults = ExecuteConfig()
    exec_op = d.get("operators", {}) or {}
    exec_op = exec_op.get("execute")
    if not isinstance(exec_op, dict):
        exec_op = {}
    exec_cfg = ExecuteConfig(
        input_dir=str(exec_op.get("input_dir", exec_defaults.input_dir)),
        output_dir=str(exec_op.get("output_dir", exec_defaults.output_dir)),
    )

    judge_defaults = JudgeConfig()
    judge_op = d.get("operators", {}) or {}
    judge_op = judge_op.get("judge")
    if not isinstance(judge_op, dict):
        judge_op = {}
    judge_cfg = JudgeConfig(
        input_dir=str(judge_op.get("input_dir", judge_defaults.input_dir)),
        output_dir=str(judge_op.get("output_dir", judge_defaults.output_dir)),
    )

    raw_diff = d.get("default_difficulty_distribution")
    if isinstance(raw_diff, dict):
        diff_dist = {str(k): float(v) for k, v in raw_diff.items()}
    else:
        diff_dist = {"易": 0.3, "中": 0.5, "难": 0.2}

    return EduConfig(
        subject=str(d.get("subject", "") or ""),
        grade=str(d.get("grade", "") or ""),
        default_difficulty_distribution=diff_dist,
        taxonomy=taxonomy,
        question_types=question_types,
        ability_levels=ability_levels,
        operators={
            "mineru_ocr": mp,
            "generation": gen,
            "balancing": bal,
            "ambiguity_cleaning": amb,
            "ambiguity_refinement": ref,
            "domain_cleaning": dom,
            "domain_refinement": domref,
            "deduplication": dedup,
            "synthesis": synth,
            "translation": trans,
            "mcq_verify": mcq_cfg,
            "execute": exec_cfg,
            "judge": judge_cfg,
        },
    )


def load_config(
    path: Optional[str] = None,
    project_root: Optional[str] = None,
    strict: bool = False,
) -> EduConfig:
    """加载配置，文件不存在时返回默认配置。

    Args:
        path: 配置文件路径，None 则使用全局默认路径。
        project_root: 项目根目录，用于解析相对路径。
        strict: 默认 False 时遇到 YAML 解析错误等异常会静默回退到 default_config()；
            设为 True 时异常会向上抛出，便于调用方区分「文件存在但损坏」和
            「文件正常」两种情况，从而决定是否走自己的 fallback 链。
            注意：文件不存在 / 内容为空 始终返回 default_config()，不受 strict 影响。
    """
    if path is None:
        path = get_config_path(project_root)
    if not os.path.isfile(path):
        return default_config()
    try:
        with open(path, "r", encoding="utf-8") as f:
            d = yaml.safe_load(f)
        if d is None:
            return default_config()
        return _dict_to_config(d, project_root)
    except Exception:
        if strict:
            raise
        return default_config()


def save_config(
    config: EduConfig,
    path: Optional[str] = None,
    project_root: Optional[str] = None,
) -> None:
    """保存配置到 YAML。"""
    if path is None:
        path = get_config_path(project_root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    d = _config_to_dict(config)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(
            d,
            f,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
        )
