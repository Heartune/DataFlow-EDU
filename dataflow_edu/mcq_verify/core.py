# -*- coding: utf-8 -*-
"""
3.8 MCQ Verify 核心逻辑：选择题结构校验 + LLM 修复。

参考 utils_from_CNLaw-Bench/optimize_answers.py 中的 check_choice_has_options /
complete_choice_options / validate_choice_questions_v2 思路，但去掉图片依赖，
统一通过 dataflow_edu.serving.call_llm 调用纯文本 LLM。

校验维度（5 项全开启）：
  1. options_complete   —— 题干含完整 A/B/C/D 四个选项
  2. answer_letter_valid —— answer 中能抽出合法字母（单字母或多字母）
  3. type_count_match   —— 单选 1 个、多选 ≥2
  4. options_nonempty   —— 4 选项内容非空且互不相同
  5. answer_in_options  —— 答案字母 ⊆ 题干已存在选项字母集

多语言策略：选中的语言独立校验、独立修复，任一语言修不好整题剔除。
"""

import json
import os
import re
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple

from tqdm import tqdm

from dataflow_edu.serving import call_llm, get_api_delay

PROGRESS_SUFFIX = "_mcq_verify_progress.json"
VERIFIED_SUFFIX = "_mcq_verified.json"
FAILED_SUFFIX = "_mcq_failed.json"

ALL_LANGS = ("zh", "en", "fr")
OPTION_LETTERS = ("A", "B", "C", "D")

# 兼容 A. / A、 / A： / A) / A: 五种分隔符（A: 是 A：的英文形态）
_OPTION_SEP_RE = re.compile(r"([A-D])\s*[\.\)、：:]\s*")
# 答案字母抽取
_ANSWER_LETTER_RE = re.compile(r"[A-Da-d]")

SYSTEM_PROMPT = """你是一位资深的题库编辑专家，擅长修复选择题的结构性问题。

你的任务有两件：
1. 如果题目缺少 A/B/C/D 四个选项中的部分或全部，请基于题干、答案、解析的语义，补全成 4 个互不相同、与题干高度相关、具有合理迷惑性的选项。
2. 如果原 answer 字段中没有合法的选项字母（A/B/C/D），请基于题意推出正确选项字母。

要求：
- 单选题输出单字母（如 "A"）；多选题输出逗号分隔的多字母（如 "A,C"）
- 选项格式严格为："A. 选项内容 B. 选项内容 C. 选项内容 D. 选项内容"，4 个选项之间用空格分隔
- 已有的合法选项内容尽可能保留，仅补全缺失项；若已有选项内容不足以区分则可适度修订
- 输出严格 JSON：{"options": "A. ... B. ... C. ... D. ...", "answer": "A" 或 "A,C"}
- 不要输出任何额外的说明文字、Markdown 代码块包裹也不要"""


# ======================== 字段映射 ========================


def _field_name(base: str, lang: str) -> str:
    """zh 走裸字段名，其他语言加 _<lang> 后缀。"""
    return base if lang == "zh" else f"{base}_{lang}"


def _is_mcq(item: dict) -> bool:
    """type 含选择/单选/多选 即视为 MCQ。"""
    t = str(item.get("type", "")).lower()
    return "选择" in t or "单选" in t or "多选" in t


def _is_multi_choice(item: dict) -> bool:
    """根据 type 判断单选 vs 多选。"""
    t = str(item.get("type", ""))
    return "多选" in t


# ======================== 选项 / 答案抽取 ========================


def _extract_options(text: str) -> Dict[str, str]:
    """
    从 question 文本中抽取 A/B/C/D 选项内容。

    支持 A./A、/A：/A:/A) 五种分隔符（与 optimize_answers.check_choice_has_options 一致 + 英文冒号）。
    返回 {'A': 'xxx', 'B': 'yyy', ...}，缺哪个就没有哪个 key。
    """
    if not text:
        return {}
    matches = list(_OPTION_SEP_RE.finditer(text))
    if not matches:
        return {}
    options: Dict[str, str] = {}
    for i, m in enumerate(matches):
        letter = m.group(1).upper()
        if letter not in OPTION_LETTERS:
            continue
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content = text[start:end].strip()
        # 去掉末尾常见标点
        content = content.rstrip(" ;,.；，。")
        if letter in options:
            # 同一字母多次出现，以第一次为准
            continue
        options[letter] = content
    return options


