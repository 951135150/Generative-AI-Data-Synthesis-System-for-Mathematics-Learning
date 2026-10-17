from src.evaluation import DatasetBenchmark, build_task_suite


def valid_problem(identifier="P-1", statement=None):
    return {
        "id": identifier,
        "topic": "Derivatives",
        "problem_statement": statement or "Differentiate x squared with respect to x.",
        "question_type": "calculation",
        "difficulty": 1,
        "solution": "The derivative is 2x.",
        "scaffolding": [{"step": 1, "hint": "Apply the power rule."}],
        "integration_analysis": "Connects powers to polynomial differentiation.",
        "quality_score": 90,
        "symbolic_validation": {
            "operation": "differentiate",
            "source_expression": "x^2",
            "claimed_result": "2*x",
            "variable": "x",
        },
    }


def test_benchmark_reports_quality_and_duplicates():
    problems = [
        valid_problem(),
        valid_problem("P-2"),
        {"id": "BAD", "topic": "Limits"},
    ]
    metrics = DatasetBenchmark().evaluate(problems)
    assert metrics.total == 3
    assert metrics.schema_valid_rate == 0.6667
    assert metrics.symbolic_coverage_rate == 0.6667
    assert metrics.symbolic_pass_rate == 1.0
    assert metrics.duplicate_rate == 0.3333
    assert metrics.average_quality_score == 90


def test_task_suite_is_reproducible():
    first = build_task_suite(["Limits", "Derivatives"], size=12, seed=7)
    second = build_task_suite(["Limits", "Derivatives"], size=12, seed=7)
    assert first == second
    assert len(first) == 12
    assert {case["difficulty"] for case in first} == {1, 2, 3, 4, 5}
