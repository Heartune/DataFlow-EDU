# -*- coding: utf-8 -*-
r"""PDF 导出：复用 Word 排版结果，调 LibreOffice headless 转换。

策略：
1. 先用 word_exporter 生成 .docx（写到临时目录）。
2. 调 `libreoffice --headless --convert-to pdf` 把 .docx 转成 .pdf。
3. 把 .pdf 移动到 output_path。

设计要点：
- 不再用 docx2pdf（它强依赖 Win/Mac 上的 MS Word/Pages，CI/容器/Linux 都跑不通）。
- LibreOffice 转换默认输出到 --outdir，所以无法直接指定文件名；本模块捕获产物路径
  后再 rename 到目标 output_path。
- LibreOffice 的可执行名在不同平台不同：Linux 是 `libreoffice` / `soffice`；
  Windows 上常装在 `C:\Program Files\LibreOffice\program\soffice.exe`。
  优先读环境变量 LIBREOFFICE_BIN，找不到再 fallback。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Optional

from dataflow_edu.export.word_exporter import (
    SUPPORTED_VARIANTS,
    VARIANT_WITH_ANSWER,
    export_word,
)


def _resolve_libreoffice_bin() -> str:
    """定位 libreoffice/soffice 可执行文件。"""

    env = os.environ.get("LIBREOFFICE_BIN", "").strip()
    if env and Path(env).is_file():
        return env

    # PATH 里查
    for name in ("soffice", "libreoffice"):
        found = shutil.which(name)
        if found:
            return found

    # Windows 常见安装路径
    if sys.platform.startswith("win"):
        candidates = [
            r"C:\Program Files\LibreOffice\program\soffice.exe",
            r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
        ]
        for c in candidates:
            if Path(c).is_file():
                return c

    raise FileNotFoundError(
        "未找到 LibreOffice。请安装 LibreOffice 并把 soffice 放进 PATH，"
        "或设置环境变量 LIBREOFFICE_BIN 指向 soffice 可执行文件。"
    )


def _convert_docx_to_pdf(docx_path: Path, out_dir: Path, *, timeout: int = 180) -> Path:
    """调用 LibreOffice headless 把 docx 转 pdf。返回生成的 .pdf 路径。"""

    bin_path = _resolve_libreoffice_bin()
    out_dir.mkdir(parents=True, exist_ok=True)

    # LibreOffice 的 -env:UserInstallation 用来给本进程独立 profile，
    # 防止与桌面端 LibreOffice 抢锁导致 hang。
    profile_dir = (out_dir / ".lo_profile").resolve()
    profile_dir.mkdir(parents=True, exist_ok=True)
    user_inst = profile_dir.as_uri()  # file:///...

    cmd: List[str] = [
        bin_path,
        f"-env:UserInstallation={user_inst}",
        "--headless",
        "--norestore",
        "--nologo",
        "--nodefault",
        "--convert-to",
        "pdf",
        "--outdir",
        str(out_dir),
        str(docx_path),
    ]

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"LibreOffice 转换超时（{timeout}s）：{e}") from e

    if result.returncode != 0:
        raise RuntimeError(
            "LibreOffice 转换失败：\n"
            f"cmd={cmd}\n"
            f"stdout={result.stdout.decode('utf-8', errors='ignore')[:500]}\n"
            f"stderr={result.stderr.decode('utf-8', errors='ignore')[:500]}"
        )

    expected = out_dir / (docx_path.stem + ".pdf")
    if not expected.is_file():
        raise RuntimeError(
            f"LibreOffice 转换后未找到 PDF：{expected}\n"
            f"stdout={result.stdout.decode('utf-8', errors='ignore')[:500]}"
        )
    return expected


def export_pdf(
    task_dir: str | os.PathLike[str],
    output_path: str | os.PathLike[str],
    *,
    stage: str = "3_8_mcq_verified",
    lang: str = "zh",
    variant: str = VARIANT_WITH_ANSWER,
    task_name: Optional[str] = None,
) -> Path:
    """生成 PDF。先生成 docx，再走 LibreOffice 转换。"""

    if variant not in SUPPORTED_VARIANTS:
        raise ValueError(f"unsupported variant: {variant!r}")

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="edu_pdf_") as tmp:
        tmp_dir = Path(tmp)
        docx_tmp = tmp_dir / "export.docx"
        export_word(
            task_dir,
            docx_tmp,
            stage=stage,
            lang=lang,
            variant=variant,
            task_name=task_name,
        )
        pdf_tmp = _convert_docx_to_pdf(docx_tmp, tmp_dir)
        # 移动到目标位置（覆盖）
        if out.exists():
            out.unlink()
        shutil.move(str(pdf_tmp), str(out))

    return out
