Create a presentation slide image following these guidelines:

## Image Specifications
- **Type**: Presentation slide | **Aspect Ratio**: 16:9 | **Style**: Professional scientific academic

## Core Principles
- Clean scientific illustration; NO realistic/photographic elements; NO slide numbers/footers/logos
- Language: Chinese (except "LLM")

## STYLE_INSTRUCTIONS

Design Aesthetic: Academic scientific illustration with clean digital precision. Three-tier classification diagram with clear branching paths and quality thresholds.

Background: Light Blue-Gray (#F0F4F8). Typography: Bold serif headlines; sans-serif labels.

Color Palette: Text #1E293B | Teal #0D9488 | Blue #3B82F6 | Purple #8B5CF6 | Amber #F59E0B | Red #EF4444 | Green #22C55E | Gray #475569

Style Rules: Precise line weights; label all branches; threshold indicators; color-coded outcomes; no decorative art; no slide numbers.

---

## SLIDE CONTENT

**Slide 10 of 15 — Content**
**Filename**: 10-slide-llm-judge-cleaning.png

**Narrative Goal**: 深入解释LLM-as-a-Judge清洗机制的三级质量评分路由逻辑。

**Key Content**:
- Headline: LLM-as-a-Judge 清洗机制
- Sub-headline: 三级质量评分驱动的智能过滤与自动优化
- 低质量（分数 < 阈值L）：直接剔除
- 中质量（阈值L ≤ 分数 < 阈值H）：送入Refinement算子优化
- 高质量（分数 ≥ 阈值H）：直接保留，进入下一阶段
- 评判维度：二义性 · 领域相关性 · 答案正确性 · 表述清晰度

**Visual Description**:
Centered hub-and-branch diagram on light blue-gray (#F0F4F8) background.

LEFT: Input arrow labeled "待清洗题目" pointing right.

CENTER: Large purple (#8B5CF6) rounded rectangle "LLM Judge 裁判模型" with a gavel/scale icon inside. Below it: a horizontal quality score bar showing scale from 0 to 1, with two threshold markers: "阈值L=0.4" and "阈值H=0.7" as vertical dashed lines.

THREE OUTPUT BRANCHES from center (spreading right):

TOP BRANCH (green #22C55E): Score ≥ 0.7
  Arrow labeled "高质量" → Box "✓ 直接保留" → continues to next pipeline stage icon

MIDDLE BRANCH (amber #F59E0B): 0.4 ≤ Score < 0.7
  Arrow labeled "中质量" → Box "⟳ Refinement优化" with circular arrow → re-enters pipeline

BOTTOM BRANCH (red #EF4444): Score < 0.4
  Arrow labeled "低质量" → Box "✗ 剔除" with X mark → dead end

BOTTOM SECTION: Four evaluation dimension badges in a row:
  "二义性" (red), "领域相关性" (blue), "答案正确性" (green), "表述清晰度" (teal)
  Each badge has a small colored indicator bar showing evaluation criteria.

**Layout**: hub-spoke — Central judge module with three output branches, evaluation dimensions shown below.

Please use nano banana pro to generate the slide image based on the content provided above.
