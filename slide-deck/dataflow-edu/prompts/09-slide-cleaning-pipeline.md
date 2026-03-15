Create a presentation slide image following these guidelines:

## Image Specifications
- **Type**: Presentation slide | **Aspect Ratio**: 16:9 | **Style**: Professional scientific academic

## Core Principles
- Clean scientific illustration; NO realistic/photographic elements; NO slide numbers/footers/logos
- Language: Chinese

## STYLE_INSTRUCTIONS

Design Aesthetic: Academic scientific illustration with clean digital precision. Funnel/filter diagram showing data quality stages with clear rejection paths.

Background: Off-White (#FAFAFA). Typography: Bold serif headlines; sans-serif labels.

Color Palette: Text #1E293B | Teal #0D9488 | Blue #3B82F6 | Purple #8B5CF6 | Amber #F59E0B | Red #EF4444 | Green #22C55E | Gray #475569

Style Rules: Precise line weights; label all stages; rejection arrows pointing outward; numbered sequence; no decorative art; no slide numbers.

---

## SLIDE CONTENT

**Slide 9 of 15 — Content**
**Filename**: 09-slide-cleaning-pipeline.png

**Narrative Goal**: 总览阶段三的多维清洗算子链路及其分级质量管控机制。

**Key Content**:
- Headline: 阶段三：多维清洗算子流水线
- Sub-headline: 从粗筛到精炼的分级质量管控
- 3.1 Ambiguity Cleaning Operator：二义性检测，剔除低质量样本
- 3.2 Ambiguity Refinement Operator：优化中质量样本二义性
- 3.3 Domain Cleaning Operator：领域相关性检测，剔除偏题样本
- 3.4 Domain Refinement Operator：优化中质量样本领域相关性
- 3.5 Deduplication Operator：N-Gram相似度计算，清洗重复题目

**Visual Description**:
Vertical funnel diagram centered on off-white (#FAFAFA) background.

TOP: Wide rectangle labeled "原始生成题库" in dark slate, showing a count "~1,500题" — the raw dataset input.

FUNNEL BODY — Five horizontal filter bands narrowing downward:
  Band 1 (red #EF4444): "3.1 Ambiguity Cleaning" — left/right rejection arrows labeled "低质量 → 剔除" with small X marks
  Band 2 (amber #F59E0B): "3.2 Ambiguity Refinement" — circular arrows on sides labeled "中质量 → 优化"
  Band 3 (blue #3B82F6): "3.3 Domain Cleaning" — left/right rejection arrows labeled "偏题 → 剔除" with X marks
  Band 4 (purple #8B5CF6): "3.4 Domain Refinement" — circular arrows labeled "领域优化"
  Band 5 (teal #0D9488): "3.5 Deduplication" — left arrow labeled "重复题 → 剔除" with X marks

Each band has: operator number badge on left, operator name in center, threshold label on right (e.g., "阈值：0.7").

BOTTOM: Narrow output rectangle in green (#22C55E) labeled "高质量题库 ✓" with a count "~900题 (精炼后)".

Statistical summary below: "清洗率约 40% | 精炼率约 15% | 去重率约 8%"

**Layout**: funnel — Vertical narrowing from raw data (top) to refined output (bottom).

Please use nano banana pro to generate the slide image based on the content provided above.
