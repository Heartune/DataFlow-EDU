# -*- coding: utf-8 -*-
"""
3.5 Deduplication 核心逻辑：基于 MinHash + LSH 对题目题干去重。
"""

import json
import os
from typing import List, Tuple

from datasketch import MinHash, MinHashLSH
from dataflow_edu._compat.tqdm import tqdm

from dataflow import get_logger

logger = get_logger()


def _scan_deduplication_candidates(input_dir: str) -> List[str]:
    """扫描 input_dir 下 *_domain_refined.json，返回教材名列表。"""
    if not os.path.isdir(input_dir):
        return []
    candidates = []
    for fname in sorted(os.listdir(input_dir)):
        if fname.endswith("_domain_refined.json"):
            name = fname[: -len("_domain_refined.json")]
            if name:
                candidates.append(name)
    return candidates


def _create_minhash(text: str, num_perm: int, n_gram: int) -> MinHash:
    """对文本使用字符级 n-gram 构建 MinHash 签名。"""
    text = text or ""
    minhash = MinHash(num_perm=num_perm)
    for i in range(len(text) - n_gram + 1):
        minhash.update(text[i : i + n_gram].encode("utf-8"))
    return minhash


def run_deduplication(
    input_path: str,
    output_dir: str,
    folder_name: str,
    threshold: float = 0.9,
    num_perm: int = 128,
    n_gram: int = 5,
) -> Tuple[bool, str | None, str | None]:
    """
    对题目进行 MinHash + LSH 去重，仅基于 question 字段。

    - 保留首次出现的题目，后续相似题目放入 removed。
    - 输出：{folder_name}_deduplicated.json（去重后）、{folder_name}_deduplication_removed.json（被剔除）。

    Returns:
        (ok, deduplicated_path, removed_path)
    """
    if not os.path.isfile(input_path):
        logger.error(f"输入文件不存在: {input_path}")
        return False, None, None

    try:
        with open(input_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.error(f"加载 JSON 失败: {e}")
        return False, None, None

    questions = data.get("questions", [])
    if not questions:
        logger.warning("题目列表为空，无需去重")
        deduplicated_path = os.path.join(output_dir, f"{folder_name}_deduplicated.json")
        removed_path = os.path.join(output_dir, f"{folder_name}_deduplication_removed.json")
        os.makedirs(output_dir, exist_ok=True)
        with open(deduplicated_path, "w", encoding="utf-8") as f:
            json.dump({"questions": []}, f, ensure_ascii=False, indent=2)
        with open(removed_path, "w", encoding="utf-8") as f:
            json.dump({"questions": []}, f, ensure_ascii=False, indent=2)
        return True, deduplicated_path, removed_path

    lsh = MinHashLSH(threshold=threshold, num_perm=num_perm)
    kept = []
    removed_list = []

    with lsh.insertion_session() as session:
        for idx, q in tqdm(enumerate(questions), desc="Deduplication", total=len(questions)):
            question_text = q.get("question") or ""
            minhash = _create_minhash(question_text, num_perm=num_perm, n_gram=n_gram)
            result = lsh.query(minhash)

            if len(result) == 0:
                kept.append(q)
                session.insert(idx, minhash)
            else:
                removed_list.append(q)

    os.makedirs(output_dir, exist_ok=True)
    deduplicated_path = os.path.join(output_dir, f"{folder_name}_deduplicated.json")
    removed_path = os.path.join(output_dir, f"{folder_name}_deduplication_removed.json")

    with open(deduplicated_path, "w", encoding="utf-8") as f:
        json.dump({"questions": kept}, f, ensure_ascii=False, indent=2)
    with open(removed_path, "w", encoding="utf-8") as f:
        json.dump({"questions": removed_list}, f, ensure_ascii=False, indent=2)

    logger.info(
        f"Deduplication 完成: 保留 {len(kept)} 题, 剔除 {len(removed_list)} 题 "
        f"(输入共 {len(questions)} 题)"
    )
    return True, deduplicated_path, removed_path
