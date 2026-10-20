import asyncio
import time

import httpx
from fastapi.testclient import TestClient

from api_server import app
from api_server import current_identity
from src.auth import AuthIdentity
from datetime import datetime, timedelta, timezone


client = TestClient(app)


def test_cors_allows_alternate_local_interview_frontend():
    response = client.options(
        "/auth/login",
        headers={
            "Origin": "http://127.0.0.1:3001",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:3001"


def test_health_contract_reports_dataset():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["total_problems"] == 252
    assert response.headers["X-Request-ID"].startswith("req_")


def test_capabilities_separate_vision_ocr_from_deepseek_grading():
    response = client.get("/capabilities")
    payload = response.json()

    assert response.status_code == 200
    assert payload["grading"]["provider"] == "simulation"
    assert payload["external_calls_enabled"] is False
    assert payload["grading"]["input"] == "text"
    assert isinstance(payload["vision_ocr"]["configured"], bool)
    assert "provider" in payload["vision_ocr"]
    assert "model" in payload["vision_ocr"]


def test_validation_errors_use_safe_standard_contract():
    response = client.post("/user/login", json={"user_id": "../unsafe"})
    payload = response.json()
    assert response.status_code == 422
    assert payload["success"] is False
    assert payload["error"]["code"] == "VALIDATION_ERROR"
    assert payload["error"]["request_id"].startswith("req_")
    assert "fields" in payload["error"]


def test_generate_rejects_out_of_range_count_before_llm_call():
    response = client.post(
        "/generate",
        json={
            "topics": ["Derivatives"],
            "num": 999,
            "mode": "drill",
            "difficulty": 3,
            "question_type": "calculation",
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_generation_does_not_block_lightweight_routes(monkeypatch):
    def slow_generation(**_kwargs):
        time.sleep(0.9)
        return []

    monkeypatch.setattr(
        "api_server.orchestrator.generator.generate_batch",
        slow_generation,
    )

    async def run_scenario():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as async_client:
            started_at = time.perf_counter()
            generation_task = asyncio.create_task(async_client.post(
                "/generate",
                json={
                    "topics": ["Applications of Derivatives"],
                    "num": 1,
                    "mode": "drill",
                    "difficulty": 3,
                    "question_type": "calculation",
                },
            ))
            await asyncio.sleep(0.05)
            topics_response = await async_client.get("/topics")
            topics_elapsed = time.perf_counter() - started_at
            generation_response = await generation_task
            return topics_response, topics_elapsed, generation_response

    topics_response, topics_elapsed, generation_response = asyncio.run(run_scenario())
    assert topics_response.status_code == 200
    assert topics_elapsed < 0.6
    assert generation_response.status_code == 500


def test_progress_requires_authentication():
    response = client.get("/user/progress/test_user")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"


def test_authenticated_user_cannot_read_another_profile():
    app.dependency_overrides[current_identity] = lambda: AuthIdentity(
        user_id="owner",
        role="student",
        session_id="session-test",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    try:
        response = client.get("/user/progress/another_user")
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "FORBIDDEN"
    finally:
        app.dependency_overrides.clear()
