from collections import Counter

from src.evaluation import StratifiedABEvaluator, build_stratified_manifest


def problem(identifier, integration=True):
    return {
        "id": identifier,
        "topic": "Derivatives",
        "problem_statement": "Differentiate the function x squared with respect to x.",
        "question_type": "calculation",
        "difficulty": 2,
        "solution": "The derivative is 2x.",
        "scaffolding": [{"step": 1, "hint": "Apply the power rule."}],
        "integration_analysis": "Connects to polynomial models." if integration else None,
        "quality_score": 90,
    }


def test_manifest_balances_every_factor_within_each_topic():
    manifest = build_stratified_manifest(
        ["Derivatives", "Integrals"], cases_per_topic=30, seed=9
    )
    assert manifest["case_count"] == 60
    assert manifest["generation_count"] == 120
    for topic in manifest["topics"]:
        tasks = [task for task in manifest["tasks"] if task["topic"] == topic]
        assert Counter(task["difficulty"] for task in tasks) == {
            1: 6, 2: 6, 3: 6, 4: 6, 5: 6
        }
        assert Counter(task["question_type"] for task in tasks) == {
            "calculation": 10, "mcq": 10, "fill_in": 10
        }
        assert Counter(task["mode"] for task in tasks) == {
            "drill": 15, "exam": 15
        }


def test_evaluator_uses_only_matched_pairs_for_confidence_intervals():
    records = []
    for case_id in ("case_1", "case_2"):
        records.extend(
            [
                {
                    "case_id": case_id,
                    "pipeline": "single_agent",
                    "topic": "Derivatives",
                    "success": False,
                    "problem": None,
                    "duration_ms": 100,
                },
                {
                    "case_id": case_id,
                    "pipeline": "multi_agent",
                    "topic": "Derivatives",
                    "success": True,
                    "problem": problem(f"M-{case_id}"),
                    "duration_ms": 200,
                },
            ]
        )
    report = StratifiedABEvaluator(seed=3, bootstrap_samples=100).evaluate(records)
    acceptance = report["paired_differences"]["accepted"]
    assert acceptance["matched_pairs"] == 2
    assert acceptance["delta_multi_minus_single"] == 1.0
    assert report["pipelines"]["single_agent"]["sample_size"] == 2
    assert report["by_topic"]["Derivatives"]["multi_agent"]["sample_size"] == 2
