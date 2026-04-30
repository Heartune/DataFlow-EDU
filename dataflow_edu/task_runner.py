# -*- coding: utf-8 -*-
"""
DataFlow-EDU 多用户任务 Runner（非交互式）。

由 webui/server 通过 `python -m dataflow_edu.task_runner ...` 拉起。
负责：
  1. 注入 input_dir / output_dir，把所有阶段产物落到 task_dir 下；
  2. 为每个阶段写 progress.json，供 SSE 监听；
  3. monkey-patch 交互式 input 与 interactive_config_llm，使现有算子在 webui 模式下能跑通；
  4. BYOK key 通过环境变量 LLM_API_KEY 传入，进程结束即销毁。

进入条件：环境变量 DATAFLOW_NONINTERACTIVE=1（必填）。
"""

from __future__ import annotations

import argparse
import builtins
import json
import os
import sys
import time
import traceback
from datetime import datetime
from typing import Any, Callable

# ---- 路径准备：与 edu_data_pipeline.py 一致 ----
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
_DATAFLOW_ROOT = os.path.join(_PROJECT_ROOT, "DataFlow")
if os.path.isdir(_DATAFLOW_ROOT) and _DATAFLOW_ROOT not in sys.path:
    sys.path.insert(0, _DATAFLOW_ROOT)


# ============================================================
# 1) 非交互输入兜底
# ============================================================

# 根据 prompt 关键字给出默认回答
_INPUT_RULES: list[tuple[str, str]] = [
    ("请输入序号选择教材", "1"),
    ("请输入序号选择文件", "1"),
    ("请输入编号", "a"),  # mineru_ocr.interactive_select_textbooks → 全选
    # GenerationOperator: "按回车运行{1|2|all}阶段，或输入 1/2/all: "
    # 不要让它走默认值（默认会因为 stage1 还没跑就只跑 stage1，导致没生成题目）
    ("1/2/all", "all"),
    ("是否从上次进度继续", "y"),
    ("是否断点续传", "1"),
    ("是否强制重生成", "n"),
    ("Tiny 模式", "0"),
    ("是否临时增加排除子层级", ""),
    ("请选择 (1/2/3)", "3"),
    ("请输入 (1/2/3)", "3"),
    ("请输入 (0/1)", "1"),
    ("随机种子", ""),
    ("确认剔除并保存", "y"),
    ("是否使用已选模型", "y"),
]


# 同一 prompt 连续被问超过该阈值，直接 raise，避免上层 while True 把日志写爆。
_INPUT_LOOP_THRESHOLD = 50
_last_prompt: dict[str, int] = {"prompt": 0, "count": 0}  # 用 0/0 占位，键是 hash


def _ni_input(prompt: str = "") -> str:
    p = prompt or ""
    # 死循环熔断：同一 prompt 反复被问明显说明喂的答案不被接受
    h = hash(p)
    if _last_prompt.get("prompt") == h:
        _last_prompt["count"] = int(_last_prompt.get("count", 0)) + 1
    else:
        _last_prompt["prompt"] = h
        _last_prompt["count"] = 1
    if int(_last_prompt["count"]) > _INPUT_LOOP_THRESHOLD:
        raise RuntimeError(
            f"non-interactive input loop detected: prompt repeated >{_INPUT_LOOP_THRESHOLD} times: {p[:200]!r}"
        )
    for kw, ans in _INPUT_RULES:
        if kw in p:
            return ans
    return ""


def _install_input_patch() -> None:
    builtins.input = _ni_input  # type: ignore[assignment]


# ============================================================
# 2) LLM 客户端非交互式初始化
# ============================================================


