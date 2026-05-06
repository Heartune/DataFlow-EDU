# -*- coding: utf-8 -*-
"""
3.7 Translation 核心逻辑：默认中→英 / 中→法翻译，含残留中文重翻。

参考：
- utils_from_ROBOTheory/翻译/trans（通用版）.py：首次翻译的 prompt 与并发框架
- utils_from_ROBOTheory/翻译/retranslate_chinese_content.py：残留中文检测与重翻

所有 LLM 调用统一通过 dataflow_edu.serving.call_llm，不引入豆包/dashscope 直连。
"""

import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple

from dataflow_edu._compat.tqdm import tqdm

from dataflow_edu.serving import call_llm, get_api_delay

PROGRESS_SUFFIX = "_translation_progress.json"
FAILED_SUFFIX = "_translation_failed.json"

LANG_NAMES = {
    "en": "英语",
    "fr": "法语",
}

# 选项字母前缀正则：A./A、A) 等
OPTION_LETTER_PATTERN = re.compile(r"^\s*([A-Z])\s*[\.\)、:：]\s*", re.UNICODE)
CHINESE_PATTERN = re.compile(r"[\u4e00-\u9fff]")
FRENCH_BE_PATTERN = re.compile(r"\bb[éê]\b", flags=re.IGNORECASE)


def contains_chinese(text: Any) -> bool:
    """检测文本是否包含中文字符。"""
    if text is None:
        return False
    if not isinstance(text, str):
        text = str(text)
    return bool(CHINESE_PATTERN.search(text))


def fix_french_option(text: Any) -> Any:
    """修复法语翻译中独立 'bé/bê' 被错译为选项 'B' 的问题。"""
    if text is None or not isinstance(text, str):
        return text
    return FRENCH_BE_PATTERN.sub("B", text)


# ============================ Prompt ============================

_SYSTEM_PROMPT = (
    "你是一名专业的学科翻译专家，精通中文与多种外语，擅长教育/学术语境下的精准翻译。"
    "你必须严格按照用户指令翻译，不添加任何解释、前后缀或元说明。"
)


def _build_user_prompt(text: str, target_language: str, residual_mode: bool) -> str:
    """根据目标语言与模式构造 prompt。"""
    lang_name = "英语" if target_language == "en" else "法语" if target_language == "fr" else target_language
    base_rules = (
        f"请将以下文本翻译成{lang_name}。注意：\n"
        f"1. 如果原文已经是{lang_name}，请直接返回原文\n"
        "2. 如果原文是纯数字、公式或代码，请保持原样\n"
        "3. 只返回翻译结果，不要包含任何前缀、后缀或解释\n"
        "4. 保持专业术语的准确性\n"
        "5. 表格结构、Markdown 标记、LaTeX 公式保持原样\n"
    )
    if residual_mode:
        base_rules += (
            f"6. 重点：彻底翻译原文中所有中文字符，确保翻译结果不再包含任何中文\n"
        )
    return f"{base_rules}\n原文：\n{text}"


# ============================ 单条翻译 ============================


def _translate_text(
    text: str,
    target_language: str,
    max_retries: int = 3,
    residual_mode: bool = False,
) -> Optional[str]:
    """调用 LLM 翻译单条文本，返回译文或 None。"""
    if not text or not str(text).strip():
        return text
    user_prompt = _build_user_prompt(str(text), target_language, residual_mode)
    for attempt in range(max_retries):
        try:
            result = call_llm(
                system_prompt=_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                max_tokens=2000,
                temperature=0.1,
                max_retries=1,
            )
            if result and result.strip():
                return result.strip()
        except Exception:
            pass
        if attempt < max_retries - 1:
            time.sleep(0.5 * (attempt + 1))
    return None


def _translate_with_options_letter(
    text: str,
    target_language: str,
    max_retries: int,
    residual_mode: bool,
) -> Optional[str]:
    """对带选项字母前缀（A./B./...）的文本翻译时保留前缀字母。"""
    if not isinstance(text, str):
        return _translate_text(text, target_language, max_retries, residual_mode)
    m = OPTION_LETTER_PATTERN.match(text)
    if not m:
        return _translate_text(text, target_language, max_retries, residual_mode)
    letter = m.group(1)
    body = text[m.end():]
    translated_body = _translate_text(body, target_language, max_retries, residual_mode)
    if translated_body is None:
        return None
    return f"{letter}. {translated_body}"


