from dataflow.utils.registry import OPERATOR_REGISTRY

from dataflow_ext_custom.operators.generate.my_generated_operator import MyGeneratedOperator

def test_operator_registered():
    assert "MyGeneratedOperator" in OPERATOR_REGISTRY
    assert OPERATOR_REGISTRY.get("MyGeneratedOperator") is MyGeneratedOperator