def _extract_answer_letters(answer: str) -> List[str]:
    """从 answer 文本中抽取合法的 A/B/C/D 字母序列（去重保序）。"""
    if not answer:
        return []
    seen = []
    for ch in _ANSWER_LETTER_RE.findall(answer):
        up = ch.upper()
        if up in OPTION_LETTERS and up not in seen:
            seen.append(up)
    return seen


# ======================== 5 维校验 ========================


def _validate(item: dict, lang: str) -> Tuple[bool, List[str]]:
    """
    对指定语言做 5 维结构校验。返回 (ok, reasons)。

    reasons 中每条形如 "options_complete: 缺 C/D"。
    """
    q_field = _field_name("question", lang)
    a_field = _field_name("answer", lang)
    q_text = str(item.get(q_field, "")).strip()
    a_text = str(item.get(a_field, "")).strip()

    reasons: List[str] = []

    # 字段缺失视为最严重失败：5 维都报
    if not q_text:
        reasons.append(f"options_complete: 缺字段 {q_field}")
    if not a_text:
        reasons.append(f"answer_letter_valid: 缺字段 {a_field}")
    if reasons and not q_text and not a_text:
        return False, reasons

    options = _extract_options(q_text) if q_text else {}
    missing = [L for L in OPTION_LETTERS if L not in options]

    # 1. options_complete
    if missing:
        reasons.append(f"options_complete: 缺 {'/'.join(missing)}")

    # 4. options_nonempty
    if not missing:
        empty_letters = [L for L in OPTION_LETTERS if not options.get(L, "").strip()]
        if empty_letters:
            reasons.append(f"options_nonempty: {'/'.join(empty_letters)} 内容为空")
        else:
            contents = [options[L] for L in OPTION_LETTERS]
            if len(set(contents)) < 4:
                # 找出重复
                dup = [c for c, n in Counter(contents).items() if n > 1]
                reasons.append(f"options_nonempty: 选项内容重复({len(dup)} 组)")

    letters = _extract_answer_letters(a_text)

    # 2. answer_letter_valid
    if not letters:
        reasons.append("answer_letter_valid: 未抽出合法字母")

    # 3. type_count_match
    if letters:
        if _is_multi_choice(item):
            if len(letters) < 2:
                reasons.append("type_count_match: 多选题答案少于 2 个字母")
        else:
            if len(letters) > 1:
                reasons.append("type_count_match: 单选题答案含多个字母")

    # 5. answer_in_options
    if letters and not missing:
        present = set(options.keys())
        out_of_range = [L for L in letters if L not in present]
        if out_of_range:
            reasons.append(f"answer_in_options: {','.join(out_of_range)} 不在选项中")

    return (len(reasons) == 0), reasons


# ======================== LLM 修复 ========================


def _strip_code_fence(text: str) -> str:
    """去掉 ```json ... ``` 包裹。"""
    s = text.strip()
    if s.startswith("```"):
        # 去首行 ``` / ```json
        first_nl = s.find("\n")
        if first_nl != -1:
            s = s[first_nl + 1 :]
        if s.endswith("```"):
            s = s[:-3]
    return s.strip()


