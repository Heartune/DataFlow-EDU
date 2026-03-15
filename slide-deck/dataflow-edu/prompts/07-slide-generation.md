Create a presentation slide image following these guidelines:

## Image Specifications
- **Type**: Presentation slide | **Aspect Ratio**: 16:9 | **Style**: Professional scientific academic

## Core Principles
- Clean scientific illustration; NO realistic/photographic elements; NO slide numbers/footers/logos
- Language: Chinese (except "Stage 1", "Stage 2", "Context", "LLM")

## STYLE_INSTRUCTIONS

Design Aesthetic: Academic scientific illustration with clean digital precision. Two-stage flowchart with slot-mechanism diagram, precise labeling.

Background: Off-White (#FAFAFA). Typography: Bold serif headlines; sans-serif labels.

Color Palette: Text #1E293B | Teal #0D9488 | Blue #3B82F6 | Purple #8B5CF6 | Amber #F59E0B | Green #22C55E | Gray #475569

Style Rules: Precise line weights; numbered stages; directional arrows; label all components; no decorative art; no slide numbers.

---

## SLIDE CONTENT

**Slide 7 of 15 — Content**
**Filename**: 07-slide-generation.png

**Narrative Goal**: 深入介绍Generation Operator的两阶段生成机制和随机槽分布控制。

**Key Content**:
- Headline: 阶段二：Generation Operator
- Sub-headline: 两阶段LLM生成 + 随机槽机制精准控制分布
- 输入单元：每两页Markdown合并为一组Context
- Stage 1：LLM判断该Context最适合的知识方向（大类→小类分类）
- Stage 2：随机槽机制预分配能力层级与题型配额，LLM批量生成题目与答案
- 随机槽：精准保证分布均衡，无需后期补题

**Visual Description**:
Two-stage vertical flowchart on off-white (#FAFAFA) background, divided into upper and lower halves by a horizontal separator line.

TOP SECTION — Stage 1 (amber theme):
  Label badge "Stage 1" in bold amber (#F59E0B).
  Left: document icon "两页Markdown合并" → center: LLM box "知识方向分类器" (amber border) → right: taxonomy tag chip "大类：细胞结构 / 小类：细胞膜功能" in amber.
  Arrow flow left to right.

BOTTOM SECTION — Stage 2 (blue theme):
  Label badge "Stage 2" in bold blue (#3B82F6).
  Left input: taxonomy tag (from Stage 1) + "随机槽 Slot 机制" box:
    Inside Slot box: a small grid table showing pre-allocated quotas:
      Rows = ability levels (记忆/理解/应用/分析)
      Columns = question types (单选/填空/简答)
      Cells filled with small colored circles showing slot allocation
  Center: LLM generation box "题目生成器" (blue border) with prompt icon.
  Right: output stack showing "题目+答案" pairs in green (#22C55E).
  Arrow flow left to right.

Bottom annotation in gray: "随机槽机制确保分布精准均衡，题型写死不依赖LLM返回"

Academic precise flowchart, two-row layout, consistent element sizing.

**Layout**: split-screen — Upper half Stage 1, lower half Stage 2, clear separator.

Please use nano banana pro to generate the slide image based on the content provided above.