def _init_llm_noninteractive() -> None:
    """
    用环境变量 / 已保存的 .llm_config.json 直接初始化 LLM 客户端，
    并把 dataflow_edu.serving.llm_client.interactive_config_llm monkey-patch 成无交互版。

    优先级（provider / model / base_url）：
      - 环境变量 DATAFLOW_LLM_{PROVIDER, MODEL, BASE_URL}
      - 项目根 .llm_config.json 中保存的同类字段
      - 兜底默认 provider=openai
    api_key：
      - 环境变量 LLM_API_KEY > 上述配置文件中 llm_api_key_<provider> > 空
    """
    from dataflow_edu.serving import llm_client

    saved = llm_client._load_config()  # type: ignore[attr-defined]
    provider = (
        os.getenv("DATAFLOW_LLM_PROVIDER")
        or saved.get("llm_provider")
        or "openai"
    ).strip()

    pc = llm_client.LLM_PROVIDERS.get(provider, {})
    base_url = (
        os.getenv("DATAFLOW_LLM_BASE_URL")
        or saved.get(f"llm_base_url_{provider}")
        or pc.get("base_url")
        or ""
    ).strip()
    model = (
        os.getenv("DATAFLOW_LLM_MODEL")
        or saved.get(f"llm_model_{provider}")
        or "gpt-4o-mini"
    ).strip()
    api_key = (
        os.getenv("LLM_API_KEY")
        or saved.get(f"llm_api_key_{provider}")
        or pc.get("default_api_key")
        or ""
    ).strip()

    if not api_key:
        raise RuntimeError(
            "未找到 LLM API Key：请通过 X-LLM-Key 头携带 BYOK，或先用 CLI "
            "运行一次 interactive_config_llm 把凭据保存到 .llm_config.json"
        )
    if not base_url:
        raise RuntimeError(f"未找到 LLM base_url（provider={provider}）")

    headers = pc.get("default_headers")
    max_workers = int(os.getenv("DATAFLOW_LLM_MAX_WORKERS") or pc.get("default_concurrent") or 8)
    api_delay = float(os.getenv("DATAFLOW_LLM_API_DELAY") or pc.get("default_delay") or 0.3)
    request_timeout = int(os.getenv("DATAFLOW_LLM_TIMEOUT") or pc.get("default_timeout") or 120)

    llm_client.init_client(
        api_key=api_key,
        base_url=base_url,
        model=model,
        headers=headers,
        max_workers=max_workers,
        api_delay=api_delay,
        request_timeout=request_timeout,
        max_retries=3,
    )

    def _patched_interactive_config_llm(gen_config_max_workers: int = 8) -> bool:
        # 已经在上面 init 过了，这里直接返回 True
        return True

    llm_client.interactive_config_llm = _patched_interactive_config_llm  # type: ignore[assignment]
    # serving 包同名导出也要 patch，避免 from dataflow_edu.serving import interactive_config_llm 拿到旧引用
    from dataflow_edu import serving as _serving_pkg

    _serving_pkg.interactive_config_llm = _patched_interactive_config_llm  # type: ignore[attr-defined]

    # 关键：各 operator 模块在 import 时已经把 interactive_config_llm 拷贝进了自己的命名空间，
    # 单独 patch llm_client / serving 包都不会更新这些已经拷出去的引用。
    # 必须遍历所有已加载的 dataflow_edu.operators.* 子模块，把它们的同名符号统一替换掉，
    # 否则 GenerationOperator / BalancingOperator / ... 仍然会调到原始交互式实现，
    # 在 webui 模式下被 _ni_input 喂入空串/'a' 触发 "无效输入" 死循环。
    import sys as _sys

    for _mod_name, _mod in list(_sys.modules.items()):
        if not _mod_name.startswith("dataflow_edu."):
            continue
        if _mod is None:
            continue
        if getattr(_mod, "interactive_config_llm", None) is None:
            continue
        try:
            setattr(_mod, "interactive_config_llm", _patched_interactive_config_llm)
        except Exception:
            pass


# ============================================================
# 3) 进度文件读写
# ============================================================


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