def _build_repair_user_prompt(
    item: dict,
    lang: str,
    existing_options: Dict[str, str],
    missing_letters: List[str],
    is_multi: bool,
) -> str:
    q_field = _field_name("question", lang)
    a_field = _field_name("answer", lang)
    e_field = _field_name("explanation", lang)
    q_text = str(item.get(q_field, "")).strip() or str(item.get("question", "")).strip()
    a_text = str(item.get(a_field, "")).strip() or str(item.get("answer", "")).strip()
    e_text = str(item.get(e_field, "")).strip() or str(item.get("explanation", "")).strip()

    lang_label = {"zh": "中文", "en": "英文 (English)", "fr": "法语 (Français)"}.get(lang, lang)
    type_label = "多选题（答案 ≥2 个字母）" if is_multi else "单选题（答案恰好 1 个字母）"

    existing_str = (
        "\n".join([f"  {L}. {existing_options[L]}" for L in OPTION_LETTERS if L in existing_options])
        or "  （无）"
    )
    missing_str = "/".join(missing_letters) if missing_letters else "（无，仅需校正答案字母）"

    return f"""请用【{lang_label}】修复下列选择题。

题型：{type_label}
原题干：
{q_text}

原答案：
{a_text}

原解析（参考，可能为空）：
{e_text or '（无）'}

已存在的选项：
{existing_str}

缺失的选项字母：{missing_str}

请输出修复后的完整 4 个选项与正确答案字母，严格 JSON：
{{"options": "A. xxx B. xxx C. xxx D. xxx", "answer": "A 或 A,C"}}"""


def _parse_repair_response(text: str) -> Optional[Dict[str, str]]:
    """解析 LLM 输出 JSON：{ options, answer }。"""
    if not text:
        return None
    raw = _strip_code_fence(text)
    try:
        obj = json.loads(raw)
    except Exception:
        # 兜底：尝试抽出第一个 {...}
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            return None
        try:
            obj = json.loads(m.group(0))
        except Exception:
            return None
    if not isinstance(obj, dict):
        return None
    options = str(obj.get("options", "")).strip()
    answer = str(obj.get("answer", "")).strip()
    if not options:
        return None
    return {"options": options, "answer": answer}


def _strip_existing_options(q_text: str) -> str:
    """从题干中去掉已有的 A/B/C/D 选项段，便于拼接修复后的新选项。"""
    if not q_text:
        return q_text
    matches = list(_OPTION_SEP_RE.finditer(q_text))
    if not matches:
        return q_text.strip()
    cut = matches[0].start()
    head = q_text[:cut].rstrip(" \t\n;,.；，。")
    return head


def _repair_with_llm(
    item: dict,
    lang: str,
    max_tokens: int,
    temperature: float,
    max_retries: int,
) -> Optional[Dict[str, str]]:
    """
    调用 LLM 一次性补全选项 + 推合法答案字母。

    成功返回 {"question": "<新 question>", "answer": "<新 answer>"}（不直接写 item，由调用方写回）。
    失败返回 None。
    """
    q_field = _field_name("question", lang)
    a_field = _field_name("answer", lang)
    q_text = str(item.get(q_field, "")).strip()

    existing = _extract_options(q_text)
    missing = [L for L in OPTION_LETTERS if L not in existing]
    is_multi = _is_multi_choice(item)

    user_prompt = _build_repair_user_prompt(item, lang, existing, missing, is_multi)

    for attempt in range(max(1, max_retries)):
        try:
            resp = call_llm(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=user_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                max_retries=1,
            )
        except Exception:
            resp = None
        parsed = _parse_repair_response(resp) if resp else None
        if parsed:
            new_options = parsed["options"]
            new_answer = parsed["answer"] or str(item.get(a_field, "")).strip()
            head = _strip_existing_options(q_text)
            sep = "" if not head else (" " if head[-1] not in "?？:：" else " ")
            new_question = f"{head}{sep}{new_options}".strip()
            return {"question": new_question, "answer": new_answer}
        if attempt < max_retries - 1:
            time.sleep(2 * (attempt + 1))
    return None


# ======================== 候选扫描 / 数据 IO ========================


# 各阶段问题 JSON 文件后缀（优先级从高到低）
_QUESTION_SUFFIXES: List[str] = [
    "_translated.json",
    "_synthesized.json",
    "_deduplicated.json",
    "_domain_refined.json",
    "_domain_cleaned.json",
    "_ambiguity_refined.json",
    "_ambiguity_cleaned.json",
    "_balanced_questions.json",
    "_generated_questions.json",
]


