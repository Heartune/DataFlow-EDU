Create a presentation slide image following these guidelines:

## Image Specifications
- **Type**: Presentation slide | **Aspect Ratio**: 16:9 | **Style**: Professional scientific academic

## Core Principles
- Clean scientific illustration; NO realistic/photographic elements; NO slide numbers/footers/logos
- Language: Chinese (except "Execute Operator", "Judge Operator", "LLM")

## STYLE_INSTRUCTIONS

Design Aesthetic: Academic scientific illustration with clean digital precision. Two-module evaluation system diagram with capability heatmap output.

Background: Off-White (#FAFAFA). Typography: Bold serif headlines; sans-serif labels.

Color Palette: Text #1E293B | Teal #0D9488 | Blue #3B82F6 | Purple #8B5CF6 | Amber #F59E0B | Red #EF4444 | Green #22C55E | Gray #475569

Style Rules: Precise line weights; labeled modules; heatmap with color gradient; directional arrows; no decorative art; no slide numbers.

---

## SLIDE CONTENT

**Slide 11 of 15 — Content**
**Filename**: 11-slide-execute-judge.png

**Narrative Goal**: 介绍阶段四的目标模型执行与LLM裁判评分，以及精细化能力图谱输出。

**Key Content**:
- Headline: 阶段四：Execute & Judge
- Sub-headline: 将Benchmark真正运行起来——模型作答与智能评判
- Execute Operator：接入待测大模型，批量输入题目，记录答案输出
- Judge Operator：LLM-as-a-Judge对比标准答案，规则评分+语义评分
- 输出：各维度得分矩阵 + 知识方向×能力层级精细化能力图谱

**Visual Description**:
Horizontal two-module flow diagram on off-white (#FAFAFA) background, with output heatmap on the right.

LEFT MODULE (blue #3B82F6 border): "Execute Operator"
  Inside: target LLM model icon (robot/brain) receiving "题目输入" arrow from left.
  Output arrow downward labeled "模型答案记录".
  Box label: "待测大模型 · 批量作答"

CENTER MODULE (purple #8B5CF6 border): "Judge Operator"
  Inside: Two inputs from left: "模型答案" (from Execute) + "标准答案" reference document.
  LLM Judge icon in center comparing both.
  Two scoring sub-modules shown: "规则评分（选择题）" and "LLM语义评分（主观题）"
  Output arrow pointing right labeled "得分".

RIGHT OUTPUT: "能力图谱" heatmap grid:
  Rows = knowledge domains (细胞结构, 物质运输, 遗传信息, 代谢过程) — 4 rows
  Columns = ability levels (记忆, 理解, 应用, 分析) — 4 columns
  Cells filled with color gradient: deep red (low score ~0.3) → yellow (medium ~0.6) → bright green (high ~0.9)
  Each cell shows a small numeric score.
  Grid labeled "知识方向 × 能力层级" with axis labels.

Connecting arrows between three components with labels.

**Layout**: split-screen — Left two-thirds: pipeline modules; right third: heatmap output.

Please use nano banana pro to generate the slide image based on the content provided above.