# ============================ 字段读写 ============================


def _translated_field_name(field: str, target_language: str) -> str:
    """字段平铺命名：question + en → question_en。"""
    return f"{field}_{target_language}"


def _has_target(item: dict, field: str, target_language: str) -> bool:
    """检查 item 中目标字段是否已有非空值且不含中文。"""
    val = item.get(_translated_field_name(field, target_language))
    if val is None:
        return False
    if isinstance(val, str):
        return bool(val.strip()) and not contains_chinese(val)
    if isinstance(val, list):
        if not val:
            return False
        return not any(contains_chinese(v) for v in val if isinstance(v, str))
    if isinstance(val, dict):
        if not val:
            return False
        return not any(contains_chinese(v) for v in val.values() if isinstance(v, str))
    return False


def _read_source(item: dict, field: str) -> Any:
    """读取源字段，对 answer 兼容 output。"""
    val = item.get(field)
    if (val is None or val == "") and field == "answer":
        val = item.get("output")
    return val


def _is_translatable_value(val: Any) -> bool:
    if val is None:
        return False
    if isinstance(val, str):
        return bool(val.strip())
    if isinstance(val, (list, dict)):
        return len(val) > 0
    return False


# ============================ 任务模型 ============================


class TranslationTask:
    """单个翻译任务：item × field × language。"""

    __slots__ = ("idx", "field", "language", "is_options")

    def __init__(self, idx: int, field: str, language: str, is_options: bool = False):
        self.idx = idx
        self.field = field
        self.language = language
        self.is_options = is_options

    def key(self) -> str:
        return f"{self.idx}|{self.field}|{self.language}"


# ============================ 扫描 / 加载 ============================


def _scan_translation_candidates(input_dir: str) -> List[str]:
    """扫描 input_dir 下 *_synthesized.json，返回教材名列表。"""
    if not os.path.isdir(input_dir):
        return []
    candidates = []
    for fname in sorted(os.listdir(input_dir)):
        if fname.endswith("_synthesized.json"):
            folder_name = fname.replace("_synthesized.json", "")
            candidates.append(folder_name)
    return candidates


def _load_questions(input_path: str) -> Tuple[List[dict], dict]:
    """加载 JSON 中的 questions 数组及 metadata。"""
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    questions = data.get("questions", [])
    metadata = data.get("metadata", {})
    return questions, metadata


