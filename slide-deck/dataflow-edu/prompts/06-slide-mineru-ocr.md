Create a presentation slide image following these guidelines:

## Image Specifications
- **Type**: Presentation slide | **Aspect Ratio**: 16:9 | **Style**: Professional scientific academic

## Core Principles
- Clean scientific illustration; NO realistic/photographic elements; NO slide numbers/footers/logos
- Language: Chinese (except "MinerU", "Markdown")

## STYLE_INSTRUCTIONS

Design Aesthetic: Academic scientific illustration with clean digital precision. System dataflow diagrams with labeled processing modules and transformation arrows.

Background: Off-White (#FAFAFA). Typography: Bold serif headlines; sans-serif labels.

Color Palette: Text #1E293B | Teal #0D9488 | Blue #3B82F6 | Purple #8B5CF6 | Amber #F59E0B | Green #22C55E | Gray #475569

Style Rules: Precise line weights; label all components; directional arrows with data type labels; no decorative art; no slide numbers.

---

## SLIDE CONTENT

**Slide 6 of 15 — Content**
**Filename**: 06-slide-mineru-ocr.png

**Narrative Goal**: 介绍MinerU OCR算子的多模态PDF解析能力与数据清洗流程。

**Key Content**:
- Headline: 阶段一：MinerU OCR Operator
- Sub-headline: 批量多模态PDF解析，输出标准化Markdown语料
- 输入：WPS导出的PDF转图片（每页一图，批量处理）
- 核心引擎：MinerU批量API，提取文本 + 表格 + 图文对
- 清洗：通用数据算子过滤乱码、噪声、低质量页面
- 输出：结构化Markdown，保留章节层级与语义

**Visual Description**:
Horizontal process flow diagram on off-white (#FAFAFA) background.

Three main components connected by labeled arrows:

LEFT — Input stack:
  A vertical stack of document/image icons representing PDF pages.
  Label: "PDF页面图片" in amber (#F59E0B).
  Small annotation: "WPS导出 · 批量处理"

CENTER — Processing engine (large box):
  Large teal (#0D9488) bordered rectangle labeled "MinerU OCR Engine" at top.
  Inside: three horizontally arranged sub-modules in smaller boxes:
    "文本提取" (blue), "表格识别" (purple), "图文对提取" (amber)
  Below sub-modules: a filter/cleaning layer box labeled "通用清洗算子" in gray with funnel icon.
  Arrow flows top-to-bottom within the box.

RIGHT — Output:
  Clean document icon stack in green (#22C55E).
  Label: "标准化Markdown"
  Small annotation: "保留章节结构与语义"

Arrows between components:
  Left→Center: "批量图片输入" labeled arrow
  Center→Right: "结构化输出" labeled arrow

Below entire diagram: four quality metrics in small label boxes:
"乱码过滤 ✓", "噪声清洗 ✓", "低质页面剔除 ✓", "语义完整 ✓"

Academic technical system diagram with consistent line weights.

**Layout**: linear-progression — Three-stage horizontal flow with sub-components visible inside center module.

Please use nano banana pro to generate the slide image based on the content provided above.
