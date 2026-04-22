# -*- coding: utf-8 -*-
"""
联网核心素养建议子包：根据「学科 + 教材 + 教师个性化需求」检索权威课程标准，
返回结构化候选素养清单，给 WebUI Wizard「找不到匹配」按钮使用。
"""

from dataflow_edu.competency_suggest.core import (
    NEEDS_MAX_CHARS,
    SuggestError,
    suggest_competencies,
)

__all__ = [
    "NEEDS_MAX_CHARS",
    "SuggestError",
    "suggest_competencies",
]