class ProgressTracker:
    def __init__(
        self,
        task_dir: str,
        task_id: str,
        task_name: str,
        stages: list[str],
        preserved_states: dict[str, dict] | None = None,
        disabled_stages: set[str] | None = None,
    ):
        self.task_dir = task_dir
        self.path = os.path.join(task_dir, "progress.json")
        os.makedirs(task_dir, exist_ok=True)
        preserved = preserved_states or {}
        disabled = disabled_stages or set()
        stage_entries: list[dict[str, Any]] = []
        for s in stages:
            if s in preserved:
                entry: dict[str, Any] = {"name": s, "status": "succeeded"}
                ts = preserved[s] or {}
                if ts.get("started_at"):
                    entry["started_at"] = ts["started_at"]
                if ts.get("finished_at"):
                    entry["finished_at"] = ts["finished_at"]
                stage_entries.append(entry)
            elif s in disabled:
                stage_entries.append({"name": s, "status": "skipped", "note": "已跳过"})
            else:
                stage_entries.append({"name": s, "status": "pending"})
        self.state: dict[str, Any] = {
            "task_id": task_id,
            "task_name": task_name,
            "status": "running",
            "current_stage": None,
            "started_at": _now_iso(),
            "finished_at": None,
            "error": None,
            "stages": stage_entries,
        }
        self._flush()

    def _flush(self) -> None:
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.state, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    def _stage(self, name: str) -> dict[str, Any]:
        for s in self.state["stages"]:
            if s["name"] == name:
                return s
        s = {"name": name, "status": "pending"}
        self.state["stages"].append(s)
        return s

    def stage_start(self, name: str) -> None:
        self.state["current_stage"] = name
        s = self._stage(name)
        s["status"] = "running"
        s["started_at"] = _now_iso()
        s.pop("error", None)
        self._flush()

    def stage_succeed(self, name: str) -> None:
        s = self._stage(name)
        s["status"] = "succeeded"
        s["finished_at"] = _now_iso()
        self._flush()

    def stage_fail(self, name: str, err: str) -> None:
        s = self._stage(name)
        s["status"] = "failed"
        s["finished_at"] = _now_iso()
        s["error"] = err
        self.state["status"] = "failed"
        self.state["error"] = err
        self.state["finished_at"] = _now_iso()
        self._flush()

    def stage_skip(self, name: str, reason: str) -> None:
        s = self._stage(name)
        s["status"] = "skipped"
        s["finished_at"] = _now_iso()
        s["note"] = reason
        self._flush()

    def finish_ok(self) -> None:
        self.state["status"] = "succeeded"
        self.state["finished_at"] = _now_iso()
        self.state["current_stage"] = None
        self._flush()


# ============================================================
# 4) 配置注入：把所有算子的 input/output_dir 改写到 task_dir 下
# ============================================================

# task_dir 下的子目录布局（沿用 dataflow_edu/data 现有命名）
_LAYOUT = {
    "img_dir": "1_2_ocr/img",
    "md_dir": "1_2_ocr/md",
    "generation_output": "2_1_generation",   # 2.1 Generation 输出根目录（含 stage_1/stage_2 子目录）
    "balanced": "2_1_generation/2_2_balanced",  # 2.2 Balancing 真实落盘子目录，3.1 input
    "amb_clean": "3_1_ambiguity_cleaned",
    "amb_refine": "3_2_ambiguity_refined",
    "domain_clean": "3_3_domain_cleaned",
    "domain_refine": "3_4_domain_refined",
    "dedup": "3_5_deduplicated",
    "synthesis": "3_6_synthesized",
    "translation": "3_7_translated",
    "mcq_verify": "3_8_mcq_verified",
}


def _abs_under(task_dir: str, rel: str) -> str:
    p = os.path.join(task_dir, rel)
    os.makedirs(p, exist_ok=True)
    return p


def _override_config_paths(config, task_dir: str, disabled_stages: "set[str] | None" = None) -> None:
    """把 config.operators 里所有 *_dir 改写到 task_dir 下的子目录。

    disabled_stages 非空时，动态计算 3.x 链路每个算子的 input_dir，
    将被跳过步骤的输出"穿透"给下一个启用的步骤。
    """
    ops = config.operators
    disabled = disabled_stages or set()

    if "mineru_ocr" in ops:
        ops["mineru_ocr"].img_dir = _abs_under(task_dir, _LAYOUT["img_dir"])
        ops["mineru_ocr"].md_dir = _abs_under(task_dir, _LAYOUT["md_dir"])
    if "generation" in ops:
        ops["generation"].md_dir = _abs_under(task_dir, _LAYOUT["md_dir"])
        ops["generation"].output_dir = _abs_under(task_dir, _LAYOUT["generation_output"])
    if "balancing" in ops:
        # BalancingOperator 内部会写到 <output_dir>/2_2_balanced/，所以这里给的是 generation 根
        ops["balancing"].output_dir = _abs_under(task_dir, _LAYOUT["generation_output"])

    # ── 3.x 链路：动态穿透跳过的步骤 ──────────────────────────────────────────
    # 链路定义：(stage_name, op_key, output_layout_key)
    _CHAIN_3X = [
        ("3.1 题意模糊检查", "ambiguity_cleaning",   "amb_clean"),
        ("3.2 题意模糊修正", "ambiguity_refinement", "amb_refine"),
        ("3.3 考察领域检查", "domain_cleaning",      "domain_clean"),
        ("3.4 考察领域修正", "domain_refinement",    "domain_refine"),
        ("3.5 去除重复题目", "deduplication",        "dedup"),
        ("3.6 题库增强",     "synthesis",            "synthesis"),
        ("3.7 多语言翻译",   "translation",          "translation"),
        ("3.8 选择题格式检查", "mcq_verify",         "mcq_verify"),
    ]

    # 链路起点：2.2 启用 → balanced 子目录；2.2 禁用 → 直接读 2.1 stage2 输出
    if "2.2 知识均衡检查与修正" not in disabled:
        current_input: str = _abs_under(task_dir, _LAYOUT["balanced"])
    else:
        current_input = _abs_under(task_dir, "2_1_generation/2_1_generated_stage_2")

    for stage_name, op_key, out_key in _CHAIN_3X:
        if op_key not in ops:
            continue
        ops[op_key].input_dir = current_input
        if stage_name not in disabled:
            ops[op_key].output_dir = _abs_under(task_dir, _LAYOUT[out_key])
            current_input = ops[op_key].output_dir
        # 禁用时：current_input 保持不变（穿透），output_dir 留原值（不会被写入）


