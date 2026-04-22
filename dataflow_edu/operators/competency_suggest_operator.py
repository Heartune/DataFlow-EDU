# -*- coding: utf-8 -*-
"""
Competency Suggest Operator：联网检索权威课程标准，
给出与「学科 + 教材 + 教师个性化需求」匹配的核心素养建议。

注册到 ``OPERATOR_REGISTRY`` 后，可通过 ``OPERATOR_REGISTRY.get_obj("CompetencySuggestOperator")``
独立调用；同时 WebUI 通过 REST 接口 ``POST /api/competency/suggest`` spawn
``python -m dataflow_edu.competency_suggest`` 子进程使用。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from dataflow import get_logger
from dataflow.core import OperatorABC
from dataflow.utils.registry import OPERATOR_REGISTRY

from dataflow_edu.competency_suggest.core import (
    NEEDS_MAX_CHARS,
    SuggestError,
    suggest_competencies,
)
from dataflow_edu.config.schema import CompetencySuggestConfig, EduConfig


@OPERATOR_REGISTRY.register()
class CompetencySuggestOperator(OperatorABC):
    """联网素养建议算子（无 input_dir / output_dir，纯查询型）。"""

    def __init__(
        self,
        zgca_model: str = "Gemini-3.0-Flash",
        max_tokens: int = 2048,
        temperature: float = 0.3,
        needs_max_chars: int = NEEDS_MAX_CHARS,
    ):
        super().__init__()
        self.logger = get_logger()
        self.zgca_model = zgca_model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.needs_max_chars = needs_max_chars

    @staticmethod
    def get_desc(lang: str = "zh") -> str:
        if lang == "zh":
            return (
                "Competency Suggest Operator：基于 zgca 联网 LLM，"
                "根据学科 + 教材 + 教师个性化需求返回结构化核心素养候选清单（list[dict]）。"
                "无 input/output 目录，专供 WebUI Wizard「找不到匹配」按钮调用。"
            )
        return (
            "Competency Suggest Operator: query a search-enabled LLM via zgca to "
            "produce structured core-competency suggestions for a given subject + textbook + teacher needs."
        )

    def run(  # type: ignore[override]
        self,
        storage=None,
        subject: str = "",
        book: str = "",
        needs: str = "",
        config: Optional[EduConfig] = None,
        **_: Any,
    ) -> List[Dict[str, Any]]:
        """同步返回素养建议清单。失败时抛 ``SuggestError``，由调用方决定怎么处理。"""
        cs_cfg: Optional[CompetencySuggestConfig] = None
        if config is not None:
            raw = config.operators.get("competency_suggest")
            if isinstance(raw, CompetencySuggestConfig):
                cs_cfg = raw
            elif isinstance(raw, dict):
                cs_cfg = CompetencySuggestConfig(
                    zgca_model=str(raw.get("zgca_model", self.zgca_model)),
                    max_tokens=int(raw.get("max_tokens", self.max_tokens)),
                    temperature=float(raw.get("temperature", self.temperature)),
                    needs_max_chars=int(raw.get("needs_max_chars", self.needs_max_chars)),
                )

        model = cs_cfg.zgca_model if cs_cfg else self.zgca_model
        max_tokens = cs_cfg.max_tokens if cs_cfg else self.max_tokens
        temperature = cs_cfg.temperature if cs_cfg else self.temperature
        max_chars = cs_cfg.needs_max_chars if cs_cfg else self.needs_max_chars

        if needs and len(needs.strip()) > max_chars:
            raise SuggestError(
                "needs_too_long",
                f"个性化需求最长 {max_chars} 字，当前 {len(needs.strip())} 字",
            )

        try:
            return suggest_competencies(
                subject=subject,
                book=book,
                needs=needs,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        except SuggestError:
            raise
        except Exception as e:  # noqa: BLE001
            self.logger.warning(f"CompetencySuggestOperator 异常: {e}")
            raise SuggestError("internal_error", f"{type(e).__name__}: {e}") from e
