# 05-slide-pipeline-stages.png

Create a 16:9 presentation slide image in Chinese.

## STYLE_INSTRUCTIONS

Design Aesthetic: 学术科学插图风格，用教科书级别的清晰图解呈现教师使用产品的完整路径。整体画面保持白底或浅蓝灰底、精确线条、明确标签和流程箭头，让“上传教材到生成题库”的过程像一张可阅读的教学工具说明图一样被理解。

Background:
  Texture: clean, no decorative texture; optional very subtle paper grain only for print feel
  Base Color: Off-White (#FAFAFA) or Light Blue-Gray (#F0F4F8)

Typography:
  Headlines: formal academic serif appearance, bold, authoritative, high contrast
  Body: readable academic body text; diagram labels use clean sans-serif appearance with consistent sizing

Color Palette:
  Primary Text: Dark Slate (#1E293B) - headlines and body
  Label Text: Medium Gray (#475569) - annotations and small labels
  Background: Off-White (#FAFAFA) - primary canvas
  Accent 1: Teal (#0D9488) - primary pipeline and source-material path
  Accent 2: Blue (#3B82F6) - system modules and WebUI layer
  Accent 3: Purple (#8B5CF6) - evaluation, judge, and intelligence layer
  Accent 4: Amber (#F59E0B) - human intervention and teacher workflow
  Alert: Red (#EF4444) - pain points and quality risks
  Positive: Green (#22C55E) - verified outputs and deliverables

Visual Elements:
  - Labeled modular components with precise rectangular or capsule modules
  - Directional arrows showing data, control, and review flow
  - Layered architecture diagrams with clean boundaries
  - Numbered step sequences and process summary boxes
  - Dataset, PDF, operator, judge, WebUI, and export icons rendered as simple scientific schematics
  - Small callout labels that explain key mechanisms without clutter

Density Guidelines:
  - Content per slide: dense but readable; 3-5 labeled components or 2-4 concise body points per slide
  - Whitespace: preserve clear gutters around diagrams and text; avoid crowding the title area
  - Element count: prefer one strong central diagram per slide, with compact annotations around it

Style Rules:
  Do: use consistent line weights, label all components clearly, show directional flow with arrows, keep diagrams precise, use restrained academic colors.
  Don't: use decorative illustrations, vague metaphors, noisy backgrounds, inconsistent icon styles, slide numbers, footers, or logos.

## SLIDE CONTENT

Slide number and filename: Slide 5 of 10, `05-slide-pipeline-stages.png`
Type: Content

Narrative goal:
解释教师在配置阶段能控制什么，让用户知道生成结果不是黑盒。

Visible text, exact Chinese copy:
- Headline: `配置越清楚，题目越贴合你的课堂`
- Sub-headline: `DataFlow-EDU 把教师要求转成结构化生成约束`
- Left panel labels: `学科与学段` `教学目标` `题目形态`
- Constraint labels: `核心素养` `知识方向` `难度分布` `题型数量`
- Arrow label: `教师要求 -> 生成约束`

Visual composition:
Create a control-panel-to-output diagram. On the left, draw a simplified teacher configuration panel with clean controls: subject selector, grade selector, competency tags, difficulty distribution bars, question type checkboxes. On the right, draw a structured question-bank grid: rows for `知识方向`, columns for `题型`, colored cells showing coverage and difficulty. In the center, place a strong arrow labeled `教师要求 -> 生成约束`.

Layout guidance:
Split composition 40/20/40: left config panel, center arrow, right distribution matrix. Headline and subtitle at top. Use blue for system controls, amber for teacher control, green for well-covered output. No footer or logo.

Text rendering requirements:
All visible text must be simplified Chinese except `DataFlow-EDU`. Use short UI labels only; avoid long paragraphs inside the figure.

Please use nano banana pro to generate the slide image based on the content provided above.
