# -*- coding: utf-8 -*-
"""Configuration Manager 交互式 CLI。"""

import os

from dataflow_edu.config.loader import get_config_path, load_config, save_config
from dataflow_edu.config.schema import (
    AbilityLevelItem,
    EduConfig,
    MinerUOCRConfig,
    QuestionType,
    TaxonomyItem,
    default_config,
)
from dataflow_edu.config.validator import validate_config

_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)


def _show_submenu():
    """显示 Configuration Manager 子菜单。"""
    print()
    print("-" * 50)
    print("  1.1 Configuration Manager")
    print("-" * 50)
    print("  1  查看当前配置")
    print("  2  管理评估层级（大类/小类）")
    print("  3  管理题型池")
    print("  4  管理能力层级")
    print("  5  管理 1.2 MinerU 参数")
    print("  6  校验并保存")
    print("  0  返回主菜单")
    print("-" * 50)


def _show_config(config: EduConfig):
    """打印当前配置概览。"""
    print("\n【评估层级 taxonomy】")
    for t in config.taxonomy:
        print(f"  - {t.name}: {t.subcategories}")
    print("\n【题型池 question_types】")
    for q in config.question_types:
        print(f"  - {q.name}: weight={q.weight}")
    print("\n【能力层级 ability_levels】")
    for a in config.ability_levels:
        sc = "、".join(a.sublevels) if a.sublevels else "（无）"
        print(f"  - {a.name}: weight={a.weight}, {sc}")
    print("\n【1.2 MinerU 参数】")
    mp = config.operators.get("mineru_ocr", MinerUOCRConfig())
    print(f"  img_dir: {mp.img_dir}")
    print(f"  md_dir: {mp.md_dir}")
    print(f"  batch_size: {mp.batch_size}, poll_interval: {mp.poll_interval}, poll_timeout: {mp.poll_timeout}")
    print(f"  skip_existing: {mp.skip_existing}, language: {mp.language}")
    print(f"  enable_formula: {mp.enable_formula}, enable_table: {mp.enable_table}")
    print()


def _manage_taxonomy(config: EduConfig) -> EduConfig:
    """管理 taxonomy：增删改大类与小类。"""
    while True:
        print("\n【管理评估层级】")
        for i, t in enumerate(config.taxonomy, 1):
            print(f"  {i}. {t.name} -> {t.subcategories}")
        print("  a  添加大类")
        print("  e N  编辑第 N 个大类")
        print("  d N  删除第 N 个大类")
        print("  s N  管理第 N 个大类下的小类")
        print("  0  返回")
        choice = input("请选择: ").strip().lower()
        if choice == "0":
            break
        if choice == "a":
            name = input("  大类名称: ").strip()
            if name:
                sub_str = input("  小类列表（逗号分隔）: ").strip()
                subcategories = [s.strip() for s in sub_str.split(",") if s.strip()]
                config.taxonomy.append(TaxonomyItem(name=name, subcategories=subcategories))
                print("  已添加。")
        elif choice.startswith("e "):
            try:
                idx = int(choice[2:].strip())
                if 1 <= idx <= len(config.taxonomy):
                    t = config.taxonomy[idx - 1]
                    new_name = input(f"  新名称 [{t.name}]: ").strip() or t.name
                    sub_str = input(f"  小类列表（逗号分隔）[{','.join(t.subcategories)}]: ").strip()
                    subcategories = [s.strip() for s in sub_str.split(",") if s.strip()] if sub_str else t.subcategories
                    config.taxonomy[idx - 1] = TaxonomyItem(name=new_name, subcategories=subcategories)
                    print("  已更新。")
            except ValueError:
                print("  无效序号。")
        elif choice.startswith("d "):
            try:
                idx = int(choice[2:].strip())
                if 1 <= idx <= len(config.taxonomy):
                    config.taxonomy.pop(idx - 1)
                    print("  已删除。")
            except ValueError:
                print("  无效序号。")
        elif choice.startswith("s "):
            try:
                idx = int(choice[2:].strip())
                if 1 <= idx <= len(config.taxonomy):
                    t = config.taxonomy[idx - 1]
                    print(f"  当前小类: {t.subcategories}")
                    print("  a 添加 | e N 编辑 | d N 删除 | 0 返回")
                    sub_choice = input("  请选择: ").strip().lower()
                    if sub_choice == "0":
                        pass
                    elif sub_choice == "a":
                        sub = input("  小类名称: ").strip()
                        if sub:
                            t.subcategories.append(sub)
                            print("  已添加。")
                    elif sub_choice.startswith("e "):
                        ni = int(sub_choice[2:].strip())
                        if 1 <= ni <= len(t.subcategories):
                            new_sub = input(f"  新名称 [{t.subcategories[ni - 1]}]: ").strip()
                            if new_sub:
                                t.subcategories[ni - 1] = new_sub
                                print("  已更新。")
                    elif sub_choice.startswith("d "):
                        ni = int(sub_choice[2:].strip())
                        if 1 <= ni <= len(t.subcategories):
                            t.subcategories.pop(ni - 1)
                            print("  已删除。")
            except ValueError:
                print("  无效序号。")
    return config


