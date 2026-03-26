from dataflow.utils.registry import OPERATOR_REGISTRY

from dataflow_edu_ops.operators.generate.edu_synthesis_operator import EduSynthesisOperator

def test_operator_registered():
    assert "EduSynthesisOperator" in OPERATOR_REGISTRY
    resolved = OPERATOR_REGISTRY.get("EduSynthesisOperator")
    assert resolved is EduSynthesisOperator
    assert resolved.__name__ == "EduSynthesisOperator"