# ============================================================
# 5) 阶段顺序与执行
# ============================================================

# 阶段名 -> run_* 函数名（None 表示自定义阶段，由 task_runner 自己处理）
# 注：M1 跑 PDF→Images -> OCR -> Generation -> Balancing -> 3.1~3.8（execute/judge 不纳入）
STAGES: list[tuple[str, str | None]] = [
    ("1.1 PDF转图片", None),
    ("1.2 文字识别", "run_mineru_ocr"),
    ("2.1 题目生成", "run_generation"),
    ("2.2 知识均衡检查与修正", "run_balancing"),
    ("3.1 题意模糊检查", "run_ambiguity_cleaning"),
    ("3.2 题意模糊修正", "run_ambiguity_refinement"),
    ("3.3 考察领域检查", "run_domain_cleaning"),
    ("3.4 考察领域修正", "run_domain_refinement"),
    ("3.5 去除重复题目", "run_deduplication"),
    ("3.6 题库增强", "run_synthesis"),
    ("3.7 多语言翻译", "run_translation"),
    ("3.8 选择题格式检查", "run_mcq_verify"),
]


# 阶段产出"判定文件" glob（相对 task_dir）。跑完阶段后必须至少匹配 1 个文件，
# 否则视为静默失败（算子里只 logger.warning + return False, 不抛异常的场景）。
# None 表示该阶段不做后置检查。
_STAGE_SENTINELS: dict[str, str | None] = {
    "1.1 PDF转图片": "1_2_ocr/img/*/page_*.png",
    # MinerU 输出名为「与源图同基名」.md，不限于 page_ 前缀
    "1.2 文字识别": "1_2_ocr/md/*/*.md",
    "2.1 题目生成": "2_1_generation/2_1_generated_stage_2/*_generated_questions.json",
    "2.2 知识均衡检查与修正": "2_1_generation/2_2_balanced/*_balanced_questions.json",
    "3.1 题意模糊检查": "3_1_ambiguity_cleaned/*_ambiguity_cleaned.json",
    "3.2 题意模糊修正": "3_2_ambiguity_refined/*_ambiguity_refined.json",
    "3.3 考察领域检查": "3_3_domain_cleaned/*_domain_cleaned.json",
    "3.4 考察领域修正": "3_4_domain_refined/*_domain_refined.json",
    "3.5 去除重复题目": "3_5_deduplicated/*_deduplicated.json",
    "3.6 题库增强": "3_6_synthesized/*_synthesized.json",
    "3.7 多语言翻译": "3_7_translated/*_translated.json",
    "3.8 选择题格式检查": "3_8_mcq_verified/*_mcq_verified.json",
}


