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
    MinerUOCRConfig,
    QuestionType,
    TaxonomyItem,
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
            "execute": {
                "input_dir": config.operators.get("execute", ExecuteConfig()).input_dir,
                "output_dir": config.operators.get("execute", ExecuteConfig()).output_dir,
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

    exec_defaults = ExecuteConfig()
    exec_op = d.get("operators", {}) or {}
    exec_op = exec_op.get("execute")
    if not isinstance(exec_op, dict):
        exec_op = {}
    exec_cfg = ExecuteConfig(
        input_dir=str(exec_op.get("input_dir", exec_defaults.input_dir)),
        output_dir=str(exec_op.get("output_dir", exec_defaults.output_dir)),
    )

    return EduConfig(
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
            "execute": exec_cfg,
        },
    )


def load_config(
    path: Optional[str] = None,
    project_root: Optional[str] = None,
) -> EduConfig:
    """加载配置，文件不存在时返回默认配置。"""
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
