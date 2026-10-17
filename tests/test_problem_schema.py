import pytest
from pydantic import ValidationError

from src.schemas.api import GenerateRequest, LoginRequest
from src.schemas.problem import Problem


def base_problem(**overrides):
    problem = {
        "id": "DERIV-001",
        "topic": "Derivatives",
        "problem_statement": "Differentiate the function $f(x)=x^2$.",
        "question_type": "calculation",
        "difficulty": 2,
        "solution": "$f'(x)=2x$.",
        "scaffolding": [{"step": 1, "hint": "Apply the power rule."}],
    }
    problem.update(overrides)
    return problem


def test_legacy_id_is_normalized_and_preserved():
    problem = Problem.model_validate(base_problem())
    assert problem.problem_id == "DERIV-001"
    assert problem.to_compatible_dict()["id"] == "DERIV-001"


def test_mcq_answer_must_reference_an_option():
    with pytest.raises(ValidationError):
        Problem.model_validate(
            base_problem(
                question_type="mcq",
                options={"A": "$1$", "B": "$2$"},
                answer="C",
            )
        )


def test_fill_in_requires_values_for_each_blank():
    with pytest.raises(ValidationError):
        Problem.model_validate(
            base_problem(
                question_type="fill_in",
                problem_statement="Complete [BLANK_1] and [BLANK_2].",
                correct_values=["1"],
            )
        )


def test_request_limits_and_safe_user_id():
    assert GenerateRequest(num=10, difficulty=5).num == 10
    with pytest.raises(ValidationError):
        GenerateRequest(num=11)
    with pytest.raises(ValidationError):
        LoginRequest(user_id="../unsafe")