# 阶段产物目录（相对 task_dir）。续跑某 stage 前会把这些目录递归清掉，避免上次半成品干扰本次。
# 新增 stage 时必须同步在这里登记，否则续跑会复用旧产物，看起来"瞬间通过"。
_STAGE_OUTPUT_DIRS: dict[str, list[str]] = {
    "1.1 PDF转图片": ["1_2_ocr/img"],
    "1.2 文字识别": ["1_2_ocr/md"],
    "2.1 题目生成": [
        "2_1_generation/2_1_generated_stage_1",
        "2_1_generation/2_1_generated_stage_2",
    ],
    "2.2 知识均衡检查与修正": ["2_1_generation/2_2_balanced"],
    "3.1 题意模糊检查": ["3_1_ambiguity_cleaned"],
    "3.2 题意模糊修正": ["3_2_ambiguity_refined"],
    "3.3 考察领域检查": ["3_3_domain_cleaned"],
    "3.4 考察领域修正": ["3_4_domain_refined"],
    "3.5 去除重复题目": ["3_5_deduplicated"],
    "3.6 题库增强": ["3_6_synthesized"],
    "3.7 多语言翻译": ["3_7_translated"],
    "3.8 选择题格式检查": ["3_8_mcq_verified"],
}


def _wipe_task_dir(task_dir: str, keep: tuple[str, ...] = ("input.pdf", "config.yaml")) -> None:
    """删除 task_dir 下除 keep 之外的所有内容（包括 progress.json / runner.log / 各 stage 子目录）。

    keep 必须包含 webui 向导写入的任务级配置 `config.yaml`，否则 `--reset` 会把它一起删掉，
    导致 `_build_config_with_overrides` 静默回退到全局 edu_config.yaml，重跑时丢失
    subject/grade/difficulty/operators 等任务专属配置。
    """
    import shutil

    if not os.path.isdir(task_dir):
        return
    keep_set = {k.lower() for k in keep}
    for entry in os.listdir(task_dir):
        if entry.lower() in keep_set:
            continue
        full = os.path.join(task_dir, entry)
        try:
            if os.path.isdir(full) and not os.path.islink(full):
                shutil.rmtree(full, ignore_errors=True)
            else:
                os.remove(full)
        except Exception as e:
            print(f"[wipe] 跳过 {full}: {e}", flush=True)


def _wipe_stage_outputs(task_dir: str, stage_name: str) -> None:
    """递归删除指定 stage 在 task_dir 下登记的产物目录，再重建为空目录。"""
    import shutil

    rels = _STAGE_OUTPUT_DIRS.get(stage_name, [])
    for rel in rels:
        full = os.path.join(task_dir, rel.replace("/", os.sep))
        if os.path.isdir(full):
            try:
                shutil.rmtree(full, ignore_errors=True)
            except Exception as e:
                print(f"[wipe-stage] 跳过 {full}: {e}", flush=True)
        try:
            os.makedirs(full, exist_ok=True)
        except Exception as e:
            print(f"[wipe-stage] 无法重建 {full}: {e}", flush=True)


def _load_preserved_states(task_dir: str, resume_from: str) -> dict[str, dict]:
    """
    读旧 progress.json，把所有 status==succeeded 且名次在 resume_from 之前的 stage 状态保留下来，
    供 ProgressTracker 回填，UI 续跑后仍能看到历史时间戳。
    """
    p = os.path.join(task_dir, "progress.json")
    if not os.path.isfile(p):
        return {}
    try:
        with open(p, "r", encoding="utf-8") as f:
            old = json.load(f)
    except Exception:
        return {}
    stage_order = [s[0] for s in STAGES]
    try:
        cutoff_idx = stage_order.index(resume_from)
    except ValueError:
        cutoff_idx = len(stage_order)
    preserved: dict[str, dict] = {}
    for s in old.get("stages", []) or []:
        name = s.get("name")
        if not name or s.get("status") != "succeeded":
            continue
        if name not in stage_order:
            continue
        if stage_order.index(name) >= cutoff_idx:
            continue
        preserved[name] = {
            "started_at": s.get("started_at"),
            "finished_at": s.get("finished_at"),
        }
    return preserved


