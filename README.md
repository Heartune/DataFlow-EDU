# 🌟DataFlow-EDU: 端到端学科语料库&Benchmark生成

> From One to Infinity 🌈
> Github Repo: <link>https://github.com/Heartune/DataFlow-EDU</link>

## 核心定位说明

基于我在包含7.9万条语料的机器人理论语料库ROBOTheory-79k、规模1.6T网络安全专业语料库CyberSecCorpus、电子信息学科数据集EE-Bench、中国法律大模型评测基准CNLaw-Bench方面的丰富构建经验，我的核心目标是打造 **DataFlow-EDU**——一条高度自动化、算子化且具备通用性的「学科数据集与评测基准（Benchmark）」生产管线。该管线贯穿从「原始教材输入」到「高质量结构化题库输出」的全生命周期。它不仅包含基于 MinerU 的多模态文档解析、切片式题库生成与题型动态均衡模块，更深度融入了目标团队 DataFlow 的算子化清洗哲学。通过灵活串联条件过滤、领域对齐 与基于 Question Verify 的 LLM-as-a-Judge 多维能力审阅等定制化算子，最终实现自动化、批量化地生产低幻觉、高质量、均衡分布的学科评测集与 SFT 训练语料，成为赋能各类学科大模型能力跃升的基础设施。这套系统支持包括教材在内的任意PDF教学资源输入，这里我将以高中生物教材（PDF格式）作为资源，进行项目demo演示。

---

## DataFlow-EDU 方案设计图景

我将这套 Workflow 映射到 DataFlow 的算子化 Operator 和管线化 Pipeline 架构中。

注意，所有算子都要是命令行交互式的，如果当前要实现的算子的参考代码不是交互式的，那么要参考前面已经实现的算子的相关代码，进行设计。我的pipeline不是那种全自动的，是半自动的，人工的监控、管理和介入是必要的。

整体有一个edu_data_pipeline.py，里面是对各个operator的调用，通过命令行交互式，用户可以选择执行哪个算子，即执行Workflow的哪个步骤。

项目应使用本地的 DataFlow 包（包含 get_logger、OperatorABC、OPERATOR_REGISTRY 等）。相关代码应将本地 DataFlow 加入 sys.path。

涉及 LLM 交互的部分，可复用 `dataflow_edu.serving.llm_client`。该模块位于 `dataflow_edu/serving/` 目录下，作为通用 LLM 客户端，被需要它的算子共用。配置保存于项目根目录的 `.llm_config.json`。


### 阶段一：Taxonomy & OCR

这一阶段主要解决「考什么」和「从哪取数据」的问题。

- **1.1 Configuration Manager：** 类似llamafactory，支持可视化、灵活配置“考察知识方向（大类-小类双层架构）” + “考察能力层级（也是主层级-子层级双层架构）” + “考察形式（题型）”。同时支持配置Pipeline 和各 Operator 的参数。注意这部分是用户手动配置。
- **1.2 MinerU OCR Operator：** 批量输入高质量教材PDF图片（图片直接用wps的pdf转图片功能），调用 MinerU 引擎的批量处理 API，利用通用数据算子对每页提取文本、表格和复杂图文对，并清洗为标准化的 Markdown 格式。

### 阶段二：Generation & Balancing 

这一阶段负责将知识原料转化为题目，并保证题型分布的合理性。结果放在dataflow_edu\data\generation_and_balancing.

基于config Manager配置的“考察知识方向（大类-小类）” + “考察能力层级（建议双层架构）” + “考察形式（题型）” 的系统设计与评测维度 

- **2.1 Generation Operator：** 将解析后的文本按「每两页为一组」进行组合，作为 Context 输入给大模型，stage 1 判断该组合最适合的考察知识方向，stage 2 基于 configuration 进行批量化的习题与答案生成，并基于configuration中的能力层级和题型提供给大模型不同的Prompt，初步控制 “考察能力层级（建议也是双层架构）” + “考察形式（题型）”的分布（【2026-3-15更新】能力层级的分布控制，通过随机槽机制实现）
- **2.2 Balancing Operator：** 基于 configuration，用于实现考察能力层级、题型分布不均衡时的补题。（注意对于知识方向的均衡程度也要分析，但是需要给用户建议让其增加相关语料而不是强制生成某个知识方向的题目）（【2026-3-15更新】注意，这个算子已经基本不再具有使用价值，因为我们在2.1阶段已经基于随机槽机制实现了精准的能力层级分布控制，而且题型在生成时也是写死的，不依赖 LLM 返回。现在这个算子的意义是提示用户知识方向的分布是否均衡。）

### 阶段三：Cleaning & Refinement

生成的数据将流经一系列严格配置的「清洗算子」，最终提纯为高质量语料。

- **3.1 Ambiguity Cleaning Operator：** 检查二义性和剔除低质量样本。
- **3.2 Ambiguity Refinement Operator：** 对于中质量样本，优化二义性。
- **3.3 Domain Cleaning Operator：** 检查领域相关性和剔除低质量样本。
- **3.4 Domain Refinement Operator：** 对于中质量样本，优化领域相关性。
- **3.5 Deduplication Operator：** 利用N-Gram计算相似度，清洗掉高度重复的冗余题目。（似乎DataFlow中有？）
- **3.6 Synthesis Operator：** 为题目生成解析。（暂时跳过）
- **3.7 Translation Operator：** 执行多语言翻译，默认支持英法两种语言。支持检查残留源语言文本重新翻译。（暂时跳过）
- **3.8 MCQ Verify Operator：** 专为选择题设计的清洗算子，检查选择题是否包含 ABCD 四个选项，没有的补上。optimize_answers有validate_choice_questions（检查ABCD）、complete_choice_options（缺失时补全）。（暂时跳过）

> 建议注意，有能提升难度的地方可以自己改一下，比如生成一些东西的时候

### 阶段四：Execute & Judge

将生成的 Benchmark 真正运行起来，检验目标模型的能力。结果放在dataflow_edu\data\execute_and_judge.

- **4.1 Execute Operator：** 将待测的大模型接入系统进行作答，记录其答案。
- **4.2 Judge Operator：** 对应 DataFlow 中的「基于正确答案 Question Verify 算子」，调用大模型作为裁判。

### 其他工具

对于CNLawbench和ROBOTheory两个项目产出的json转excel、excel转jsonl这些工具脚本，整理放在utils文件夹下。

### WebUI

阶段一、二、三的执行过程中，基于utils_from_CNLaw-Bench\stage_viewer.html的样式（同时借鉴DataFlow项目的WebUI中的功能，有做得好的要加上），设计一个统一的面板，可以看到各个节点的情况。

Pipeline 看板（Vue 3 + Node.js）位于 `webui/`。启动方式：`cd webui && npm install && npm run dev`.


---

