from dataflow.utils.registry import OPERATOR_REGISTRY

from dataflow_edu_ops.operators.generate.edu_socratic_hint_generator import EduSocraticHintGenerator

def test_operator_registered():
    assert "EduSocraticHintGenerator" in OPERATOR_REGISTRY
    assert OPERATOR_REGISTRY.get("EduSocraticHintGenerator") is EduSocraticHintGenerator
