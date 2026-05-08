# Slide Deck Outline

**Topic**: DataFlow-EDU 项目介绍
**Style**: scientific
**Dimensions**: clean + cool + technical + dense
**Audience**: Teacher users
**Language**: zh
**Slide Count**: 10 slides
**Generated**: 2026-05-08 15:32

---

<STYLE_INSTRUCTIONS>
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
</STYLE_INSTRUCTIONS>

---

## Slide 1 of 10

**Type**: Cover
**Filename**: 01-slide-cover.png

// NARRATIVE GOAL
建立第一印象：DataFlow-EDU 是教师的智能题库生产工具，帮助把教材和课件快速转化为可检查、可编辑、可导出的题目。

// KEY CONTENT
Headline: DataFlow-EDU
Sub-headline: 给教师的教材出题、题库整理与测评资料生成工具
Body:
- 上传教材或课件
- 选择学科与要求
- 自动生成题目
- 在线审核编辑
- 导出教学资料

// VISUAL
中央是一条清晰的教师工作流示意图：左侧为“教材 PDF / PPT / 复习资料”，中间经过“AI 生成 + 质量检查 + 教师审核”，右侧输出“作业 / 练习 / 测验 / Word / PDF”。流程下方用小标签显示“把重复备题工作交给系统，把教学判断留给教师”。

// LAYOUT
Layout: title-hero
上方大标题居中；中部为横向教师使用流程图；底部用五个小型标签列出教师直接能感知的能力。

---

## Slide 2 of 10

**Type**: Content
**Filename**: 02-slide-problem-context.png

// NARRATIVE GOAL
说明教师用户的真实痛点：备题和改题耗时，AI 生成又经常不够贴合教材或难以直接使用。

// KEY CONTENT
Headline: 老师需要的不是“会出题”，而是“能用的题”
Sub-headline: 备课时间有限，题目还必须贴教材、可检查、能导出
Body:
- 手工出题慢：从教材整理知识点、设计题干、写选项和解析都很耗时。
- 普通 AI 出题不稳：容易偏离课本，难度、题型和知识点覆盖不好控。
- 最后仍要交付：老师需要能改、能查、能打印、能分享的成品资料。

// VISUAL
画面用四个红色风险节点组成教师痛点链：备题耗时、题目跑偏、质量难查、格式难交付。每个风险节点下方配一句教师视角说明，并用灰色箭头指向右侧“需要可控的出题产品”的结论框。

// LAYOUT
Layout: problem-chain
左到右痛点链，右侧结论框突出“可控、可审核、可导出的题库工具”。

---

## Slide 3 of 10

**Type**: Content
**Filename**: 03-slide-project-positioning.png

// NARRATIVE GOAL
给出产品定位：DataFlow-EDU 帮教师把自己的教学材料转成题库，而不是凭空生成一批题。

// KEY CONTENT
Headline: 上传你的教材，生成贴合课堂的题库
Sub-headline: 系统围绕上传材料工作，教师保留最终审核和修改权
Body:
- 输入：教材 PDF、PPT、复习资料或校本材料。
- 配置：选择学段、学科、知识方向、题型、难度和能力要求。
- 输出：题目、选项、答案、解析、知识点和可导出文档。

// VISUAL
中心是一个三段式产品价值图：教师材料 → DataFlow-EDU → 教学可用题库。输入端显示教材和课件，系统端显示“生成 + 检查 + 编辑”，输出端显示作业、练习、测验和题库档案。管线上方加小标签“贴合材料”“可控配置”“教师审核”。

// LAYOUT
Layout: lifecycle-flow
标题在上；中心横向产品价值图；下方三列简短说明输入、配置、输出。

---

## Slide 4 of 10

**Type**: Content
**Filename**: 04-slide-system-architecture.png

// NARRATIVE GOAL
用教师能理解的方式介绍产品使用路径，避免展开底层工程架构。

// KEY CONTENT
Headline: 5 步完成一次出题任务
Sub-headline: 从上传材料到导出文档，流程按教师日常工作组织
Body:
- 上传：选择教材 PDF、PPT 或复习资料。
- 配置：确定学科、题型、难度、知识点和数量。
- 生成：系统按材料生成题目、答案和解析。
- 审核：查看进度、预览样题、在线修改。
- 导出：生成 Word、PDF 或 JSON，用于课堂和备课组。

// VISUAL
绘制 5 步横向流程图：Upload → Configure → Generate → Review/Edit → Export。每一步用一个小界面示意框表示，并在下方写教师动作，例如“拖入课本 PDF”“选择高中生物”“预览最新题”“修改选项”“下载 Word”。

// LAYOUT
Layout: five-step-workflow
横向 5 步流程居中；每步上方为简洁图标，下方为一句教师动作；右侧绿色输出框突出“可直接使用”。

---

## Slide 5 of 10

**Type**: Content
**Filename**: 05-slide-pipeline-stages.png

// NARRATIVE GOAL
解释教师在配置阶段能控制什么，让用户知道生成结果不是黑盒。

// KEY CONTENT
Headline: 配置越清楚，题目越贴合你的课堂
Sub-headline: DataFlow-EDU 把教师要求转成结构化生成约束
Body:
- 学科与学段：选择初中/高中和具体科目，加载对应预设。
- 教学目标：设置核心素养、认知层级、知识方向和难度分布。
- 题目形态：控制题型、数量、答案解析和可选处理阶段。

// VISUAL
主图是一个“教师配置面板 → 生成约束”的示意图。左侧为简化配置面板，包含学科、题型、难度、核心素养等开关和选项；右侧为被约束的题库生成网格，显示题目按知识点、难度和题型分布。