def _manage_question_types(config: EduConfig) -> EduConfig:
    """管理题型池：增删改题型及权重。"""
    while True:
        print("\n【管理题型池】")
        for i, q in enumerate(config.question_types, 1):
            print(f"  {i}. {q.name} weight={q.weight}")
        print("  a  添加题型")
        print("  e N  编辑第 N 个题型")
        print("  d N  删除第 N 个题型")
        print("  0  返回")
        choice = input("请选择: ").strip().lower()
        if choice == "0":
            break
        if choice == "a":
            name = input("  题型名称: ").strip()
            if name:
                try:
                    w = float(input("  权重 (0~1): ").strip() or "0.25")
                    config.question_types.append(QuestionType(name=name, weight=w))
                    print("  已添加。")
                except ValueError:
                    print("  权重需为数字。")
        elif choice.startswith("e "):
            try:
                idx = int(choice[2:].strip())
                if 1 <= idx <= len(config.question_types):
                    q = config.question_types[idx - 1]
                    new_name = input(f"  新名称 [{q.name}]: ").strip() or q.name
                    w_str = input(f"  权重 [{q.weight}]: ").strip()
                    w = float(w_str) if w_str else q.weight
                    config.question_types[idx - 1] = QuestionType(name=new_name, weight=w)
                    print("  已更新。")
            except (ValueError, IndexError):
                print("  无效输入。")
        elif choice.startswith("d "):
            try:
                idx = int(choice[2:].strip())
                if 1 <= idx <= len(config.question_types):
                    config.question_types.pop(idx - 1)
                    print("  已删除。")
            except ValueError:
                print("  无效序号。")
    return config


def _manage_ability_levels(config: EduConfig) -> EduConfig:
    """管理能力层级：增删改能力层级及其子层级。"""
    while True:
        print("\n【管理能力层级】")
        for i, a in enumerate(config.ability_levels, 1):
            sc = "、".join(a.sublevels) if a.sublevels else "（无）"
            print(f"  {i}. {a.name} weight={a.weight} -> {sc}")
        print("  a  添加能力层级")
        print("  e N  编辑第 N 个能力层级")
        print("  d N  删除第 N 个能力层级")
        print("  s N  管理第 N 个子层级")
        print("  0  返回")
        choice = input("请选择: ").strip().lower()
        if choice == "0":
            break
        if choice == "a":
            name = input("  能力层级名称: ").strip()
            if name:
                desc = input("  描述（用于 Prompt，可留空）: ").strip()
                w_str = input("  权重 (0~1，等分可留空) [0.25]: ").strip()
                weight = float(w_str) if w_str else 0.25
                sub_str = input("  子层级列表（逗号分隔）: ").strip()
                sublevels = [s.strip() for s in sub_str.split(",") if s.strip()]
                config.ability_levels.append(
                    AbilityLevelItem(name=name, description=desc, sublevels=sublevels, weight=weight)
                )
                print("  已添加。")
        elif choice.startswith("e "):
            try:
                idx = int(choice[2:].strip())
                if 1 <= idx <= len(config.ability_levels):
                    a = config.ability_levels[idx - 1]
                    new_name = input(f"  新名称 [{a.name}]: ").strip() or a.name
                    new_desc = input(f"  描述（回车保留）: ").strip()
                    desc = new_desc if new_desc else a.description
                    w_str = input(f"  权重 (0~1) [{a.weight}]: ").strip()
                    weight = float(w_str) if w_str else a.weight
                    sub_str = input(f"  子层级列表（逗号分隔）[{','.join(a.sublevels)}]: ").strip()
                    sublevels = [s.strip() for s in sub_str.split(",") if s.strip()] if sub_str else a.sublevels
                    config.ability_levels[idx - 1] = AbilityLevelItem(name=new_name, description=desc, sublevels=sublevels, weight=weight)
                    print("  已更新。")
            except ValueError:
                print("  无效序号。")
        elif choice.startswith("d "):
            try:
                idx = int(choice[2:].strip())
                if 1 <= idx <= len(config.ability_levels):
                    config.ability_levels.pop(idx - 1)
                    print("  已删除。")
            except ValueError:
                print("  无效序号。")
        elif choice.startswith("s "):
            try:
                idx = int(choice[2:].strip())
                if 1 <= idx <= len(config.ability_levels):
                    a = config.ability_levels[idx - 1]
                    print(f"  当前子层级: {a.sublevels}")
                    print("  a 添加 | e N 编辑 | d N 删除 | 0 返回")
                    sub_choice = input("  请选择: ").strip().lower()
                    if sub_choice == "0":
                        pass
                    elif sub_choice == "a":
                        sub = input("  子层级名称: ").strip()
                        if sub:
                            a.sublevels.append(sub)
                            print("  已添加。")
                    elif sub_choice.startswith("e "):
                        ni = int(sub_choice[2:].strip())
                        if 1 <= ni <= len(a.sublevels):
                            new_sub = input(f"  新名称 [{a.sublevels[ni - 1]}]: ").strip()
                            if new_sub:
                                a.sublevels[ni - 1] = new_sub
                                print("  已更新。")
                    elif sub_choice.startswith("d "):
                        ni = int(sub_choice[2:].strip())
                        if 1 <= ni <= len(a.sublevels):
                            a.sublevels.pop(ni - 1)
                            print("  已删除。")
            except ValueError:
                print("  无效序号。")
    return config


