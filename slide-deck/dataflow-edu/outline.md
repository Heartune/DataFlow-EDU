# Slide Deck Outline

**Topic**: DataFlow-EDU 端到端学科语料库与Benchmark生成管线
**Style**: scientific
**Dimensions**: clean + cool + technical + dense
**Audience**: 高校评审/导师
**Language**: 中文
**Slide Count**: 15 slides
**Generated**: 2026-03-15 00:00

---

<STYLE_INSTRUCTIONS>
Design Aesthetic: Academic scientific illustration style with clean digital precision and cool analytical palette. Precise technical diagrams with proper labeling, numbered sequences, and clear visual flow. Educational clarity with professional polish—think textbook-quality illustrations and academic journal figures, adapted for system architecture documentation.

Background:
  Texture: Clean, no texture—pure solid color backgrounds
  Base Color: Off-White (#FAFAFA) or Light Blue-Gray (#F0F4F8)

Typography:
  Headlines: Bold clean serif (Times New Roman style), authoritative and formal, suitable for academic publishing
  Body: Rounded sans-serif for bullet points and labels; serif for body paragraphs; consistent small size for hierarchy

Color Palette:
  Primary Text: Dark Slate (#1E293B) - headlines and body text
  Background: Off-White (#FAFAFA) - primary background
  Accent Teal: Teal (#0D9488) - primary pathway / pipeline flow
  Accent Blue: Blue (#3B82F6) - secondary pathway / modules
  Accent Purple: Purple (#8B5CF6) - tertiary elements / judge layer
  Accent Amber: Amber (#F59E0B) - membranes / configuration layer
  Alert Red: Red (#EF4444) - key emphasis / quality alerts
  Positive Green: Green (#22C55E) - outputs / positive results
  Label Gray: Medium Gray (#475569) - annotations and captions

Visual Elements:
  - Modular pipeline diagrams with labeled, color-coded operator boxes
  - Directional flow arrows showing data transformation stages
  - Numbered step sequences for multi-stage processes
  - Cross-section/layered architecture views
  - Structured comparison tables with clean borders
  - Key metric callout boxes with bold numbers
  - Process summary panels at bottom of slides
  - Clean icons representing operators (filter, transform, judge, generate)

Density Guidelines:
  - Content per slide: 3-5 key points or one focused diagram
  - Whitespace: Moderate—enough breathing room for academic readability
  - Element count: Balanced; dense enough to convey technical depth

Style Rules:
  Do: Use precise consistent line weights; label all components clearly; show directional flow with arrows; use numbered sequences; maintain grid alignment; use color coding consistently across slides
  Don't: Use decorative illustrations; create imprecise/artistic diagrams; omit labels; add slide numbers/footers/logos; use inconsistent visual language
</STYLE_INSTRUCTIONS>

---

## Slide 1 of 15

**Type**: Cover
**Filename**: 01-slide-cover.png

// NARRATIVE GOAL
建立项目的学术身份——一条面向高校评审的、工程化的学科数据集生产管线。

// KEY CONTENT
Headline: DataFlow-EDU
Sub-headline: 端到端学科语料库与Benchmark自动化生成管线
Body:
- 从原始教材PDF到高质量评测集的全生命周期方案
- 算子化 · 半自动化 · 低幻觉 · 多学科通用

// VISUAL
Scientific academic cover: centered composition on off-white background. Large bold serif title "DataFlow-EDU" in dark slate. Below: elegant subtitle in teal. A horizontal pipeline diagram spans the lower third—four labeled boxes (OCR → 生成 → 清洗 → 评测) connected by teal directional arrows, each box with a distinct color accent. Clean, journal-cover aesthetic with subtle blue-gray gradient panel behind the pipeline.

// LAYOUT
Layout: title-hero

---

## Slide 2 of 15

**Type**: Content
**Filename**: 02-slide-motivation.png

// NARRATIVE GOAL
说明学科大模型评测数据稀缺的痛点，建立研究动机。

// KEY CONTENT
Headline: 学科大模型能力评测面临数据困境
Sub-headline: 现有数据集构建方式的三大瓶颈
Body:
- 人工标注成本高昂：专业学科题目依赖领域专家，规模化极难
- 质量参差不齐：幻觉问题、题目二义性、答案错误普遍存在
- 题型与能力层级分布失衡：选择题堆砌，高阶推理题严重不足

// VISUAL
Three-panel scientific illustration on light blue-gray background. Each panel is a clean rectangular box with a colored header bar: red for "成本高", orange for "质量低", purple for "分布偏". Inside each panel: precise labeled diagram showing the problem—panel 1 shows a steep cost curve, panel 2 shows a quality scatter with outlier markers, panel 3 shows an imbalanced bar chart. Connecting arrows suggest these are compounding problems. Academic journal figure style with annotation labels.

// LAYOUT
Layout: three-columns

---

## Slide 3 of 15

**Type**: Content
**Filename**: 03-slide-project-scope.png

// NARRATIVE GOAL
明确DataFlow-EDU的核心定位：通用性、自动化、算子化的学科数据流水线。

// KEY CONTENT
Headline: DataFlow-EDU 的核心定位
Sub-headline: 基于丰富项目经验提炼的通用生产基础设施
Body:
- 输入：任意学科PDF教材（本次demo：高中生物必修一）
- 输出：均衡分布的低幻觉学科评测集与训练语料
- 特点：高度自动化、算子化、半自动（保留人工监控）
- 借鉴DataFlow算子化哲学，深度融合条件过滤与LLM-as-a-Judge

// VISUAL
Bridge diagram on off-white background. Left side: a PDF document icon labeled "原始教材 PDF" in amber. Right side: a structured dataset icon labeled "高质量评测集" in green. The bridge connecting them is a horizontal pipeline with four colored operator blocks. Below the bridge: three key property labels in teal callout boxes—"自动化", "算子化", "半自动人工监控". Clean scientific layout with precise line weights.

// LAYOUT
Layout: bridge

---

## Slide 4 of 15

**Type**: Content
**Filename**: 04-slide-architecture.png

// NARRATIVE GOAL
鸟瞰四阶段管线架构，建立整体认知框架。

// KEY CONTENT
Headline: 四阶段端到端管线架构
Sub-headline: 从文档解析到模型评测的完整算子链路
Body:
- 阶段一 Taxonomy & OCR：知识分类配置 + MinerU多模态解析
- 阶段二 Generation & Balancing：随机槽控制分布 + 批量题目生成
- 阶段三 Cleaning & Refinement：多维清洗算子组 + N-Gram去重
- 阶段四 Execute & Judge：目标模型作答 + LLM-as-a-Judge评判

// VISUAL
Horizontal linear pipeline diagram on off-white background. Four large labeled rectangular stages connected by bold teal arrows. Stage 1 (amber): "Taxonomy & OCR" with sub-labels "Config Manager" and "MinerU OCR". Stage 2 (blue): "Generation & Balancing" with sub-labels "Generator" and "Balancer". Stage 3 (purple): "Cleaning & Refinement" with sub-labels "Ambiguity" "Domain" "Dedup". Stage 4 (teal): "Execute & Judge" with sub-labels "Execute" "Judge". Each stage box has numbered operator icons. Academic flowchart style with consistent line weights.

// LAYOUT
Layout: linear-progression

---

## Slide 5 of 15

**Type**: Content
**Filename**: 05-slide-taxonomy-config.png

// NARRATIVE GOAL
介绍阶段一的Configuration Manager——类LlamaFactory的可视化配置系统。

// KEY CONTENT
Headline: 阶段一：Configuration Manager
Sub-headline: 双层知识体系与题型的灵活配置
Body:
- 知识方向：大类-小类双层架构（如：细胞结构 → 细胞膜功能）
- 能力层级：主层级-子层级双层（记忆、理解、应用、分析）
- 考察题型：单选、多选、填空、简答、论述
- 配置文件驱动Pipeline各Operator参数，类似LlamaFactory风格

// VISUAL
Hierarchical tree diagram on light blue-gray background. Root node "知识配置" in amber at top. Two main branches: left branch "知识方向" expanding into two levels (大类→小类, showing biology examples); right branch "能力层级" expanding into Bloom's taxonomy pyramid (记忆→理解→应用→分析). Bottom section: horizontal row of five colored "题型" capsules. Clean academic taxonomy chart with precise connection lines and consistent label sizing.

// LAYOUT
Layout: tree-branching

---

## Slide 6 of 15

**Type**: Content
**Filename**: 06-slide-mineru-ocr.png

// NARRATIVE GOAL
介绍MinerU OCR算子的多模态文档解析能力。

// KEY CONTENT
Headline: 阶段一：MinerU OCR Operator
Sub-headline: 批量多模态PDF解析，输出标准化Markdown
Body:
- 输入：WPS导出的高质量PDF转图片（每页一图）
- 处理：MinerU引擎批量API调用，提取文本+表格+图文对
- 输出：标准化Markdown格式，保留结构与语义
- 清洗：通用数据算子过滤乱码、噪声、低质量页面

// VISUAL
Scientific process diagram showing data transformation pipeline. Left: stack of document/image icons representing PDF pages. Center: large teal "MinerU OCR Engine" processing box with internal labeled sub-components (文本提取, 表格识别, 图文对提取). Right: clean markdown document icons representing structured output. Directional arrows with labeled data types flowing between components. Academic system diagram style with precise boxes and consistent icon sizing.

// LAYOUT
Layout: linear-progression

---

## Slide 7 of 15

**Type**: Content
**Filename**: 07-slide-generation.png

// NARRATIVE GOAL
深入介绍Generation Operator的两阶段生成机制和随机槽分布控制。

// KEY CONTENT
Headline: 阶段二：Generation Operator
Sub-headline: 两阶段LLM生成 + 随机槽机制精准控制分布
Body:
- 输入单元：每两页Markdown合并为一组Context
- Stage 1：LLM判断该Context最适合的知识方向（大类-小类）
- Stage 2：基于随机槽机制分配能力层级与题型，批量生成题目与答案
- 随机槽：预先计算各维度配额，随机选取填充，保证分布精准均衡

// VISUAL
Two-stage flowchart on off-white background. Top half (Stage 1): input document icon → LLM classification box with "知识方向判断" label → output taxonomy tag in amber. Bottom half (Stage 2): taxonomy tag + "随机槽 Slot" mechanism diagram (a grid showing pre-allocated slots by ability level and question type) → LLM generation box → output question-answer pairs in green. Color-coded flow: amber for stage 1, blue for stage 2. Precise scientific diagram with numbered steps.

// LAYOUT
Layout: split-screen

---

## Slide 8 of 15

**Type**: Content
**Filename**: 08-slide-balancing.png

// NARRATIVE GOAL
说明Balancing Operator在新版设计中的演变角色——从补题到分布诊断。

// KEY CONTENT
Headline: 阶段二：Balancing Operator
Sub-headline: 分布均衡诊断——从补题工具到知识覆盖顾问
Body:
- 原始功能：检测能力层级/题型分布偏差并自动补题
- 现状升级：随机槽机制已实现精准分布控制，补题需求基本消除
- 当前价值：分析知识方向覆盖度，提示用户补充欠缺学科语料
- 设计哲学：保留人工判断权，给建议而非强制生成

// VISUAL
Dashboard-style scientific slide. Top: a distribution bar chart showing question type balance (before/after comparison using binary-comparison layout within the slide). Bottom left: a pie chart showing knowledge direction coverage with highlighted sparse sector. Bottom right: a clean advisory text box in amber with "建议：增加[领域]语料" label. Precise academic data visualization style with teal and blue color coding.

// LAYOUT
Layout: dashboard

---

## Slide 9 of 15

**Type**: Content
**Filename**: 09-slide-cleaning-pipeline.png

// NARRATIVE GOAL
总览阶段三的多维清洗算子链路及其质量分级机制。

// KEY CONTENT
Headline: 阶段三：多维清洗算子流水线
Sub-headline: 从粗筛到精炼的分级质量管控
Body:
- 3.1 Ambiguity Cleaning：二义性检测，剔除低质量样本
- 3.2 Ambiguity Refinement：对中质量样本进行二义性优化
- 3.3 Domain Cleaning：领域相关性检测，剔除偏题低质样本
- 3.4 Domain Refinement：优化领域相关性的中质量样本
- 3.5 Deduplication：N-Gram相似度计算，清洗高度重复题目

// VISUAL
Vertical funnel diagram on light blue-gray background. At top: large raw dataset rectangle labeled "原始生成题库". The funnel narrows through five labeled filter stages, each represented by a horizontal colored band: red band (Ambiguity Clean), orange band (Ambiguity Refine), blue band (Domain Clean), teal band (Domain Refine), purple band (Dedup). Rejected samples shown as small red X marks exiting the sides. At bottom: clean green "高质量题库" output. Each stage shows quality threshold as a labeled threshold line. Academic scientific funnel/filter style.

// LAYOUT
Layout: funnel

---

## Slide 10 of 15

**Type**: Content
**Filename**: 10-slide-llm-judge-cleaning.png

// NARRATIVE GOAL
深入解释LLM-as-a-Judge清洗机制的三级质量评分逻辑。

// KEY CONTENT
Headline: LLM-as-a-Judge 清洗机制
Sub-headline: 三级质量评分驱动的智能过滤与优化
Body:
- 低质量样本（分数 < 阈值L）：直接剔除
- 中质量样本（阈值L ≤ 分数 < 阈值H）：送入Refinement算子优化
- 高质量样本（分数 ≥ 阈值H）：直接进入下一阶段
- 评判维度：二义性、领域相关性、答案正确性、表述清晰度

// VISUAL
Scientific three-tier classification diagram. Center: large LLM Judge module box in purple with input arrow from left. Three output branches emerge right: bottom branch in red labeled "低质量 → 剔除" with X icon; middle branch in amber labeled "中质量 → Refinement优化" with circular arrow; top branch in green labeled "高质量 → 保留" with checkmark. Below the diagram: four evaluation dimension icons in a row (二义性, 领域, 答案, 表述) with colored indicator bars. Precise scientific system diagram with clean line weights.

// LAYOUT
Layout: hub-spoke

---

## Slide 11 of 15

**Type**: Content
**Filename**: 11-slide-execute-judge.png

// NARRATIVE GOAL
介绍阶段四的目标模型执行与LLM裁判评分机制。

// KEY CONTENT
Headline: 阶段四：Execute & Judge
Sub-headline: 将Benchmark真正运行起来——模型作答与智能评判
Body:
- Execute Operator：接入待测大模型，批量输入题目，记录答案输出
- Judge Operator：调用LLM-as-a-Judge对比标准答案，计算得分
- 支持规则评分（选择题精确匹配）+ LLM评分（主观题语义理解）
- 输出：各维度得分矩阵、知识方向与能力层级的精细化能力图谱

// VISUAL
Two-module scientific diagram on off-white background. Left module (blue): "Execute Operator"—shows target LLM model icon receiving question inputs, outputting answer records. Right module (purple): "Judge Operator"—shows judge LLM comparing model answer vs. ground truth, outputting score. Below both modules: a capability heatmap grid (rows = knowledge domains, columns = ability levels) with colored score cells from red (low) to green (high). Arrows connect the three components linearly. Clean academic system diagram.

// LAYOUT
Layout: split-screen

---

## Slide 12 of 15

**Type**: Content
**Filename**: 12-slide-webui.png

// NARRATIVE GOAL
展示WebUI监控看板的设计理念——半自动化管线的人工监控接口。

// KEY CONTENT
Headline: WebUI 管线监控看板
Sub-headline: Vue 3 + Node.js 实现的半自动化人工监控界面
Body:
- 节点状态可视化：实时显示各算子执行状态（待机/运行/完成/错误）
- 数据统计面板：生成量、清洗率、各维度分布图表
- 交互式管线控制：选择执行特定算子，支持参数调整
- 设计参考：融合DataFlow WebUI功能与CNLaw-Bench stage_viewer风格

// VISUAL
Dashboard mockup on light blue-gray background in scientific style. Top section: horizontal pipeline with operator nodes shown as colored status circles (green=done, blue=running, gray=pending). Middle section: three metric panels—a bar chart for question type distribution, a donut chart for quality scores, a number metric "已生成 1,247 题". Bottom section: a clean control panel with operator selector buttons. Precise wireframe-style academic diagram with teal and blue color scheme.

// LAYOUT
Layout: dashboard

---

## Slide 13 of 15

**Type**: Content
**Filename**: 13-slide-prior-work.png

// NARRATIVE GOAL
展示项目负责人的丰富先验项目经验，建立可信度。

// KEY CONTENT
Headline: 先验项目经验支撑
Sub-headline: 四大学科语料库项目的实战经验积累
Body:
- ROBOTheory-79k：7.9万条机器人理论语料库，题目生成与二义性清洗
- CyberSecCorpus：规模1.6T网络安全专业语料库，大规模数据处理
- EE-Bench：电子信息学科数据集，多模态题型设计
- CNLaw-Bench：中国法律大模型评测基准，LLM-as-a-Judge评测体系

// VISUAL
Four-panel bento grid on off-white background. Each panel is a clean scientific information card: Panel 1 (teal): ROBOTheory-79k with "79,000条" large metric, robot/gear icon; Panel 2 (blue): CyberSecCorpus with "1.6T" large metric, shield icon; Panel 3 (purple): EE-Bench with circuit/chip icon; Panel 4 (amber): CNLaw-Bench with scales-of-justice icon and "LLM Judge" label. Each panel has 2-line description text. Academic data card style with consistent sizing.

// LAYOUT
Layout: bento-grid

---

## Slide 14 of 15

**Type**: Content
**Filename**: 14-slide-dataflow-integration.png

// NARRATIVE GOAL
说明DataFlow-EDU与DataFlow开源框架的深度技术融合，体现工程规范性。

// KEY CONTENT
Headline: 深度融合 DataFlow 算子化哲学
Sub-headline: 基于OperatorABC与OPERATOR_REGISTRY的标准化算子设计
Body:
- 复用DataFlow核心：get_logger、OperatorABC、OPERATOR_REGISTRY
- 通用LLM客户端：dataflow_edu.serving.llm_client模块共用
- 配置驱动：.llm_config.json统一管理API参数
- 命令行交互式Pipeline：edu_data_pipeline.py调度所有算子

// VISUAL
Venn-diagram style integration illustration on light blue-gray background. Left circle (blue): "DataFlow 框架" containing labeled components: OperatorABC, OPERATOR_REGISTRY, get_logger. Right circle (teal): "DataFlow-EDU 定制" containing: Generation, Cleaning, Judge operators. Overlapping center (purple): "复用接口" with llm_client, config, pipeline labels. Below: a simple code snippet box showing the sys.path integration pattern in monospace font. Academic software architecture diagram style.

// LAYOUT
Layout: venn-diagram

---

## Slide 15 of 15

**Type**: Back Cover
**Filename**: 15-slide-back-cover.png

// NARRATIVE GOAL
以"从一到无穷"的哲学收尾，强调DataFlow-EDU作为学科大模型基础设施的通用价值。

// KEY CONTENT
Headline: From One to Infinity
Sub-headline: DataFlow-EDU：赋能各类学科大模型能力跃升的数据基础设施
Body:
- 任意学科教材输入 → 高质量标准化评测集输出
- 算子化架构保障可扩展性与可复现性
- 开放生态：面向更多学科、更多语言、更多场景

// VISUAL
Clean scientific closing slide on off-white background. Large centered equation-style display: "1 → ∞" in bold teal serif font. Below: the subtitle text in dark slate. Bottom section: a minimal horizontal pipeline icon (simplified version of the full architecture) as a visual callback to the cover. Light blue-gray accent panel on the right side with the project tagline. Academic journal back-matter aesthetic—clean, confident, minimal.

// LAYOUT
Layout: title-hero