// LAYOUT
Layout: control-panel-to-output
左侧配置面板，右侧题库分布矩阵；中间用箭头标注“教师要求 → 生成约束”。

---

## Slide 6 of 10

**Type**: Content
**Filename**: 06-slide-operator-system.png

// NARRATIVE GOAL
解释产品如何从教材中生成题目，并强调不是脱离材料的自由发挥。

// KEY CONTENT
Headline: 系统围绕教材内容生成，而不是凭空出题
Sub-headline: 教材解析、知识定位和题目生成连续工作
Body:
- 先读材料：解析 PDF/PPT 中的章节、段落、图文和知识内容。
- 再生成题：围绕材料中的概念、事实、关系和例子组织题干。
- 可追溯检查：教师可查看样题，并根据课堂需要继续修改。

// VISUAL
中心是“教材页 → 知识片段 → 题目卡片”的科学流程图。教材页中高亮几个知识区域，箭头指向结构化知识片段，再指向题目卡片，题目卡片包含题干、选项、答案、解析四个字段。

// LAYOUT
Layout: material-to-question
左侧教材页，中间知识抽取节点，右侧题目卡片；底部用一句话强调“传什么材料，就围绕什么材料生成”。

---

## Slide 7 of 10

**Type**: Content
**Filename**: 07-slide-quality-control.png

// NARRATIVE GOAL
回应教师最关心的问题：生成结果如何减少跑偏、重复、难度失衡和低质量题目。

// KEY CONTENT
Headline: 不止生成题目，还会做质量检查
Sub-headline: 贴合教材、分布均衡、去重清洗和格式检查共同把关
Body:
- 贴合教材：减少与上传材料无关的题目。
- 覆盖均衡：检查知识点、题型、难度和能力层级分布。
- 清洗修正：处理歧义表达、领域偏移、重复样本和格式问题。
- 质量评判：规则检查和 LLM Judge 辅助发现潜在问题。

// VISUAL
画面是一个质量控制“过滤柱”示意：左侧输入“初始生成题目”，依次通过“教材贴合”“分布均衡”“歧义清洗”“去重”“Judge 评判”“格式检查”六层过滤，右侧输出“待教师确认题库”。每层滤膜都有简短中文标签和颜色编码。

// LAYOUT
Layout: quality-funnel
中心为横向过滤流程；右侧绿色输出框；底部小表格列出教师可理解的质量维度。

---

## Slide 8 of 10

**Type**: Content
**Filename**: 08-slide-teacher-webui.png

// NARRATIVE GOAL
说明教师不是被动接受 AI 输出，而是在界面中持续观察、审核和编辑。

// KEY CONTENT
Headline: 教师保留最终把关权
Sub-headline: 生成过程可观察，题目结果可编辑，最终产物可确认
Body:
- 实时进度：看到 OCR、生成、清洗、评判等阶段状态。
- 样题预览：过程中查看最新题目，及时发现方向是否正确。
- 在线编辑：修改题干、选项、答案、解析、知识点和难度。
- 版本交付：确认后再导出教师版或学生空白版。

// VISUAL
绘制教师审核闭环图：系统生成 → 进度观察 → 样题预览 → 表格编辑 → 确认导出 → 课堂使用。图中用 amber 色强调“Teacher-in-the-loop”，用蓝色表示系统自动处理。

// LAYOUT
Layout: review-loop
中心为闭环流程；左侧系统自动处理，右侧教师审核编辑；底部放“AI 负责提效，教师负责判断”。

---

## Slide 9 of 10

**Type**: Content
**Filename**: 09-slide-product-maturity.png

// NARRATIVE GOAL
展示产品最终如何进入教学场景，强调教师能拿到可使用的交付物。

// KEY CONTENT
Headline: 导出的不是数据文件，而是教学资料
Sub-headline: 同一批题库可以服务作业、练习、测验和教研沉淀
Body:
- Word：适合教师继续编辑、排版、加入班级要求。
- PDF：适合直接打印、发布或作为学生练习材料。
- JSON：适合学校题库系统、二次开发或长期数据沉淀。

// VISUAL
中心是“一个题库，多种用途”的输出分叉图。题库卡片位于中心，向外分成 Word 讲义、PDF 练习、JSON 题库、只读分享链接、备课组复用五个方向。每个输出方向配一个简洁文件或场景图标。

// LAYOUT
Layout: output-branches
标题上；中心题库卡片；四周输出分叉；底部强调“生成结果能进入真实教学流程”。

---

## Slide 10 of 10

**Type**: Back Cover
**Filename**: 10-slide-back-cover.png

// NARRATIVE GOAL
收束教师用户视角的产品价值：节省重复备题时间，同时保留教师专业判断。

// KEY CONTENT
Headline: 把重复备题工作交给系统，把教学判断留给教师
Body:
- 适合场景：课后作业、单元练习、期末复习、随堂测验、校本题库建设。
- 教师收益：更快出题、更贴教材、更容易修改、更方便导出。
- 下一步：用自己的教材创建第一个任务，检查样题，再导出使用。

// VISUAL
中央为简洁闭环图：教材资料 → DataFlow-EDU → 可编辑题库 → 课堂使用 → 教师反馈。闭环中教师反馈箭头回到配置环节，表示产品服务的是持续备课与迭代，而不是一次性生成。

// LAYOUT
Layout: closing-loop
上方大标题；中部教师使用闭环图；底部三条产品收益，保持简洁有力。
