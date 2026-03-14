# -*- coding: utf-8 -*-
"""
LLM 评分 Prompt 构建模块。
参考 utils_from_CNLaw-Bench/gen_judgment.py，学科通用化（适配 K12 多学科）。
"""


def build_fill_in_blank_prompt(
    question: str, reference_answer: str, model_answer: str
) -> str:
    """填空题评分 Prompt（0 或 1 分）。要求 LLM 输出 {"score": 0或1}"""
    return f"""你是答案评判专家。请批改学生的填空题答案。

**严格评分要求：**
只有当学生答案满足以下**所有**条件时才给1分：
- 核心概念与标准答案完全一致（含同义表述）
- 专业术语必须准确无误
- 关键数值、单位、符号必须准确
- 不包含明显错误或编造的内容

如果不满足以上条件，则给0分。

题目：{question}
标准答案：{reference_answer}
学生回答：{model_answer}

请以 JSON 格式输出结果：
{{"score": <分数数字, 0或1>}}"""


def build_short_answer_prompt(
    question: str, reference_answer: str, model_answer: str
) -> str:
    """简答题评分 Prompt（1-10 分）。要求 LLM 输出 {"score": 1-10}"""
    return f"""你是答案评判专家。请批改学生的简答题答案。
评分的范围是1-10分，其中10分为最高分，1分为最低分。请**严格以标准答案为基准逐点对照**，综合考虑要点覆盖率、概念准确性和表述规范性。

你需要按照以下*严格标准*给出分数：

- **第一档：1-4分（明显错误或严重遗漏）**
  - 遗漏了标准答案中一半以上的关键要点，或核心要点完全错误
  - 概念理解有根本性偏差
  - 编造不存在的内容

- **第二档：5-6分（部分正确但有遗漏/瑕疵）**
  - 仅覆盖了标准答案中约一半的关键要点
  - 基本概念理解正确，但表述不够精准

- **第三档：7-8分（大体正确但不够完美）**
  - 覆盖了标准答案中的绝大多数关键要点
  - 仍有少部分次要要点遗漏或阐述不够充分

- **第四档：9-10分（完全覆盖且零错误）**
  - **必须毫无遗漏地覆盖标准答案中的每一个关键要点**
  - 概念准确，表述规范
  - （说明：只要遗漏了标准答案中的任何一个要点，最高只能给8分）

题目：{question}
标准答案：{reference_answer}
学生回答：{model_answer}

请以 JSON 格式输出结果：
{{"score": <分数数字, 范围1-10>}}"""


def build_calculation_prompt(
    question: str, reference_answer: str, model_answer: str
) -> str:
    """计算题评分 Prompt（1-10 分）。要求 LLM 输出 {"score": 1-10}"""
    return f"""你是答案评判专家。请严格批改学生的计算题答案。
此类题目涉及数值计算、公式运用等。
评分的范围是1-10分，其中10分为最高分，1分为最低分。请**严格对照标准答案中的计算步骤和最终结果**。

你需要按照以下*严格标准*给出分数：

- **第一档：1-4分（结果错误且依据错误）**
  - 最终计算结果错误
  - 计算依据或公式运用有误
  - 编造不存在的计算标准或数据

- **第二档：5-6分（结果错误但思路部分正确，或结果对但过程无依据）**
  - 最终结果错误，但部分中间步骤正确
  - 或最终数字蒙对，但未给出合理的计算步骤或依据

- **第三档：7-8分（结果正确但步骤/依据有轻微瑕疵）**
  - 最终计算结果与标准答案完全一致
  - 但缺少明确依据标注，或中间某一步骤论述不够严谨

- **第四档：9-10分（结果正确、步骤完整、依据精准）**
  - 最终计算结果与标准答案**完全一致**
  - 计算步骤严谨完整
  - 依据（公式、定理等）准确无误

题目：{question}
标准答案：{reference_answer}
学生回答：{model_answer}

请以 JSON 格式输出结果：
{{"score": <分数数字, 范围1-10>}}"""


def build_comprehensive_prompt(
    question: str, reference_answer: str, model_answer: str
) -> str:
    """综合题评分 Prompt（1-10 分）。要求 LLM 输出 {"score": 1-10}"""
    return f"""你是答案评判专家。请严格批改学生的综合题答案。
综合题要求学生进行系统、深入的分析和论证。
评分的范围是1-10分，其中10分为最高分，1分为最低分。请**严格以标准答案的论点为考核基准**。

你需要按照以下*严格标准*给出分数：

- **第一档：1-4分（偏题或存在根本性错误）**
  - 内容偏离核心主题
  - 对核心概念的理解存在根本性错误
  - 遗漏了标准答案中绝大多数核心论点
  - 编造内容

- **第二档：5-6分（观点单薄或论证缺乏深度）**
  - 覆盖了标准答案中的部分核心观点，但存在重大要点遗漏
  - 论证单薄，仅有结论而缺乏展开分析

- **第三档：7-8分（大体全面且无明显错误）**
  - 基本覆盖了标准答案中的绝大多数要点
  - 分析较为系统
  - 但论述深度可能未达极致，或个别次要论据未能点出

- **第四档：9-10分（要点全覆、逻辑严谨、极具深度）**
  - **必须包含标准答案中拆解出的所有论述维度，毫无遗漏**
  - 分析深入且令人信服
  - 表述专业规范
  - （只要漏掉标准答案中的某一个分析维度，最高只能给8分）

题目：{question}
标准答案：{reference_answer}
学生回答：{model_answer}

请以 JSON 格式输出结果：
{{"score": <分数数字, 范围1-10>}}"""


def build_scoring_prompt(
    question: str, reference_answer: str, model_answer: str, qtype: str
) -> str:
    """根据题型分发到对应的 Prompt 构造函数。"""
    dispatch = {
        "填空题": build_fill_in_blank_prompt,
        "简答题": build_short_answer_prompt,
        "计算题": build_calculation_prompt,
        "综合题": build_comprehensive_prompt,
    }
    builder = dispatch.get(qtype)
    if builder:
        return builder(question, reference_answer, model_answer)
    # 未知题型兜底：使用简答题 prompt
    return build_short_answer_prompt(question, reference_answer, model_answer)