def _pdf_to_images(task_name: str, task_dir: str, input_pdf: str, dpi: int = 100) -> None:
    """
    将 input.pdf 转为 <img_dir>/<task_name>/page_NNN.png，供 MinerU OCR 扫描。
    依赖 pdf2image + Poppler；poppler_path 通过环境变量 POPPLER_PATH 注入（也允许 PATH 已配好）。
    """
    from pdf2image import convert_from_path

    img_dir = _abs_under(task_dir, _LAYOUT["img_dir"])
    book_dir = os.path.join(img_dir, task_name)
    os.makedirs(book_dir, exist_ok=True)

    # 已有 png 且数量 > 0 时跳过（resume 友好）
    existing = [f for f in os.listdir(book_dir) if f.lower().endswith(".png")]
    if existing:
        print(f"[pdf->img] 已有 {len(existing)} 张 png，跳过转换", flush=True)
        return

    poppler_path = os.getenv("POPPLER_PATH", "").strip().strip('"').strip("'")
    if poppler_path and not os.path.isdir(poppler_path):
        print(f"[pdf->img] 警告：POPPLER_PATH 不是目录：{poppler_path}", flush=True)
        poppler_path = ""

    kwargs: dict = {"dpi": dpi}
    if poppler_path:
        kwargs["poppler_path"] = poppler_path

    print(f"[pdf->img] 转换 {input_pdf} -> {book_dir} (dpi={dpi}, poppler={poppler_path or 'PATH'})", flush=True)
    images = convert_from_path(input_pdf, **kwargs)
    total = len(images)
    width = max(3, len(str(total)))
    for i, img in enumerate(images, 1):
        out = os.path.join(book_dir, f"page_{str(i).zfill(width)}.png")
        img.save(out, "PNG")
    print(f"[pdf->img] 完成，共 {total} 页", flush=True)


def _build_config_with_overrides(task_dir: str):
    """加载配置（task_dir/config.yaml 优先于全局 edu_config.yaml）→ 兜底 default_config → 覆写所有路径到 task_dir。

    优先级：
      1. task_dir/config.yaml（M2 起 webui 向导写入此处，每个任务一份）
      2. dataflow_edu/config/edu_config.yaml（旧的全局配置）
      3. default_config()
    """
    from dataflow_edu.config.loader import get_config_path, load_config
    from dataflow_edu.config.schema import default_config

    task_cfg_path = os.path.join(task_dir, "config.yaml")
    if os.path.isfile(task_cfg_path):
        try:
            # strict=True：让 YAML 解析错误抛出，避免 load_config 静默吞掉异常
            # 后误以为加载成功（fallback 链就完全走不到了）。
            config = load_config(
                path=task_cfg_path,
                project_root=_PROJECT_ROOT,
                strict=True,
            )
            print(f"[runner] 使用任务专用配置: {task_cfg_path}", flush=True)
        except Exception as e:
            print(f"[runner] 读取 {task_cfg_path} 失败 ({e})，回退到全局配置", flush=True)
            config = load_config(project_root=_PROJECT_ROOT)
            cfg_path = get_config_path(_PROJECT_ROOT)
            if not os.path.isfile(cfg_path):
                config = default_config()
    else:
        config = load_config(project_root=_PROJECT_ROOT)
        cfg_path = get_config_path(_PROJECT_ROOT)
        if not os.path.isfile(cfg_path):
            config = default_config()
    # 兜底所有缺失的算子条目
    base = default_config()
    for k, v in base.operators.items():
        config.operators.setdefault(k, v)
    _override_config_paths(config, task_dir)
    return config


def _patch_pipeline_module_for_task(
    task_dir: str,
    disabled_stages: "set[str] | None" = None,
) -> None:
    """
    将 dataflow_edu.edu_data_pipeline 模块内的 _PROJECT_ROOT-relative 配置加载，
    替换为我们已经 override 好的同一份 config（避免每个 run_* 重新 load 配置时丢失覆写）。

    disabled_stages 非空时，重新对已 cached 的 config 调用一次带 disabled_stages 的
    _override_config_paths，确保 3.x 链路的 input_dir 动态穿透跳过的步骤。
    """
    from dataflow_edu import edu_data_pipeline as edp
    from dataflow_edu.config import loader as _loader

    cached = _build_config_with_overrides(task_dir)
    # 用 disabled_stages 重算一次路径（_build_config_with_overrides 里已调用了一次不带
    # disabled_stages 的版本，这里覆盖那次的结果）
    if disabled_stages:
        _override_config_paths(cached, task_dir, disabled_stages=disabled_stages)

    def _patched_load_config(project_root: str | None = None):
        return cached

    # 让所有 run_* 内的 load_config 调用都拿到我们改写过路径的 config
    edp.load_config = _patched_load_config  # type: ignore[assignment]
    _loader.load_config = _patched_load_config  # type: ignore[assignment]

    # default_config 也覆写为返回同一份 config，避免某些算子在 cfg 缺字段时
    # 走 default_config().operators[...] 取到原始相对路径
    def _patched_default_config():
        return cached

    edp.default_config = _patched_default_config  # type: ignore[assignment]
    from dataflow_edu.config import schema as _schema

    _schema.default_config = _patched_default_config  # type: ignore[assignment]


