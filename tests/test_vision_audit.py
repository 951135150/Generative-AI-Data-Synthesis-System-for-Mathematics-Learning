import base64
import json

from fastapi.testclient import TestClient

import api_server
from src.ocr import OCRConfigurationError, OCRTranscriptionError


client = TestClient(api_server.app)


def image_data_url(mime_type="image/png"):
    payload = base64.b64encode(b"synthetic-image").decode("ascii")
    return f"data:{mime_type};base64,{payload}"


def test_photo_audit_transcribes_before_deepseek_grading(monkeypatch):
    captured = {}
    transcript = r"$f(x)=x^2$, therefore $f'(x)=2x$."

    monkeypatch.setattr(
        api_server.ocr_client,
        "transcribe",
        lambda image_bytes, mime_type: transcript,
    )
    monkeypatch.setattr(
        api_server.problem_repository,
        "get",
        lambda _problem_id: {
            "id": "vision-problem",
            "topic": "Derivatives",
            "problem_statement": "Differentiate x squared.",
            "solution": "2x",
        },
    )

    def fake_review(**kwargs):
        captured.update(kwargs)
        return json.dumps({
            "is_correct": True,
            "logic_alignment_score": 92,
            "error_analysis": "",
            "tutor_feedback": "Correct differentiation.",
            "next_hint": "Try the chain rule next.",
        })

    monkeypatch.setattr(api_server.orchestrator.llm_client, "mentor_review", fake_review)
    monkeypatch.setattr(
        api_server.submission_repository,
        "create",
        lambda **_kwargs: "sub_vision",
    )

    response = client.post("/audit", json={
        "problem_id": "vision-problem",
        "student_work_image": image_data_url(),
        "is_exam_mode": False,
    })

    assert response.status_code == 200
    assert response.json()["ocr_text"] == transcript
    assert captured["student_work_image"] is None
    assert captured["student_text_answer"] == transcript


def test_photo_audit_reports_missing_vision_configuration(monkeypatch):
    def missing_provider(*_args, **_kwargs):
        raise OCRConfigurationError("Dedicated vision OCR is not configured.")

    monkeypatch.setattr(api_server.ocr_client, "transcribe", missing_provider)
    response = client.post("/audit", json={
        "problem_id": "any-problem",
        "student_work_image": image_data_url(),
    })

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "VISION_OCR_NOT_CONFIGURED"


def test_photo_audit_reports_provider_failure_without_deepseek_image_fallback(monkeypatch):
    def failed_provider(*_args, **_kwargs):
        raise OCRTranscriptionError("The vision provider could not read this image.")

    def unexpected_review(**_kwargs):
        raise AssertionError("DeepSeek grading must not receive a failed OCR image")

    monkeypatch.setattr(api_server.ocr_client, "transcribe", failed_provider)
    monkeypatch.setattr(api_server.orchestrator.llm_client, "mentor_review", unexpected_review)

    response = client.post("/audit", json={
        "problem_id": "any-problem",
        "student_work_image": image_data_url(),
    })

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "VISION_OCR_FAILED"
