# -*- coding: utf-8 -*-
"""Word 导出（python-docx）。

排版规则（与 plan.md M3 对齐）：
- 章节层级：category（H1）→ subcategory（H2）→ type（H3），全局连续编号。
- variant='with_answer'：每题正文 + 答案 + 解析 inline 排版。
- variant='blank'：主体只有题目+选项；分页符之后单独一个「参考答案与解析」区域，
  按相同的章节层级再次列出每题答案+解析（编号沿用主体）。
- lang='zh'|'en'|'fr'：题目/答案/解析字段已在 data_loader 里 resolve 完毕，
  本模块只关心排版。

中文字体在 docx 里非常坑：默认 Calibri 对中文不友好。这里强制全文（中文 east-asia
+ 西文 ascii/hAnsi）统一为「微软雅黑」，并同步覆盖 Title / Heading 1~3 等内置样式，
保证 docx 与下游 LibreOffice 转出的 PDF 字体一致。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from docx import Document
from docx.document import Document as DocxDocument
from docx.enum.text import WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt

from dataflow_edu.export.data_loader import (
    QuestionRecord,
    load_task_questions,
)


VARIANT_WITH_ANSWER = "with_answer"
VARIANT_BLANK = "blank"
SUPPORTED_VARIANTS = (VARIANT_WITH_ANSWER, VARIANT_BLANK)

# UI 上显示的章节标题文案（按语言）
_HEADINGS = {
    "zh": {
        "title": "试题",
        "answers_section": "参考答案与解析",
        "uncategorized": "未分类",
        "answer_label": "【答案】",
        "explanation_label": "【解析】",
        "type_label": "题型",
        "difficulty_label": "难度",
        "page_label": "出处",
    },
    "en": {
        "title": "Questions",
        "answers_section": "Answers & Explanations",
        "uncategorized": "Uncategorized",
        "answer_label": "[Answer] ",
        "explanation_label": "[Explanation] ",
        "type_label": "Type",
        "difficulty_label": "Difficulty",
        "page_label": "Source",
    },
    "fr": {
        "title": "Questions",
        "answers_section": "Réponses et explications",
        "uncategorized": "Non classé",
        "answer_label": "[Réponse] ",
        "explanation_label": "[Explication] ",
        "type_label": "Type",
        "difficulty_label": "Difficulté",
        "page_label": "Source",
    },
}


DEFAULT_FONT = "微软雅黑"

# 需要统一字体的内置样式（Title 是封面大标题；Heading 1~3 是章节）
_STYLES_TO_UNIFY = ("Normal", "Title", "Heading 1", "Heading 2", "Heading 3")


def _force_style_font(doc: DocxDocument, style_name: str, font_name: str) -> None:
    """把指定样式的中英文字体都改成 font_name。

    重点坑：python-docx 默认模板里 Title / Heading 1~3 的 rFonts 用的是
    **主题字体引用**（`asciiTheme="majorHAnsi"` / `eastAsiaTheme="majorEastAsia"` 等）。
    OOXML 里 `*Theme` 优先级高于具体名，不清掉它们，写多少具体字体名都没用——
    渲染器会去 theme1.xml 查主题字体，默认主题里 `majorEastAsia` 没设中文字体，
    Windows 上就会回落到 MS Gothic / MS Mincho。
    所以这里：1) 先删 4 个 *Theme 属性；2) 再写 4 个具体 slot。
    """

    try:
        style = doc.styles[style_name]
    except KeyError:
        return
    rPr = style.element.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.append(rFonts)
    for attr in ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme"):
        if rFonts.get(qn(attr)) is not None:
            del rFonts.attrib[qn(attr)]
    for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        rFonts.set(qn(attr), font_name)
    # python-docx 的 style.font.name 只会写 ascii / hAnsi，这里补一刀方便后续读取
    style.font.name = font_name


def _set_east_asia_font(doc: DocxDocument, font_name: str = DEFAULT_FONT) -> None:
    """把所有相关样式的中英文字体统一为 font_name（默认微软雅黑）。"""

    for style_name in _STYLES_TO_UNIFY:
        _force_style_font(doc, style_name, font_name)
    doc.styles["Normal"].font.size = Pt(11)


def _grouped(records: List[QuestionRecord]) -> List[Tuple[str, List[Tuple[str, List[Tuple[str, List[Tuple[int, QuestionRecord]]]]]]]]:
    """按 category → subcategory → type 三级分组，并在最内层附上「全局序号」。

    返回结构：
        [(category, [(subcategory, [(type, [(global_idx, record), ...]), ...]), ...]), ...]
    """

    out: "Dict[str, Dict[str, Dict[str, List[Tuple[int, QuestionRecord]]]]]" = {}
    for idx, r in enumerate(records, start=1):
        cat = r.category or "__uncat__"
        sub = r.subcategory or "__uncat__"
        typ = r.type or "__uncat__"
        out.setdefault(cat, {}).setdefault(sub, {}).setdefault(typ, []).append((idx, r))

    result = []
    for cat, sub_map in out.items():
        sub_list = []
        for sub, type_map in sub_map.items():
            type_list = [(typ, items) for typ, items in type_map.items()]
            sub_list.append((sub, type_list))
        result.append((cat, sub_list))
    return result


def _normalize_label(label: str, fallback: str) -> str:
    return fallback if label == "__uncat__" else label


def _format_options(options: Any) -> List[str]:
    """返回每个选项的渲染字符串。兼容 list[str] / dict[letter -> text]。"""

    if not options:
        return []
    if isinstance(options, list):
        rendered = []
        existing_prefixes = {
            f"{chr(c)}{sep}" for c in range(ord("A"), ord("H")) for sep in (".", "、", ":", "：")
        }
        for i, opt in enumerate(options):
            text = "" if opt is None else str(opt)
            stripped = text.lstrip()
            if stripped[:2] in existing_prefixes:
                rendered.append(stripped)
            else:
                rendered.append(f"{chr(ord('A') + i)}. {stripped}")
        return rendered
    if isinstance(options, dict):
        rendered = []
        for letter in sorted(options.keys()):
            text = options[letter]
            rendered.append(f"{letter}. {text}")
        return rendered
    return [str(options)]


def _add_question_body(doc: DocxDocument, idx: int, rec: QuestionRecord) -> None:
    """渲染单题的题干 + 选项（不含答案/解析）。"""

    p = doc.add_paragraph()
    p.add_run(f"{idx}. ").bold = True
    p.add_run(rec.question or "")

    for line in _format_options(rec.options):
        op = doc.add_paragraph(line)
        op.paragraph_format.left_indent = Pt(18)


def _add_question_answer(
    doc: DocxDocument,
    idx: int,
    rec: QuestionRecord,
    *,
    labels: Dict[str, str],
    include_question_repeat: bool,
) -> None:
    """渲染单题的答案+解析。

    `include_question_repeat=True` 时（学生卷答案区），先重复一行题号 + 题干截断，
    便于学生对照；with_answer 卷正文已经有题干，无需重复。
    """

    if include_question_repeat:
        head = doc.add_paragraph()
        head.add_run(f"{idx}. ").bold = True
        snippet = (rec.question or "").strip().replace("\n", " ")
        if len(snippet) > 60:
            snippet = snippet[:60] + "…"
        head.add_run(snippet)

    if rec.answer:
        p = doc.add_paragraph()
        p.add_run(labels["answer_label"]).bold = True
        p.add_run(rec.answer)
    if rec.explanation:
        p = doc.add_paragraph()
        p.add_run(labels["explanation_label"]).bold = True
        p.add_run(rec.explanation)


def export_word(
    task_dir: str | os.PathLike[str],
    output_path: str | os.PathLike[str],
    *,
    stage: str = "3_8_mcq_verified",
    lang: str = "zh",
    variant: str = VARIANT_WITH_ANSWER,
    task_name: Optional[str] = None,
) -> Path:
    """生成 .docx。"""

    if variant not in SUPPORTED_VARIANTS:
        raise ValueError(f"unsupported variant: {variant!r}, expected one of {SUPPORTED_VARIANTS}")
    labels = _HEADINGS.get(lang, _HEADINGS["zh"])

    records = load_task_questions(task_dir, stage=stage, lang=lang)

    doc = Document()
    _set_east_asia_font(doc)

    title = task_name or labels["title"]
    if variant == VARIANT_BLANK:
        title = f"{title} ({labels['title']})"
    h = doc.add_heading(title, level=0)
    h.alignment = 1  # center

    grouped = _grouped(records)

    # 题干主体
    for cat, sub_list in grouped:
        doc.add_heading(_normalize_label(cat, labels["uncategorized"]), level=1)
        for sub, type_list in sub_list:
            doc.add_heading(_normalize_label(sub, labels["uncategorized"]), level=2)
            for typ, items in type_list:
                doc.add_heading(_normalize_label(typ, labels["uncategorized"]), level=3)
                for idx, rec in items:
                    _add_question_body(doc, idx, rec)
                    if variant == VARIANT_WITH_ANSWER:
                        _add_question_answer(
                            doc, idx, rec, labels=labels, include_question_repeat=False
                        )
                    # 题与题间留个空行
                    doc.add_paragraph("")

    # 学生卷：分页 + 答案区
    if variant == VARIANT_BLANK and records:
        # 分页符
        p = doc.add_paragraph()
        p.add_run().add_break(WD_BREAK.PAGE)
        doc.add_heading(labels["answers_section"], level=0)
        for cat, sub_list in grouped:
            doc.add_heading(_normalize_label(cat, labels["uncategorized"]), level=1)
            for sub, type_list in sub_list:
                doc.add_heading(_normalize_label(sub, labels["uncategorized"]), level=2)
                for typ, items in type_list:
                    doc.add_heading(_normalize_label(typ, labels["uncategorized"]), level=3)
                    for idx, rec in items:
                        _add_question_answer(
                            doc, idx, rec, labels=labels, include_question_repeat=True
                        )
                        doc.add_paragraph("")

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out))
    return out
