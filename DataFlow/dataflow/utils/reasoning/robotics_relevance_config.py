from typing import Dict, Any


# 机器人学细分小类列表，来自你原先的相关性评估脚本
ROBOTICS_CATEGORIES_TEXT = """
·线性代数与矩阵运算 (Linear Algebra & Matrix Operations)
·微积分与微分方程 (Calculus & Differential Equations)
·空间几何与坐标变换 (Spatial Geometry & Coordinate Transformation)
·概率论与统计分析 (Probability & Statistical Analysis)
·数值计算方法 (Numerical Computing Methods)
·最优化理论基础 (Optimization Theory Basics)
·机构学与运动学 (Kinematics & Mechanisms)
·动力学建模 (Dynamics Modeling)
·结构力学与材料 (Structural Mechanics & Materials)
·执行器与电机 (Actuators & Motors)
·传动系统设计 (Transmission System Design)
·末端执行器 (End Effectors)
·传感器原理 (Sensor Principles)
·机器视觉 (Computer Vision)
·信号处理 (Signal Processing)
·控制理论 (Control Theories)
·轨迹规划 (Trajectory Planning)
·机器学习（Machine Learning）
·电路设计 (Circuit Design)
·微控制器应用 (Microcontroller Applications)
·机器人编程 (Robot Programming)
·通信协议 (Communication Protocols)
·嵌入式系统 (Embedded Systems)
·系统集成与调试 (System Integration & Debugging)
""".strip()


def get_default_robotics_relevance_config() -> Dict[str, Any]:
    """
    集中管理“机器人学相关性 + 小类划分”算子的默认配置。

    这些配置可以在 DataFlow 管线中通过传参覆盖，但这里提供一个统一入口，
    方便后续在一个地方调整默认行为。
    """
    return {
        "input_question_key": "question",
        "input_answer_key": "answer",
        "output_relevance_key": "robotics_relevance",
        "output_category_prefix": "robotics_category",
        # 未来如果需要引入不同领域，只需在此增加 domain 或 categories 配置即可
        "categories_text": ROBOTICS_CATEGORIES_TEXT,
    }


def build_robotics_relevance_prompt(question: str, answer: str, categories_text: str) -> str:
    """
    根据问答对构造用于 LLM 的提示词，要求输出一个 JSON。

    JSON 结构约定为：
    {
      "robotics_relevance": 0.87,
      "categories": [
        {"category_name": "...", "confidence": 0.5},
        {"category_name": "...", "confidence": 0.3},
        {"category_name": "...", "confidence": 0.2}
      ]
    }
    """
    prompt = f"""你是一名机器人学专家，需要分析下面的问题-答案对与机器人领域的相关性，并识别其所属的机器人学细分小类。

机器人学细分小类列表（中文 + 英文，仅从这些中选择）：
{categories_text}

待分析的问题-答案对如下：
问题：{question}
答案：{answer}

请完成以下任务：
1. 评估该问答对与“机器人领域”的相关性，给出 0 到 1 之间的小数，保留两位小数，记为 robotics_relevance。
2. 从上面给出的细分小类列表中，挑选最多 3 个最相关的小类，按相关度从高到低排序，并为每一个给出 0 到 1 之间的置信度（confidence）。
3. 3 个置信度之和应为 1（允许微小误差）。

请严格按照下面的 JSON 格式输出，不要添加任何额外说明、注释或 Markdown 代码块：
{{
  "robotics_relevance": 0.87,
  "categories": [
    {{"category_name": "细分小类名称1", "confidence": 0.5}},
    {{"category_name": "细分小类名称2", "confidence": 0.3}},
    {{"category_name": "细分小类名称3", "confidence": 0.2}}
  ]
}}"""
    return prompt

