# 🌟DataFlow-EDU: 端到端学科语料库&Benchmark生成

> From One to Infinity 🌈

> Github Repo: <link>https://github.com/Heartune/DataFlow-EDU</link>

## 核心定位说明

基于我在包含7.9万条语料的机器人理论语料库ROBOTheory-79k、规模1.6T网络安全专业语料库CyberSecCorpus、电子信息学科数据集EE-Bench、中国法律大模型评测基准CNLaw-Bench方面的丰富构建经验，我的核心目标是打造 **DataFlow-EDU**——一条高度自动化、算子化且具备通用性的「学科数据集与评测基准（Benchmark）」生产管线。该管线贯穿从「原始教材输入」到「高质量结构化题库输出」的全生命周期。它不仅包含基于 MinerU 的多模态文档解析、切片式题库生成与题型动态均衡模块，更深度融入了目标团队 DataFlow 的算子化清洗哲学。通过灵活串联条件过滤、领域对齐 与基于 Question Verify 的 LLM-as-a-Judge 多维能力审阅等定制化算子，最终实现自动化、批量化地生产低幻觉、高质量、均衡分布的学科评测集与训练语料，成为赋能各类学科大模型能力跃升的基础设施。这套系统支持包括教材在内的任意PDF教学资源输入，这里我将以一本高中生物必修一教材（PDF格式）作为资源，进行项目demo演示。

---

## 📖 Introducing DataFlow-EDU

![](slide-deck/dataflow-edu/01-slide-cover.png)

---

![](slide-deck/dataflow-edu/02-slide-motivation.png)

---

![](slide-deck/dataflow-edu/03-slide-project-scope.png)

---

![](slide-deck/dataflow-edu/04-slide-architecture.png)

---

![](slide-deck/dataflow-edu/05-slide-taxonomy-config.png)

---

![](slide-deck/dataflow-edu/06-slide-mineru-ocr.png)

---

![](slide-deck/dataflow-edu/07-slide-generation.png)

---

![](slide-deck/dataflow-edu/08-slide-balancing.png)

---

![](slide-deck/dataflow-edu/09-slide-cleaning-pipeline.png)

---

![](slide-deck/dataflow-edu/10-slide-llm-judge-cleaning.png)

---

![](slide-deck/dataflow-edu/11-slide-execute-judge.png)

---

![](slide-deck/dataflow-edu/12-slide-webui.png)

---

![](slide-deck/dataflow-edu/13-slide-prior-work.png)

---

![](slide-deck/dataflow-edu/14-slide-dataflow-integration.png)

---

![](slide-deck/dataflow-edu/15-slide-back-cover.png)

---

## Star History

<a href="https://www.star-history.com/?repos=Heartune%2FDataFlow-EDU&type=date&legend=top-left">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/image?repos=Heartune/DataFlow-EDU&type=date&theme=dark&legend=top-left" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/image?repos=Heartune/DataFlow-EDU&type=date&legend=top-left" />
   <img alt="Star History Chart" src="https://api.star-history.com/image?repos=Heartune/DataFlow-EDU&type=date&legend=top-left" />
 </picture>
</a>

---

## DataFlow-EDU 方案设计图景

我将这套 Workflow 映射到 DataFlow 的算子化 Operator 和管线化 Pipeline 架构中。

注意，所有算子都要是命令行交互式的，如果当前要实现的算子的参考代码不是交互式的，那么要参考前面已经实现的算子的相关代码，进行设计。我的pipeline不是那种全自动的，是半自动的，人工的监控、管理和介入是必要的。

整体有一个edu_data_pipeline.py，里面是对各个operator的调用，通过命令行交互式，用户可以选择执行哪个算子，即执行Workflow的哪个步骤。

项目应使用本地的 DataFlow 包（包含 get_logger、OperatorABC、OPERATOR_REGISTRY 等）。相关代码应将本地 DataFlow 加入 sys.path。

涉及 LLM 交互的部分，可复用 `dataflow_edu.serving.llm_client`。该模块位于 `dataflow_edu/serving/` 目录下，作为通用 LLM 客户端，被需要它的算子共用。配置保存于项目根目录的 `.llm_config.json`。


### 其他工具

对于CNLawbench和ROBOTheory两个项目产出的json转excel、excel转jsonl这些工具脚本，整理放在utils文件夹下。

