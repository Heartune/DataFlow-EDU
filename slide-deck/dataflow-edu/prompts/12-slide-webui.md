Create a presentation slide image following these guidelines:

## Image Specifications
- **Type**: Presentation slide | **Aspect Ratio**: 16:9 | **Style**: Professional scientific academic

## Core Principles
- Clean scientific illustration; NO realistic/photographic elements; NO slide numbers/footers/logos
- Language: Chinese (except "Vue 3", "Node.js", "WebUI")

## STYLE_INSTRUCTIONS

Design Aesthetic: Academic scientific dashboard wireframe style. Clean UI mockup with chart panels and pipeline status indicators.

Background: Light Blue-Gray (#F0F4F8). Typography: Bold serif headlines; monospace-style sans-serif for UI labels.

Color Palette: Text #1E293B | Teal #0D9488 | Blue #3B82F6 | Purple #8B5CF6 | Amber #F59E0B | Green #22C55E | Gray #475569

Style Rules: Clean wireframe precision; consistent panel borders; status color coding; no decorative art; no slide numbers.

---

## SLIDE CONTENT

**Slide 12 of 15 — Content**
**Filename**: 12-slide-webui.png

**Narrative Goal**: 展示WebUI监控看板的功能设计——半自动化管线的人工监控与交互界面。

**Key Content**:
- Headline: WebUI 管线监控看板
- Sub-headline: Vue 3 + Node.js 实现的半自动化人工监控界面
- 节点状态可视化：实时显示各算子执行状态（待机/运行/完成/错误）
- 数据统计面板：生成量、清洗率、各维度分布图表
- 交互式管线控制：选择执行特定算子，支持参数调整

**Visual Description**:
Clean UI wireframe/mockup on light blue-gray (#F0F4F8) background. Resembles a browser window showing the dashboard (no browser chrome, just the content area).

SECTION 1 — Pipeline Status Bar (top of mockup):
  Horizontal row of 8 circular node status indicators connected by lines:
  "Config ●" (green=done), "OCR ●" (green), "生成 ●" (green), "均衡 ●" (amber=pending), "二义清洗 ◉" (blue=running, pulsing ring), "领域清洗 ○" (gray=waiting), "去重 ○" (gray), "评测 ○" (gray)
  Each node has a small label below.

SECTION 2 — Three metric panels (middle row):
  Left panel (teal border): Bar chart "题型分布" showing 5 question type bars
  Center panel (blue border): Donut chart "质量得分分布" with three segments (高/中/低)
  Right panel (purple border): Large number metric "已生成 1,247 题" with secondary "通过清洗 743 题"

SECTION 3 — Control panel (bottom strip):
  Row of clickable operator buttons in different colors:
  [OCR解析] [题目生成] [二义清洗] [领域清洗] [去重] [执行评测]
  Right side: a parameter config text area labeled "算子参数配置"

Title bar at very top of mockup: "DataFlow-EDU 管线监控" with connection status dot (green).

**Layout**: dashboard — Three-zone layout: status bar (top), metric panels (middle), controls (bottom).

Please use nano banana pro to generate the slide image based on the content provided above.
