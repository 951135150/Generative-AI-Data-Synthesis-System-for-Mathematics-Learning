import json

import pytest

from src.multi_agent.coordinator import SynthesisConfig
from src.multi_agent.tools import _save_problem_to_disk


def valid_problem():
    return {
        "id": "INT-001",
        "topic": "Integrals",
        "problem_statement": "Find an antiderivative of the function $2x$.",
        "question_type": "calculation",
        "difficulty": 1,
        "solution": "$x^2+C$.",
        "scaffolding": [{"step": 1, "hint": "Reverse the power rule."}],
        "symbolic_validation": {
            "operation": "integrate",
            "source_expression": "2*x",
            "claimed_result": "x^2",
            "variable": "x",
        },
    }


def test_save_tool_refuses_invalid_problem(tmp_path):
    result = _save_problem_to_disk(
        {"id": "BAD", "topic": "Limits"},
        output_dir=str(tmp_path),
    )
    assert result["saved"] is False
    assert list(tmp_path.iterdir()) == []


def test_save_tool_writes_validated_canonical_problem(tmp_path):
    result = _save_problem_to_disk(valid_problem(), output_dir=str(tmp_path))
    assert result["saved"] is True
    saved = json.loads((tmp_path / "INT-001.json").read_text(encoding="utf-8"))
    assert saved["problem_id"] == "INT-001"
    assert saved["deterministic_validation"]["status"] == "passed"


def test_synthesis_config_rejects_invalid_bounds():
    with pytest.raises(ValueError):
        SynthesisConfig(topics=[], target_count=1)
    with pytest.raises(ValueError):
        SynthesisConfig(topics=["Limits"], target_count=21)