### WebUI

Pipeline 看板（Vue 3 + Node.js）位于 `webui/`。启动方式：`cd webui && npm install && npm run dev`。

![](webui/img_intro/PixPin_2026-03-15_11-36-15.png)

---

![](webui/img_intro/PixPin_2026-03-15_11-36-34.png)

---

![](webui/img_intro/PixPin_2026-03-15_11-37-26.png)

---

![](webui/img_intro/PixPin_2026-03-15_11-41-24.png)

---

## 项目文件结构

```
DataFlow-EDU/
├── README.md
├── .llm_config.json          # LLM 配置（需自行创建）
├── dataflow_edu/             # 主管线与算子包
│   ├── edu_data_pipeline.py  # 命令行交互式入口
│   ├── config/               # 配置加载、校验、CLI 管理
│   │   ├── edu_config.yaml
│   │   ├── loader.py, schema.py, validator.py
│   │   ├── manager_cli.py
│   │   └── presets/
│   ├── operators/            # 各阶段算子
│   │   ├── mineru_ocr_operator.py
│   │   ├── generation_operator.py, balancing_operator.py
│   │   ├── ambiguity_cleaning_operator.py, ambiguity_refinement_operator.py
│   │   ├── domain_cleaning_operator.py, domain_refinement_operator.py
│   │   ├── deduplication_operator.py
│   │   ├── execute_operator.py, judge_operator.py
│   │   └── ...
│   ├── pipelines/            # 生成、MinerU 等管线
│   ├── serving/              # 通用 LLM 客户端
│   ├── judge/, execute/      # 评判与执行逻辑
│   ├── balancing/, generation/
│   ├── ambiguity_cleaning/, ambiguity_refinement/
│   ├── domain_cleaning/, domain_refinement/, deduplication/
│   └── data/                 # 管线产出数据
│       ├── generation_and_balancing/
│       ├── cleaning_and_refinement/
│       └── execute_and_judge/
├── webui/                    # Vue3 + Node 看板
│   ├── frontend/             # 前端 (Vite, Vue, Pinia)
│   │   └── src/
│   │       ├── views/, components/, stores/, api/, types/
│   │       └── App.vue
│   ├── server/               # 后端 API
│   │   └── src/
│   └── README.md
└── slide-deck/dataflow-edu/  # 演示文稿与配图
```

---

## Quick Start

1. **环境与依赖**
   - 确保项目根目录下的 `DataFlow` 目录存在（管线会通过 `sys.path` 使用本地 DataFlow 包）。
   - 在 `DataFlow`目录下运行 `pip install -e .`通过源码编译方式安装 DataFlow.

2. **配置**
   - 在项目根目录配置 LLM：创建 `.llm_config.json`，供生成、清洗、评测等算子调用大模型。
   - 建议优先通过 **WebUI 看板** 配置知识方向、能力层级、题型及各算子参数。启动 WebUI：在项目根目录执行 `cd webui && npm install && npm run dev`，浏览器访问 http://localhost:5173。也可在管线菜单中运行 **1.1 Configuration Manager**，或直接编辑 `dataflow_edu/config/edu_config.yaml`。

3. **运行管线**
   - 在项目根目录执行：
     ```bash
     python -m dataflow_edu.edu_data_pipeline
     ```
   - 根据提示选择步骤：1.1 配置 → 1.2 MinerU OCR → 2.1 生成 → 2.2 均衡（可选）→ 阶段三清洗 → 4.1 执行 → 4.2 评判。

4. **查看进度与结果**
   - 启动 WebUI 看板：` npm run dev`，浏览器访问前端（如 http://localhost:5173）查看各阶段节点状态。
   - 生成与均衡结果在 `dataflow_edu/data/generation_and_balancing/`，执行与评判结果在 `dataflow_edu/data/execute_and_judge/`。

---

## TODO
- [ ] 加入对课件的支持
- [ ] 有能提升难度的地方可以自己改一下，比如生成一些东西的时候
- [ ] 平民化webui设计，完善参数配置自由度，开发拖动控件和实时进度预览
- [ ] 优化终端与webui的联动，比如webui实时监控生成情况并同步，或终端每完成一个算子就给出对应阶段的webui url，方便用户快捷跳转
