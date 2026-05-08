# 04-slide-system-architecture.png

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

Slide number and filename: Slide 4 of 10, `04-slide-system-architecture.png`
Type: Content

Narrative goal:
用教师能理解的方式介绍产品使用路径，避免展开底层工程架构。

Visible text, exact Chinese copy:
- Headline: `5 步完成一次出题任务`
- Sub-headline: `从上传材料到导出文档，流程按教师日常工作组织`
- Step labels: `上传` `配置` `生成` `审核` `导出`
- Action labels: `选择教材` `确定要求` `自动出题` `在线修改` `下载使用`
- Output badge: `可直接使用`

Visual composition:
Create a five-step workflow diagram across the center. Each step is a precise module with a small UI-style schematic:
1. `上传`: upload panel with PDF/PPT icon and drag area
2. `配置`: settings panel with subject, question type, difficulty sliders
3. `生成`: AI processing module making question cards
4. `审核`: teacher reviewing a question card and editing fields
5. `导出`: Word/PDF/JSON document outputs
Use numbered circular markers 1-5, but do not add slide numbers. End with a green output badge `可直接使用`.

Layout guidance:
Headline top-left, subtitle below. Center a clean horizontal five-step workflow. Use equal-sized modules with arrows between them. No footer or logo.

Text rendering requirements:
All visible text must be simplified Chinese except `PDF`, `PPT`, `Word`, `JSON`. Use large labels and concise action text.

Please use nano banana pro to generate the slide image based on the content provided above.
