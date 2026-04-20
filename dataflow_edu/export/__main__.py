# -*- coding: utf-8 -*-
"""CLI 入口：`python -m dataflow_edu.export ...`

供 WebUI 后端 spawn 使用。所有错误以非 0 退出码 + stderr JSON 输出，stdout
仅用于打印结果元信息（一行 JSON）。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from pathlib import Path

from dataflow_edu.export.json_exporter import export_json
from dataflow_edu.export.pdf_exporter import export_pdf
from dataflow_edu.export.word_exporter import (
    SUPPORTED_VARIANTS,
    VARIANT_WITH_ANSWER,
    export_word,
)


SUPPORTED_FORMATS = ("json", "word", "pdf")


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="dataflow_edu.export")
    p.add_argument("--task-dir", required=True, help="任务工作目录绝对路径")
    p.add_argument("--output", required=True, help="导出文件目标绝对路径")
    p.add_argument("--format", choices=SUPPORTED_FORMATS, required=True)
    p.add_argument(
        "--variant",
        choices=SUPPORTED_VARIANTS,
        default=VARIANT_WITH_ANSWER,
        help="word/pdf 排版变体；json 时忽略",
    )
    p.add_argument("--lang", choices=("zh", "en", "fr"), default="zh")
    p.add_argument("--stage", default="3_8_mcq_verified")
    p.add_argument("--task-name", default="", help="写入 Word/JSON 元信息")
    p.add_argument(
        "--keep-raw",
        action="store_true",
        help="JSON 导出时保留每题原始字段（含未 resolve 的多语言版本）",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    started = time.time()

    task_dir = Path(args.task_dir)
    if not task_dir.is_dir():
        print(
            json.dumps({"error": "task_dir_not_found", "task_dir": str(task_dir)}),
            file=sys.stderr,
        )
        return 2

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        if args.format == "json":
            written = export_json(
                task_dir,
                out_path,
                stage=args.stage,
                lang=args.lang,
                task_name=args.task_name or None,
                keep_raw=bool(args.keep_raw),
            )
        elif args.format == "word":
            written = export_word(
                task_dir,
                out_path,
                stage=args.stage,
                lang=args.lang,
                variant=args.variant,
                task_name=args.task_name or None,
            )
        elif args.format == "pdf":
            written = export_pdf(
                task_dir,
                out_path,
                stage=args.stage,
                lang=args.lang,
                variant=args.variant,
                task_name=args.task_name or None,
            )
        else:
            print(json.dumps({"error": "unknown_format"}), file=sys.stderr)
            return 2
    except Exception as exc:
        print(
            json.dumps(
                {
                    "error": "export_failed",
                    "type": type(exc).__name__,
                    "message": str(exc),
                    "trace": traceback.format_exc(),
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 1

    payload = {
        "ok": True,
        "format": args.format,
        "variant": args.variant,
        "lang": args.lang,
        "stage": args.stage,
        "output": str(written),
        "size_bytes": written.stat().st_size if written.is_file() else 0,
        "elapsed_ms": int((time.time() - started) * 1000),
    }
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