def _scan_mcq_candidates(input_dir: str) -> List[str]:
    """扫描 input_dir 下的问题 JSON 文件，返回教材名列表。

    支持多种上游阶段的文件命名格式，不再限定必须为 *_translated.json。
    同一教材名只取最高优先级后缀对应的文件。
    """
    if not os.path.isdir(input_dir):
        return []
    seen: set = set()
    out: List[str] = []
    for fname in sorted(os.listdir(input_dir)):
        for suffix in _QUESTION_SUFFIXES:
            if fname.endswith(suffix):
                name = fname[: -len(suffix)]
                if name and name not in seen:
                    seen.add(name)
                    out.append(name)
                break
    return out


def _find_input_file(input_dir: str, name: str) -> Optional[str]:
    """在 input_dir 中查找指定教材名对应的问题 JSON 文件。

    按 _QUESTION_SUFFIXES 优先级顺序依次尝试，返回第一个存在的路径；
    全部不存在时返回 None。
    """
    for suffix in _QUESTION_SUFFIXES:
        path = os.path.join(input_dir, f"{name}{suffix}")
        if os.path.isfile(path):
            return path
    return None


def _load_input(input_path: str) -> Tuple[List[dict], dict]:
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("questions", []), data.get("metadata", {})


def _load_progress(progress_path: str) -> Optional[Dict[str, Any]]:
    if not os.path.isfile(progress_path):
        return None
    try:
        with open(progress_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _save_progress(
    progress_path: str,
    processed: Dict[int, str],
    patches: Dict[int, Dict[str, str]],
    failures: Dict[int, Dict[str, List[str]]],
) -> None:
    payload = {
        "processed": {str(k): v for k, v in processed.items()},
        "patches": {str(k): v for k, v in patches.items()},
        "failures": {
            str(k): {lang: list(reasons) for lang, reasons in v.items()}
            for k, v in failures.items()
        },
    }
    with open(progress_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


# ======================== 单题处理 ========================


def _process_single_mcq(
    idx: int,
    item: dict,
    target_languages: List[str],
    max_tokens: int,
    temperature: float,
    max_retries: int,
) -> Tuple[int, str, Dict[str, str], Dict[str, List[str]]]:
    """
    处理单道 MCQ。

    Returns:
      (idx, status, patches, failures)
      status ∈ {"passed", "repaired", "dropped"}
      patches: {field_name: new_value}  仅 repaired 状态下含已写入字段
      failures: {lang: [reason, ...]}   dropped 状态下含每语言最终失败原因
    """
    work = dict(item)  # 副本，避免污染共享对象
    initial_pass = True
    initial_failures: Dict[str, List[str]] = {}
    for lang in target_languages:
        ok, reasons = _validate(work, lang)
        if not ok:
            initial_pass = False
            initial_failures[lang] = reasons
    if initial_pass:
        return idx, "passed", {}, {}

    # 走修复
    patches: Dict[str, str] = {}
    final_failures: Dict[str, List[str]] = {}
    for lang in target_languages:
        if lang not in initial_failures:
            continue
        repaired = _repair_with_llm(work, lang, max_tokens, temperature, max_retries)
        if not repaired:
            final_failures[lang] = initial_failures[lang]
            continue
        # 写回临时副本，复跑校验
        q_field = _field_name("question", lang)
        a_field = _field_name("answer", lang)
        work[q_field] = repaired["question"]
        work[a_field] = repaired["answer"]
        ok2, reasons2 = _validate(work, lang)
        if ok2:
            patches[q_field] = repaired["question"]
            patches[a_field] = repaired["answer"]
        else:
            final_failures[lang] = reasons2

    if final_failures:
        return idx, "dropped", {}, final_failures
    return idx, "repaired", patches, {}


# ======================== 主流程 ========================


def _print_mcq_summary(
    total: int,
    non_mcq: int,
    mcq_total: int,
    passed_initial: int,
    repaired_ok: int,
    dropped: int,
    target_languages: List[str],
    failure_reasons: Dict[str, Counter],
) -> None:
    """终端打印 MCQ Verify 汇总。"""
    print("\n【3.8 MCQ Verify 汇总】")
    print(f"  总题数: {total}")
    print(f"  非 MCQ 透传: {non_mcq}")
    print(f"  MCQ 题数: {mcq_total}")
    print(f"  ├─ 初次直接通过: {passed_initial}")
    print(f"  ├─ 修复后通过: {repaired_ok}")
    print(f"  └─ 修复仍失败被剔除: {dropped}")
    print(f"  校验语言: {target_languages}")
    if dropped:
        print("\n  各语言失败维度 Top:")
        for lang in target_languages:
            counter = failure_reasons.get(lang) or Counter()
            if not counter:
                continue
            top = counter.most_common(3)
            top_str = "; ".join([f"{name.split(':')[0]}({n})" for name, n in top])
            print(f"    {lang}: {top_str}")


def run_mcq_verify(
    input_path: str,
    output_dir: str,
    folder_name: str,
    target_languages: List[str],
    max_workers: int = 8,
    max_retries: int = 3,
    max_tokens: int = 2000,
    temperature: float = 0.3,
    resume: bool = False,
) -> Tuple[bool, str, Optional[str]]:
    """
    执行 3.8 MCQ Verify。

    Returns:
      (ok, verified_path, failed_path | None)
    """
    os.makedirs(output_dir, exist_ok=True)
    progress_path = os.path.join(output_dir, f"{folder_name}{PROGRESS_SUFFIX}")
    verified_path = os.path.join(output_dir, f"{folder_name}{VERIFIED_SUFFIX}")
    failed_path = os.path.join(output_dir, f"{folder_name}{FAILED_SUFFIX}")

    questions, metadata = _load_input(input_path)
    total = len(questions)
    if total == 0:
        print("⚠ 输入文件不含任何题目。")
        return False, verified_path, None

    # 划分 MCQ / 非 MCQ
    mcq_indices = [i for i, q in enumerate(questions) if _is_mcq(q)]
    non_mcq_count = total - len(mcq_indices)
    print(f"\n检测到 MCQ {len(mcq_indices)} 道，非 MCQ {non_mcq_count} 道。")
    if not mcq_indices:
        # 仍然要落盘（非 MCQ 全透传），保持管线统一
        print("⚠ 没有 MCQ 题目可校验，将直接透传所有题目。")

    # 加载 resume 进度
    processed: Dict[int, str] = {}
    patches: Dict[int, Dict[str, str]] = {}
    failures: Dict[int, Dict[str, List[str]]] = {}
    if resume:
        prog = _load_progress(progress_path)
        if prog:
            for k, v in (prog.get("processed") or {}).items():
                try:
                    processed[int(k)] = str(v)
                except (TypeError, ValueError):
                    continue
            for k, v in (prog.get("patches") or {}).items():
                try:
                    patches[int(k)] = {str(fk): str(fv) for fk, fv in (v or {}).items()}
                except (TypeError, ValueError):
                    continue
            for k, v in (prog.get("failures") or {}).items():
                try:
                    failures[int(k)] = {
                        str(lang): [str(r) for r in (reasons or [])]
                        for lang, reasons in (v or {}).items()
                    }
                except (TypeError, ValueError):
                    continue
            done_n = sum(1 for i in mcq_indices if i in processed)
            if done_n:
                print(f"Resume: 已处理 {done_n}/{len(mcq_indices)} 道 MCQ")

    needs_work = [i for i in mcq_indices if i not in processed]

    api_delay = get_api_delay()
    lock = threading.Lock()
    save_every = max(10, max_workers * 2)
    completed_since_save = 0

    if needs_work:
        with tqdm(total=len(needs_work), desc="MCQ 校验", unit="题") as pbar:
            if max_workers <= 1:
                for idx in needs_work:
                    _, status, p, f = _process_single_mcq(
                        idx, questions[idx], target_languages, max_tokens, temperature, max_retries
                    )
                    with lock:
                        processed[idx] = status
                        if p:
                            patches[idx] = p
                        if f:
                            failures[idx] = f
                        completed_since_save += 1
                        if completed_since_save >= save_every:
                            _save_progress(progress_path, processed, patches, failures)
                            completed_since_save = 0
                    pbar.update(1)
                    time.sleep(api_delay)
            else:
                with ThreadPoolExecutor(max_workers=max_workers) as ex:
                    futures = {
                        ex.submit(
                            _process_single_mcq,
                            idx,
                            questions[idx],
                            target_languages,
                            max_tokens,
                            temperature,
                            max_retries,
                        ): idx
                        for idx in needs_work
                    }
                    for fut in as_completed(futures):
                        idx = futures[fut]
                        try:
                            _, status, p, f = fut.result()
                        except Exception as e:
                            status = "dropped"
                            p = {}
                            f = {"_exception": [str(e)]}
                        with lock:
                            processed[idx] = status
                            if p:
                                patches[idx] = p
                            if f:
                                failures[idx] = f
                            completed_since_save += 1
                            if completed_since_save >= save_every:
                                _save_progress(progress_path, processed, patches, failures)
                                completed_since_save = 0
                        pbar.update(1)
                        time.sleep(api_delay)

    _save_progress(progress_path, processed, patches, failures)

    # 组装主输出 / 失败清单
    output_items: List[dict] = []
    failed_records: List[dict] = []
    passed_initial = 0
    repaired_ok = 0
    dropped = 0
    failure_reasons: Dict[str, Counter] = {lang: Counter() for lang in target_languages}

    for i in range(total):
        item = dict(questions[i])
        if i not in mcq_indices:
            output_items.append(item)
            continue
        status = processed.get(i, "dropped")
        if status == "passed":
            output_items.append(item)
            passed_initial += 1
        elif status == "repaired":
            for fk, fv in (patches.get(i) or {}).items():
                item[fk] = fv
            output_items.append(item)
            repaired_ok += 1
        else:  # dropped
            dropped += 1
            f = failures.get(i) or {}
            failed_records.append(
                {
                    "index": i,
                    "type": item.get("type", ""),
                    "question": item.get("question", ""),
                    "answer": item.get("answer", ""),
                    "failures": {lang: list(reasons) for lang, reasons in f.items()},
                }
            )
            for lang, reasons in f.items():
                if lang not in failure_reasons:
                    continue
                for r in reasons:
                    failure_reasons[lang][r] += 1

    meta_out = {
        **metadata,
        "source": input_path,
        "mcq_verify": {
            "total": total,
            "non_mcq_passthrough": non_mcq_count,
            "mcq_total": len(mcq_indices),
            "mcq_passed_initial": passed_initial,
            "mcq_passed_after_repair": repaired_ok,
            "mcq_dropped": dropped,
            "target_languages": list(target_languages),
        },
    }

    with open(verified_path, "w", encoding="utf-8") as f:
        json.dump({"questions": output_items, "metadata": meta_out}, f, ensure_ascii=False, indent=2)

    failed_out_path: Optional[str] = None
    if failed_records:
        with open(failed_path, "w", encoding="utf-8") as f:
            json.dump(
                {"failed": failed_records, "metadata": meta_out["mcq_verify"]},
                f,
                ensure_ascii=False,
                indent=2,
            )
        failed_out_path = failed_path

    _print_mcq_summary(
        total=total,
        non_mcq=non_mcq_count,
        mcq_total=len(mcq_indices),
        passed_initial=passed_initial,
        repaired_ok=repaired_ok,
        dropped=dropped,
        target_languages=target_languages,
        failure_reasons=failure_reasons,
    )
    print(f"\n✓ 主输出: {verified_path}")
    if failed_out_path:
        print(f"  失败清单: {failed_out_path}")
    print(f"  进度文件: {progress_path}")
    return True, verified_path, failed_out_path
