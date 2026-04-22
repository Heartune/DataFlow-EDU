# -*- coding: utf-8 -*-
"""
``python -m dataflow_edu.competency_suggest --subject ... --book ... --needs ...``

按 agent_notes.md「webui」一节约定：
    stdout 仅输出一行结果 JSON：``{"ok": true, "competencies": [...]}``
    stderr 在失败时输出一行错误 JSON：``{"ok": false, "error": "..."}``
不掺其它日志，方便 Express 子进程直接 ``JSON.parse(stdout.trim())``。
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from dataflow_edu.competency_suggest.core import SuggestError, suggest_competencies


def _emit_ok(payload: dict) -> int:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
    sys.stdout.flush()
    return 0


def _emit_err(code: str, message: Optional[str] = None) -> int:
    sys.stderr.write(
        json.dumps(
            {"ok": False, "error": code, "message": message or code},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        + "\n"
    )
    sys.stderr.flush()
    return 1


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(prog="dataflow_edu.competency_suggest")
    parser.add_argument("--subject", required=True, help="学科名（与 preset 一致）")
    parser.add_argument("--book", required=True, help="教材名")
    parser.add_argument("--needs", default="", help="教师个性化需求自由文本，<=500 字")
    parser.add_argument("--model", default=None, help="覆盖 zgca 模型名（可选）")
    parser.add_argument("--max-tokens", type=int, default=2048)
    parser.add_argument("--temperature", type=float, default=0.3)
    args = parser.parse_args(argv)

    try:
        items = suggest_competencies(
            args.subject,
            args.book,
            args.needs,
            model=args.model,
            max_tokens=args.max_tokens,
            temperature=args.temperature,
        )
    except SuggestError as e:
        return _emit_err(e.code, e.message)
    except Exception as e:  # noqa: BLE001
        return _emit_err("internal_error", f"{type(e).__name__}: {e}")

    return _emit_ok({"ok": True, "competencies": items})


if __name__ == "__main__":
    raise SystemExit(main())
