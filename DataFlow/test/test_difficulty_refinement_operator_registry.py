from dataflow.utils.registry import OPERATOR_REGISTRY

from custom_operators.operators.refine.difficulty_refinement_operator import DifficultyRefinementOperator

def test_operator_registered():
    assert "DifficultyRefinementOperator" in OPERATOR_REGISTRY
    resolved = OPERATOR_REGISTRY.get("DifficultyRefinementOperator")
    assert resolved is DifficultyRefinementOperator
    assert resolved.__name__ == "DifficultyRefinementOperator"