def _load_progress(progress_path: str) -> Optional[Dict[str, Any]]:
    if not os.path.isfile(progress_path):
        return None
    try:
        with open(progress_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _save_progress(progress_path: str, done_keys: List[str]) -> None:
    with open(progress_path, "w", encoding="utf-8") as f:
        json.dump({"done": sorted(set(done_keys))}, f, ensure_ascii=False, indent=2)


def _save_failed(failed_path: str, failed: List[Dict[str, Any]]) -> None:
    with open(failed_path, "w", encoding="utf-8") as f:
        json.dump({"failed": failed}, f, ensure_ascii=False, indent=2)


# ============================ 翻译写入辅助 ============================


def _translate_value(
    value: Any,
    field: str,
    target_language: str,
    max_retries: int,
    residual_mode: bool,
    fix_french_option_letter: bool,
) -> Tuple[Any, bool]:
    """
    将原始字段值翻译为目标语言版本。
    Returns:
        (translated_value, ok)：ok 为 False 表示该字段全部翻译失败。
    """
    is_options_field = field == "options"

    def _wrap_french(s: Any) -> Any:
        if (
            target_language == "fr"
            and fix_french_option_letter
            and isinstance(s, str)
        ):
            return fix_french_option(s)
        return s

    if isinstance(value, str):
        if is_options_field:
            t = _translate_with_options_letter(
                value, target_language, max_retries, residual_mode
            )
        else:
            t = _translate_text(value, target_language, max_retries, residual_mode)
        if t is None:
            return None, False
        return _wrap_french(t), True

    if isinstance(value, list):
        out_list = []
        any_ok = False
        for v in value:
            if isinstance(v, str):
                if is_options_field:
                    tv = _translate_with_options_letter(
                        v, target_language, max_retries, residual_mode
                    )
                else:
                    tv = _translate_text(v, target_language, max_retries, residual_mode)
                if tv is None:
                    out_list.append(v)
                else:
                    out_list.append(_wrap_french(tv))
                    any_ok = True
            else:
                out_list.append(v)
        return out_list, any_ok

    if isinstance(value, dict):
        out_dict = {}
        any_ok = False
        for k, v in value.items():
            if isinstance(v, str) and v.strip():
                if is_options_field:
                    tv = _translate_with_options_letter(
                        v, target_language, max_retries, residual_mode
                    )
                else:
                    tv = _translate_text(v, target_language, max_retries, residual_mode)
                if tv is None:
                    out_dict[k] = v
                else:
                    out_dict[k] = _wrap_french(tv)
                    any_ok = True
            else:
                out_dict[k] = v
        return out_dict, any_ok

    return value, True


def _has_residual_chinese(value: Any) -> bool:
    """递归检查值是否含中文。"""
    if value is None:
        return False
    if isinstance(value, str):
        return contains_chinese(value)
    if isinstance(value, list):
        return any(_has_residual_chinese(v) for v in value)
    if isinstance(value, dict):
        return any(_has_residual_chinese(v) for v in value.values())
    return False


# ============================ 阶段 1：首次翻译 ============================


def _process_first_task(
    items: List[dict],
    task: TranslationTask,
    max_retries: int,
    fix_french_option_letter: bool,
) -> Tuple[TranslationTask, Any, bool]:
    """处理一条首次翻译任务（线程池 worker）。"""
    item = items[task.idx]
    src = _read_source(item, task.field)
    if not _is_translatable_value(src):
        return task, None, True
    translated, ok = _translate_value(
        src,
        task.field,
        task.language,
        max_retries=max_retries,
        residual_mode=False,
        fix_french_option_letter=fix_french_option_letter,
    )
    return task, translated, ok


def run_translation_first(
    items: List[dict],
    target_languages: List[str],
    translate_fields: List[str],
    progress_path: str,
    max_workers: int,
    max_retries: int,
    fix_french_option_letter: bool,
    skip_existing: bool = True,
) -> Tuple[int, int]:
    """
    阶段 1：首次翻译。原地修改 items（添加 *_en / *_fr 等字段）。

    Returns:
        (success_units, failed_units)：以 item × field × language 为单位计数。
    """
    prog = _load_progress(progress_path) or {}
    done_keys = set(prog.get("done") or [])

    tasks: List[TranslationTask] = []
    for idx, item in enumerate(items):
        for field in translate_fields:
            if field == "answer" and not _is_translatable_value(item.get("answer")) and not _is_translatable_value(item.get("output")):
                continue
            if field != "answer" and not _is_translatable_value(item.get(field)):
                continue
            for lang in target_languages:
                key = f"{idx}|{field}|{lang}"
                if key in done_keys:
                    continue
                if skip_existing and _has_target(item, field, lang):
                    done_keys.add(key)
                    continue
                tasks.append(TranslationTask(idx, field, lang))

    if not tasks:
        _save_progress(progress_path, list(done_keys))
        print("阶段 1：首次翻译，无新任务（全部已存在或已完成）。")
        return 0, 0

    api_delay = get_api_delay()
    lock = threading.Lock()
    success = 0
    failed = 0
    save_every = max(20, max_workers * 2)
    completed_since_save = 0

    with tqdm(total=len(tasks), desc="首次翻译", unit="单元") as pbar:
        if max_workers <= 1:
            for task in tasks:
                _, translated, ok = _process_first_task(
                    items, task, max_retries, fix_french_option_letter
                )
                with lock:
                    if ok and translated is not None:
                        items[task.idx][_translated_field_name(task.field, task.language)] = translated
                        done_keys.add(task.key())
                        success += 1
                    else:
                        failed += 1
                    completed_since_save += 1
                    if completed_since_save >= save_every:
                        _save_progress(progress_path, list(done_keys))
                        completed_since_save = 0
                pbar.update(1)
                time.sleep(api_delay)
        else:
            with ThreadPoolExecutor(max_workers=max_workers) as ex:
                futures = {
                    ex.submit(
                        _process_first_task, items, t, max_retries, fix_french_option_letter
                    ): t
                    for t in tasks
                }
                for future in as_completed(futures):
                    try:
                        task, translated, ok = future.result()
                    except Exception:
                        with lock:
                            failed += 1
                        pbar.update(1)
                        continue
                    with lock:
                        if ok and translated is not None:
                            items[task.idx][_translated_field_name(task.field, task.language)] = translated
                            done_keys.add(task.key())
                            success += 1
                        else:
                            failed += 1
                        completed_since_save += 1
                        if completed_since_save >= save_every:
                            _save_progress(progress_path, list(done_keys))
                            completed_since_save = 0
                    pbar.update(1)
                    time.sleep(api_delay)

    _save_progress(progress_path, list(done_keys))
    print(f"阶段 1 完成：成功 {success}，失败 {failed}")
    return success, failed


# ============================ 阶段 2：残留重翻 ============================


def _retranslate_value(
    item: dict,
    field: str,
    target_language: str,
    max_retries: int,
    fix_french_option_letter: bool,
) -> Tuple[Any, bool]:
    """对已翻译字段做残留重翻：如果当前译文不含中文则跳过；否则重新翻译，源文优先取已翻译版本。"""
    cur = item.get(_translated_field_name(field, target_language))
    if cur is None or not _has_residual_chinese(cur):
        return cur, True
    src_for_retrans = cur if _is_translatable_value(cur) else _read_source(item, field)
    new_val, ok = _translate_value(
        src_for_retrans,
        field,
        target_language,
        max_retries=max_retries,
        residual_mode=True,
        fix_french_option_letter=fix_french_option_letter,
    )
    return new_val, ok


def _scan_residual_tasks(
    items: List[dict],
    target_languages: List[str],
    translate_fields: List[str],
) -> List[TranslationTask]:
    out: List[TranslationTask] = []
    for idx, item in enumerate(items):
        for field in translate_fields:
            for lang in target_languages:
                cur = item.get(_translated_field_name(field, lang))
                if cur is None:
                    continue
                if _has_residual_chinese(cur):
                    out.append(TranslationTask(idx, field, lang))
    return out


def run_translation_residual(
    items: List[dict],
    target_languages: List[str],
    translate_fields: List[str],
    max_workers: int,
    max_retries: int,
    fix_french_option_letter: bool,
    max_rounds: int = 3,
) -> List[Dict[str, Any]]:
    """
    阶段 2：残留重翻。最多 max_rounds 轮，仍残留的写入 failed 列表返回。
    """
    api_delay = get_api_delay()
    lock = threading.Lock()
    final_failed: List[Dict[str, Any]] = []

    for round_idx in range(1, max_rounds + 1):
        tasks = _scan_residual_tasks(items, target_languages, translate_fields)
        if not tasks:
            print(f"残留重翻：第 {round_idx} 轮检测无残留，提前结束。")
            return []

        round_done = 0
        round_still = 0

        with tqdm(
            total=len(tasks), desc=f"残留重翻第 {round_idx}/{max_rounds} 轮", unit="单元"
        ) as pbar:
            if max_workers <= 1:
                for task in tasks:
                    new_val, ok = _retranslate_value(
                        items[task.idx],
                        task.field,
                        task.language,
                        max_retries=max_retries,
                        fix_french_option_letter=fix_french_option_letter,
                    )
                    with lock:
                        if ok and new_val is not None:
                            items[task.idx][
                                _translated_field_name(task.field, task.language)
                            ] = new_val
                            if _has_residual_chinese(new_val):
                                round_still += 1
                            else:
                                round_done += 1
                        else:
                            round_still += 1
                    pbar.update(1)
                    time.sleep(api_delay)
            else:
                with ThreadPoolExecutor(max_workers=max_workers) as ex:
                    fut2task = {
                        ex.submit(
                            _retranslate_value,
                            items[t.idx],
                            t.field,
                            t.language,
                            max_retries,
                            fix_french_option_letter,
                        ): t
                        for t in tasks
                    }
                    for future in as_completed(fut2task):
                        task = fut2task[future]
                        try:
                            new_val, ok = future.result()
                        except Exception:
                            with lock:
                                round_still += 1
                            pbar.update(1)
                            continue
                        with lock:
                            if ok and new_val is not None:
                                items[task.idx][
                                    _translated_field_name(task.field, task.language)
                                ] = new_val
                                if _has_residual_chinese(new_val):
                                    round_still += 1
                                else:
                                    round_done += 1
                            else:
                                round_still += 1
                        pbar.update(1)
                        time.sleep(api_delay)

        print(f"  第 {round_idx} 轮：消除残留 {round_done}，仍残留 {round_still}")
        if round_still == 0:
            break

    # 收尾：仍残留的项归入 failed
    final_tasks = _scan_residual_tasks(items, target_languages, translate_fields)
    for t in final_tasks:
        item = items[t.idx]
        final_failed.append(
            {
                "idx": t.idx,
                "field": t.field,
                "language": t.language,
                "current_translation": item.get(_translated_field_name(t.field, t.language)),
                "source": _read_source(item, t.field),
                "question_preview": str(item.get("question", ""))[:80],
            }
        )
    return final_failed


# ============================ 顶层入口 ============================


def run_translation(
    input_path: str,
    output_dir: str,
    folder_name: str,
    mode: str,
    target_languages: List[str],
    translate_fields: List[str],
    max_workers: int = 8,
    max_retries: int = 3,
    fix_french_option_letter: bool = True,
    skip_existing: bool = True,
) -> Tuple[bool, str, Optional[str]]:
    """
    执行翻译。
    mode in {"first", "residual", "both"}：
      - first    ：仅首次翻译
      - residual ：仅残留重翻（要求输出文件已存在或基于输入文件已有翻译字段）
      - both     ：两阶段顺序执行

    Returns:
        (ok, translated_path, failed_path or None)
    """
    if mode not in ("first", "residual", "both"):
        raise ValueError(f"未知模式: {mode}")
    os.makedirs(output_dir, exist_ok=True)
    progress_path = os.path.join(output_dir, f"{folder_name}{PROGRESS_SUFFIX}")
    translated_path = os.path.join(output_dir, f"{folder_name}_translated.json")
    failed_path = os.path.join(output_dir, f"{folder_name}{FAILED_SUFFIX}")

    # 选择起始数据：若已有 translated 输出则在其基础上继续，否则从输入读取
    base_path = translated_path if os.path.isfile(translated_path) else input_path
    items, metadata = _load_questions(base_path)
    total = len(items)
    if total == 0:
        return False, translated_path, None

    success_first = 0
    failed_first = 0
    if mode in ("first", "both"):
        success_first, failed_first = run_translation_first(
            items=items,
            target_languages=target_languages,
            translate_fields=translate_fields,
            progress_path=progress_path,
            max_workers=max_workers,
            max_retries=max_retries,
            fix_french_option_letter=fix_french_option_letter,
            skip_existing=skip_existing,
        )

    failed_residual: List[Dict[str, Any]] = []
    if mode in ("residual", "both"):
        failed_residual = run_translation_residual(
            items=items,
            target_languages=target_languages,
            translate_fields=translate_fields,
            max_workers=max_workers,
            max_retries=max_retries,
            fix_french_option_letter=fix_french_option_letter,
            max_rounds=max_retries,
        )

    meta_out = {
        **metadata,
        "source": input_path,
        "translation": {
            "mode": mode,
            "target_languages": list(target_languages),
            "translate_fields": list(translate_fields),
            "first_success": success_first,
            "first_failed": failed_first,
            "residual_remaining": len(failed_residual),
        },
    }

    with open(translated_path, "w", encoding="utf-8") as f:
        json.dump(
            {"questions": items, "metadata": meta_out},
            f,
            ensure_ascii=False,
            indent=2,
        )

    failed_path_out: Optional[str] = None
    if failed_residual:
        _save_failed(failed_path, failed_residual)
        failed_path_out = failed_path

    print(f"\n3.7 翻译完成: {translated_path}")
    if failed_path_out:
        print(f"  仍含中文残留 {len(failed_residual)} 单元，详见: {failed_path_out}")
    return True, translated_path, failed_path_out


# ============================ 终端展示 ============================


def _print_translation_coverage(
    items: List[dict],
    target_languages: List[str],
    translate_fields: List[str],
) -> None:
    """打印各语言×字段的覆盖率。"""
    total = len(items)
    if total == 0:
        return
    print("\n【翻译覆盖率】")
    header = f"  {'字段':<14}" + "".join(
        f"{LANG_NAMES.get(lg, lg) + '(' + lg + ')':<16}" for lg in target_languages
    )
    print(header)
    for field in translate_fields:
        line = f"  {field:<14}"
        for lg in target_languages:
            n = sum(1 for it in items if _has_target(it, field, lg))
            line += f"{n}/{total} ({100 * n / total:5.1f}%)"
            line += " " * max(0, 16 - len(f"{n}/{total} ({100 * n / total:5.1f}%)"))
        print(line)