def _verify_stage_output(task_dir: str, name: str) -> tuple[bool, str]:
    """
    依据 _STAGE_SENTINELS 校验阶段产出。返回 (ok, msg)。
    没有定义 sentinel 的阶段视为通过。
    """
    import glob

    pattern = _STAGE_SENTINELS.get(name)
    if not pattern:
        return True, ""
    full = os.path.join(task_dir, pattern.replace("/", os.sep))
    matches = glob.glob(full)
    if matches:
        return True, f"{len(matches)} file(s) matched"
    return False, f"no output matched {pattern!r} under task dir"


def _run_stage(
    progress: ProgressTracker,
    name: str,
    fn: Callable[[], None],
    task_dir: str,
) -> bool:
    print(f"\n========== [stage start] {name} ==========", flush=True)
    progress.stage_start(name)
    t0 = time.time()
    try:
        fn()
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        traceback.print_exc()
        progress.stage_fail(name, err)
        print(f"========== [stage FAIL]  {name}: {err} ==========", flush=True)
        return False

    elapsed = time.time() - t0
    ok, msg = _verify_stage_output(task_dir, name)
    if not ok:
        # 算子通常在缺输入时只 logger.warning + return False；这里把它升级成阶段失败，
        # 否则 UI 上一连串 "瞬间成功" 会掩盖真问题。
        err = f"stage produced no output: {msg}"
        progress.stage_fail(name, err)
        print(f"========== [stage FAIL]  {name}  ({elapsed:.1f}s): {err} ==========", flush=True)
        return False
    progress.stage_succeed(name)
    print(f"========== [stage ok]    {name}  ({elapsed:.1f}s) [{msg}] ==========", flush=True)
    return True


# ============================================================
# 6) main
# ============================================================


