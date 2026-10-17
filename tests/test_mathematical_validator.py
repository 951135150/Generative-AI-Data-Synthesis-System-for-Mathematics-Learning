from src.validation import MathematicalValidator, ValidationStatus


def problem_with_claim(claim=None):
    return {
        "id": "DERIV-001",
        "topic": "Derivatives",
        "problem_statement": "Differentiate the function $f(x)=x^3+2x$.",
        "question_type": "calculation",
        "difficulty": 2,
        "solution": "$f'(x)=3x^2+2$.",
        "scaffolding": [{"step": 1, "hint": "Apply the power rule."}],
        "symbolic_validation": claim,
    }


def test_correct_derivative_passes_symbolically():
    report = MathematicalValidator().validate(
        problem_with_claim(
            {
                "operation": "differentiate",
                "source_expression": "x^3 + 2*x",
                "claimed_result": "3*x^2 + 2",
                "variable": "x",
            }
        )
    )
    assert report.status == ValidationStatus.PASSED
    assert report.checks["symbolic_claim"] is True


def test_incorrect_derivative_is_hard_failure():
    report = MathematicalValidator().validate(
        problem_with_claim(
            {
                "operation": "differentiate",
                "source_expression": "x^3 + 2*x",
                "claimed_result": "2*x^2 + 2",
                "variable": "x",
            }
        )
    )
    assert report.status == ValidationStatus.FAILED
    assert report.passed is False


def test_valid_problem_without_machine_claim_is_partial_not_failed():
    report = MathematicalValidator().validate(problem_with_claim())
    assert report.status == ValidationStatus.PARTIAL
    assert report.passed is True


def test_duplicate_mcq_options_are_rejected():
    problem = problem_with_claim()
    problem.update(
        {
            "question_type": "mcq",
            "options": {"A": "$2x$", "B": "$2x$"},
            "answer": "A",
        }
    )
    report = MathematicalValidator().validate(problem)
    assert report.status == ValidationStatus.FAILED
    assert report.checks["mcq_options_unique"] is False


def test_unsafe_symbolic_expression_is_rejected():
    report = MathematicalValidator().validate(
        problem_with_claim(
            {
                "operation": "differentiate",
                "source_expression": "__import__('os')",
                "claimed_result": "0",
                "variable": "x",
            }
        )
    )
    assert report.status == ValidationStatus.FAILED