def _manage_mineru_params(config: EduConfig) -> EduConfig:
    """管理 1.2 MinerU 参数。"""
    mp = config.operators.get("mineru_ocr", MinerUOCRConfig())
    if "mineru_ocr" not in config.operators:
        config.operators["mineru_ocr"] = mp

    print("\n【管理 1.2 MinerU 参数】")
    img_dir = input(f"  img_dir [{mp.img_dir}]: ").strip()
    if img_dir:
        mp.img_dir = img_dir
    md_dir = input(f"  md_dir [{mp.md_dir}]: ").strip()
    if md_dir:
        mp.md_dir = md_dir
    bs = input(f"  batch_size [{mp.batch_size}]: ").strip()
    if bs:
        try:
            mp.batch_size = int(bs)
        except ValueError:
            print("  无效数字，已忽略。")
    pi = input(f"  poll_interval [{mp.poll_interval}]: ").strip()
    if pi:
        try:
            mp.poll_interval = int(pi)
        except ValueError:
            print("  无效数字，已忽略。")
    pt = input(f"  poll_timeout [{mp.poll_timeout}]: ").strip()
    if pt:
        try:
            mp.poll_timeout = int(pt)
        except ValueError:
            print("  无效数字，已忽略。")
    se = input(f"  skip_existing (y/n) [{mp.skip_existing}]: ").strip().lower()
    if se in ("y", "yes", "1", "true"):
        mp.skip_existing = True
    elif se in ("n", "no", "0", "false"):
        mp.skip_existing = False
    lang = input(f"  language (ch/en) [{mp.language}]: ").strip().lower()
    if lang in ("ch", "en"):
        mp.language = lang
    ef = input(f"  enable_formula (y/n) [{mp.enable_formula}]: ").strip().lower()
    if ef in ("y", "yes", "1", "true"):
        mp.enable_formula = True
    elif ef in ("n", "no", "0", "false"):
        mp.enable_formula = False
    et = input(f"  enable_table (y/n) [{mp.enable_table}]: ").strip().lower()
    if et in ("y", "yes", "1", "true"):
        mp.enable_table = True
    elif et in ("n", "no", "0", "false"):
        mp.enable_table = False
    print("  已更新。")
    return config


def _validate_and_save(config: EduConfig) -> EduConfig:
    """校验配置并保存。"""
    is_valid, errors = validate_config(config, project_root=_PROJECT_ROOT, check_paths=False)
    if not is_valid:
        print("\n❌ 校验失败：")
        for e in errors:
            print(f"  - {e}")
        print("  请修正后再保存。")
        return config
    path = get_config_path(_PROJECT_ROOT)
    save_config(config, path=path, project_root=_PROJECT_ROOT)
    print(f"\n✅ 配置已保存到 {path}\n")
    return config


def run_config_manager():
    """运行 Configuration Manager 主循环。"""
    path = get_config_path(_PROJECT_ROOT)
    if not os.path.isfile(path):
        print("\n⚠ 配置文件不存在，使用内置配置。可直接编辑 YAML 或通过菜单配置后保存。")
        config = default_config()
    else:
        config = load_config(path=path, project_root=_PROJECT_ROOT)

    while True:
        _show_submenu()
        choice = input("请选择: ").strip()
        if choice == "0":
            print("返回主菜单。")
            break
        if choice == "1":
            _show_config(config)
        elif choice == "2":
            config = _manage_taxonomy(config)
        elif choice == "3":
            config = _manage_question_types(config)
        elif choice == "4":
            config = _manage_ability_levels(config)
        elif choice == "5":
            config = _manage_mineru_params(config)
        elif choice == "6":
            config = _validate_and_save(config)
        else:
            print("无效选项。")