def _write_task_meta(task_dir: str, pdf_path: str) -> None:
    """提取 PDF 页数，写入 task_dir/task_meta.json，供后端 ETA 接口读取。"""
    meta: dict[str, Any] = {}
    try:
        import pypdf  # type: ignore[import]
        with open(pdf_path, "rb") as f:
            reader = pypdf.PdfReader(f)
            meta["pdf_pages"] = len(reader.pages)
    except Exception:
        try:
            # 回退：从文件名暗示的类似大小估算不靠谱，直接跳过
            pass
        except Exception:
            pass
    meta_path = os.path.join(task_dir, "task_meta.json")
    try:
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False)
    except Exception as e:
        print(f"[runner] write task_meta failed: {e}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser("dataflow_edu.task_runner")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--uid", required=True)
    parser.add_argument("--task-dir", required=True)
    parser.add_argument("--input-pdf", required=True)
    parser.add_argument("--task-name", default="")
    parser.add_argument(
        "--resume-from",
        default="",
        help="续跑：从该 stage 开始，之前 succeeded 的 stage 直接跳过；必须是 STAGES 里的完整阶段名",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="从头重跑：清掉 task_dir 下除 input.pdf 之外的所有内容后再开始",
    )
    args = parser.parse_args()

    # 强制非交互模式
    os.environ["DATAFLOW_NONINTERACTIVE"] = "1"
    _install_input_patch()

    task_dir = os.path.abspath(args.task_dir)
    os.makedirs(task_dir, exist_ok=True)
    task_name = (args.task_name or os.path.splitext(os.path.basename(args.input_pdf))[0]).strip() or "task"
    # 教材名只允许文件系统友好字符：去除路径分隔符，限制长度
    safe_name = "".join(c for c in task_name if c not in '\\/:*?"<>|').strip() or "task"

    stage_names = [s[0] for s in STAGES]

    # ── 读取用户在向导中选择的步骤白名单 ──────────────────────────────────────
    # 强制不可跳过的步骤（OCR + 生成）
    _MANDATORY = {"1.1 PDF转图片", "1.2 文字识别", "2.1 题目生成"}
    _disabled_stages: set[str] = set()
    _task_cfg_path = os.path.join(task_dir, "config.yaml")
    if os.path.isfile(_task_cfg_path):
        try:
            import yaml as _yaml_mod
            with open(_task_cfg_path, encoding="utf-8") as _f:
                _raw_cfg = _yaml_mod.safe_load(_f) or {}
            if isinstance(_raw_cfg.get("enabled_stages"), list):
                _all_optional = {s[0] for s in STAGES} - _MANDATORY
                _enabled_set = {n for n in _raw_cfg["enabled_stages"] if isinstance(n, str)}
                _disabled_stages = _all_optional - _enabled_set
                if _disabled_stages:
                    print(
                        f"[runner] 用户禁用步骤：{sorted(_disabled_stages)}",
                        flush=True,
                    )
        except Exception as _e:
            print(f"[runner] 读取 enabled_stages 失败 ({_e})，所有步骤全部执行", flush=True)

    # --reset 与 --resume-from 互斥；--reset 优先生效
    resume_from = (args.resume_from or "").strip()
    if args.reset:
        if resume_from:
            print("[runner] --reset 与 --resume-from 同时提供，忽略 --resume-from", flush=True)
            resume_from = ""
        _wipe_task_dir(task_dir)

    preserved: dict[str, dict] = {}
    if resume_from:
        if resume_from not in stage_names:
            print(f"[runner] 未知的 --resume-from={resume_from!r}，回退为完整运行", flush=True)
            resume_from = ""
        else:
            preserved = _load_preserved_states(task_dir, resume_from)
            # 清掉续跑起点 stage 的产物，避免半成品干扰算子内部 skip_existing 判断
            _wipe_stage_outputs(task_dir, resume_from)

    progress = ProgressTracker(
        task_dir,
        args.task_id,
        safe_name,
        stage_names,
        preserved_states=preserved,
        disabled_stages=_disabled_stages,
    )

    # 尝试提取 PDF 页数并写入 task_meta.json，供 ETA 估算使用
    _write_task_meta(task_dir, os.path.abspath(args.input_pdf))

    # 注入配置 + LLM 非交互初始化（在所有 run 之前完成）
    # 传入 disabled_stages，使 _override_config_paths 动态计算 3.x 链路 input_dir
    try:
        _patch_pipeline_module_for_task(task_dir, disabled_stages=_disabled_stages)
    except Exception as e:
        progress.stage_fail(stage_names[0], f"config inject: {e}")
        return 2

    try:
        _init_llm_noninteractive()
    except Exception as e:
        progress.stage_fail(stage_names[0], f"llm init: {e}")
        return 2

    from dataflow_edu import edu_data_pipeline as edp
    from dataflow_edu.serving.llm_client import get_total_tokens

    exit_code = 0
    try:
        for name, fn_name in STAGES:
            if name in preserved:
                print(f"========== [stage skip-preserved] {name} ==========", flush=True)
                continue
            if name in _disabled_stages:
                # ProgressTracker 初始化时已标记为 skipped，无需再次调用
                print(f"========== [stage skip-disabled] {name} ==========", flush=True)
                continue
            if fn_name is None:
                if name == "1.1 PDF转图片":
                    ok = _run_stage(
                        progress,
                        name,
                        lambda: _pdf_to_images(safe_name, task_dir, os.path.abspath(args.input_pdf)),
                        task_dir,
                    )
                else:
                    progress.stage_skip(name, "no handler")
                    continue
            else:
                fn = getattr(edp, fn_name, None)
                if not callable(fn):
                    progress.stage_skip(name, f"missing handler {fn_name}")
                    continue
                ok = _run_stage(progress, name, fn, task_dir)
            if not ok:
                exit_code = 1
                break

        if exit_code == 0:
            progress.finish_ok()
    finally:
        # 无论成功/失败都写 token 用量，供服务端入库
        try:
            usage_path = os.path.join(task_dir, "task_usage.json")
            with open(usage_path, "w", encoding="utf-8") as _uf:
                json.dump({"total_tokens": get_total_tokens()}, _uf)
        except Exception as _ue:
            print(f"[runner] write task_usage.json failed: {_ue}", flush=True)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
