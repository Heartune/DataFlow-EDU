Create a presentation slide image following these guidelines:

## Image Specifications
- **Type**: Presentation slide | **Aspect Ratio**: 16:9 | **Style**: Professional scientific academic

## Core Principles
- Clean scientific illustration; NO realistic/photographic elements; NO slide numbers/footers/logos
- Language: Chinese (except: DataFlow, OperatorABC, OPERATOR_REGISTRY, get_logger, llm_client, edu_data_pipeline.py, sys.path, .llm_config.json)

## STYLE_INSTRUCTIONS

Design Aesthetic: Academic scientific software architecture diagram. Venn-diagram integration style showing framework reuse, with clean code snippet panel.

Background: Light Blue-Gray (#F0F4F8). Typography: Bold serif headlines; monospace for code snippets; sans-serif labels.

Color Palette: Text #1E293B | Teal #0D9488 | Blue #3B82F6 | Purple #8B5CF6 | Amber #F59E0B | Green #22C55E | Gray #475569

Style Rules: Precise geometric circles for Venn; consistent label placement; monospace code block; no decorative art; no slide numbers.

---

## SLIDE CONTENT

**Slide 14 of 15 — Content**
**Filename**: 14-slide-dataflow-integration.png

**Narrative Goal**: 说明DataFlow-EDU与DataFlow框架的深度技术融合，体现工程规范性与可复现性。

**Key Content**:
- Headline: 深度融合 DataFlow 算子化哲学
- Sub-headline: 基于OperatorABC与OPERATOR_REGISTRY的标准化算子设计
- 复用DataFlow核心：get_logger · OperatorABC · OPERATOR_REGISTRY
- 通用LLM客户端：dataflow_edu.serving.llm_client 共用模块
- 配置驱动：.llm_config.json 统一管理API参数
- 命令行交互式Pipeline：edu_data_pipeline.py 调度所有算子

**Visual Description**:
Left two-thirds: Venn-diagram style integration illustration on light blue-gray (#F0F4F8).

LEFT CIRCLE (blue #3B82F6, semi-transparent fill): "DataFlow 框架"
  Inside (left exclusive area): Three labeled component boxes stacked:
    "OperatorABC" (blue chip)
    "OPERATOR_REGISTRY" (blue chip)
    "get_logger" (blue chip)

RIGHT CIRCLE (teal #0D9488, semi-transparent fill): "DataFlow-EDU 定制"
  Inside (right exclusive area): Three labeled component boxes:
    "GenerationOperator" (teal chip)
    "CleaningOperator" (teal chip)
    "JudgeOperator" (teal chip)

OVERLAPPING CENTER (purple #8B5CF6 fill): "复用接口层"
  Three items in overlap:
    "llm_client"
    ".llm_config.json"
    "edu_data_pipeline.py"

Right one-third: Clean code snippet box on white background with dark border:
  Title bar: "集成方式" in gray
  Monospace code block (dark background #1E293B, light text):
  ```python
  # 将本地DataFlow加入路径
  sys.path.insert(0, "DataFlow/")

  from dataflow.core.operator import (
      OperatorABC,
      OPERATOR_REGISTRY
  )
  from dataflow.logger import get_logger
  ```
  Caption below: "标准化集成，工程规范"

**Layout**: venn-diagram — Two overlapping circles on left, code panel on right.

Please use nano banana pro to generate the slide image based on the content provided above.
