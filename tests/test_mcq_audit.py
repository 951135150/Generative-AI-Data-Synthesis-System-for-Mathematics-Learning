import json

from fastapi.testclient import TestClient

import api_server
from src.evaluator import QualityEvaluator
from src.grading import MCQSelectionError, assess_mcq, extract_selected_option
from src.llm_client import LLMClient


client = TestClient(api_server.app)


def mcq_problem():
    return {
        "id": "MCQ-LOCAL-MAX",
        "problem_id": "MCQ-LOCAL-MAX",
        "topic": "Multivariable Calculus",
        "problem_statement": "Which point is a local maximum?",
        "question_type": "mcq",
        "difficulty": 3,
        "options": {
            "A": "(1, 2)",
            "B": "(-1, 2)",
            "C": "(1, -2)",
            "D": "(-1, -2)",
        },
        "answer": "D",
        "solution": "The Hessian is negative definite at (-1, -2).",
        "scaffolding": [{"step": 1, "hint": "Inspect the Hessian."}],
        "integration_analysis": "Not applicable in drill mode.",
        "mode": "drill",
    }


def configure_audit(monkeypatch, review_payload):
    captured = {}
    monkeypatch.setattr(
        api_server.problem_repository,
        "get",
        lambda _problem_id: mcq_problem(),
    )

    def fake_review(**kwargs):
        captured.update(kwargs)
        if isinstance(review_payload, Exception):
            raise review_payload
        return review_payload

    monkeypatch.setattr(api_server.orchestrator.llm_client, "mentor_review", fake_review)
    monkeypatch.setattr(
        api_server.submission_repository,
        "create",
        lambda **_kwargs: "sub_mcq",
    )
    return captured


def test_deterministic_mcq_assessment_maps_key_to_full_content():
    assessment = assess_mcq(mcq_problem(), "d")
    assert assessment.selected_key == "D"
    assert assessment.selected_content == "(-1, -2)"
    assert assessment.answer_content == "(-1, -2)"
    assert assessment.is_correct is True
    assert extract_selected_option(None, "The option I have chosen is: D") == "D"


def test_invalid_mcq_selection_is_rejected():
    try:
        assess_mcq(mcq_problem(), "Z")
    except MCQSelectionError as error:
        assert "A, B, C, D" in str(error)
    else:
        raise AssertionError("Unknown option keys must be rejected.")


def test_backend_verdict_overrides_incorrect_ai_verdict(monkeypatch):
    captured = configure_audit(
        monkeypatch,
        json.dumps({
            "is_correct": False,
            "logic_alignment_score": 5,
            "error_analysis": "AI incorrectly rejected the option.",
            "tutor_feedback": "AI feedback.",
            "next_hint": "AI hint.",
        }),
    )

    response = client.post("/audit", json={
        "problem_id": "MCQ-LOCAL-MAX",
        "selected_option": "D",
    })

    assert response.status_code == 200
    assert response.json()["is_correct"] is True
    assert response.json()["logic_alignment_score"] == 100
    assert "matches the verified reference option" in response.json()["tutor_feedback"]
    assert "incorrectly rejected" not in response.json()["error_analysis"]
    assert captured["student_text_answer"] == "Selected option D: (-1, -2)"
    assert captured["mcq_assessment"] == {
        "selected_key": "D",
        "selected_content": "(-1, -2)",
        "answer_key": "D",
        "answer_content": "(-1, -2)",
        "is_correct": True,
    }


def test_backend_verdict_overrides_false_positive_ai_verdict(monkeypatch):
    configure_audit(
        monkeypatch,
        json.dumps({
            "is_correct": True,
            "logic_alignment_score": 100,
            "error_analysis": "",
            "tutor_feedback": "AI incorrectly accepted the option.",
            "next_hint": "",
        }),
    )

    response = client.post("/audit", json={
        "problem_id": "MCQ-LOCAL-MAX",
        "selected_option": "A",
    })

    assert response.status_code == 200
    assert response.json()["is_correct"] is False
    assert response.json()["logic_alignment_score"] == 0
    assert "incorrectly accepted" not in response.json()["tutor_feedback"]


def test_mcq_grading_survives_ai_feedback_failure(monkeypatch):
    configure_audit(monkeypatch, RuntimeError("temporary provider failure"))

    response = client.post("/audit", json={
        "problem_id": "MCQ-LOCAL-MAX",
        "selected_option": "D",
    })

    payload = response.json()
    assert response.status_code == 200
    assert payload["is_correct"] is True
    assert payload["logic_alignment_score"] == 100
    assert "matches the verified reference option" in payload["tutor_feedback"]


def test_mentor_prompt_contains_full_mcq_reference_context():
    captured = {}
    llm_client = LLMClient.__new__(LLMClient)

    def fake_generate(**kwargs):
        captured.update(kwargs)
        return "{}"

    llm_client.generate = fake_generate
    assessment = assess_mcq(mcq_problem(), "D")
    llm_client.mentor_review(
        student_text_answer="Selected option D: (-1, -2)",
        problem_data=mcq_problem(),
        mcq_assessment=assessment.to_dict(),
    )

    prompt = captured["prompt"]
    assert '"A": "(1, 2)"' in prompt
    assert '"D": "(-1, -2)"' in prompt
    assert '"answer_key": "D"' in prompt
    assert '"answer_content": "(-1, -2)"' in prompt
    assert '"is_correct": true' in prompt


def test_generation_review_rejects_unconfirmed_mcq_answer_mapping():
    class FakeReviewer:
        def generate(self, *_args, **_kwargs):
            return json.dumps({
                "math_logic_score": 100,
                "pedagogical_score": 100,
                "integration_score": 0,
                "is_mathematically_correct": True,
                "mcq_answer_consistent": False,
                "logical_gap_detected": False,
                "critical_flaw": "The answer key points to the wrong option.",
                "improvement_suggestion": "Correct the answer mapping.",
            })

    result = QualityEvaluator(llm_client=FakeReviewer()).evaluate(
        mcq_problem(),
        ["Multivariable Calculus"],
    )

    assert result.passed is False
    assert result.dimensions["answer_consistency"] == 0
    assert any("MCQ ANSWER MISMATCH" in issue for issue in result.issues)
