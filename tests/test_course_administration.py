import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import api_server
from src.auth import AuthIdentity
from src.auth_dependencies import current_identity
from src.config import Config
from src.rag import api as course_api
from src.rag.service import RetrievalService

client = TestClient(api_server.app)


def identity(role):
    return AuthIdentity("course_tester", role, "course_session", datetime.now(timezone.utc) + timedelta(hours=1))


def payload(**updates):
    return {"source_id": "test-course", "title": "Reviewed course notes", "version": "1",
            "topic": "Derivatives and Differentiation", "provenance": "Original test teaching notes",
            "license_name": "CC0-1.0", "filename": "notes.md", "content": "# Chain rule\nDifferentiate the outer function and multiply by the inner derivative.", **updates}


@pytest.fixture
def catalog(tmp_path, monkeypatch):
    directory = tmp_path / "knowledge"
    retriever = RetrievalService(knowledge_path=directory, use_dense=False)
    monkeypatch.setattr(Config, "KNOWLEDGE_PATH", directory)
    monkeypatch.setattr(course_api, "get_retriever", lambda: retriever)
    monkeypatch.setattr(api_server, "get_retriever", lambda: retriever)
    checks = []
    def validate(document):
        checks.append(document["source_id"])
        return {"tokenizer_checked": True, "max_tokens": 30}
    monkeypatch.setattr(retriever, "validate_document", validate)
    api_server.app.dependency_overrides[current_identity] = lambda: identity("admin")
    yield retriever, checks, directory
    api_server.app.dependency_overrides.clear()


def test_course_mutations_require_admin():
    assert client.get("/knowledge/manage/sources").status_code == 401
    api_server.app.dependency_overrides[current_identity] = lambda: identity("student")
    try:
        assert client.post("/knowledge/manage/preview", json=payload()).status_code == 403
        assert client.post("/knowledge/manage/save", json=payload()).status_code == 403
        assert client.get("/knowledge/manage/sources").status_code == 403
    finally:
        api_server.app.dependency_overrides.clear()


def test_preview_draft_publish_search_and_withdraw(catalog):
    retriever, checks, directory = catalog
    preview = client.post("/knowledge/manage/preview", json=payload())
    assert preview.status_code == 200
    assert preview.json()["document"]["status"] == "draft"
    assert not directory.exists(), "Preview must not write a course source."
    saved = client.post("/knowledge/manage/save", json=payload())
    assert saved.status_code == 200
    assert client.get("/knowledge/catalog").json()["chunks"] == []
    assert client.get("/knowledge/manage/sources/test-course").json()["document"]["chunks"]
    hashed = saved.json()["source_hash"]
    denied = client.post("/knowledge/manage/sources/test-course/status", json={"status": "published", "expected_hash": hashed})
    assert denied.status_code == 422
    published = client.post("/knowledge/manage/sources/test-course/status", json={
        "status": "published", "expected_hash": hashed, "review_confirmed": True})
    assert published.status_code == 200
    assert checks == ["test-course"]
    public = client.get("/knowledge/catalog").json()
    assert len(public["chunks"]) == 1
    search = client.get("/knowledge/search", params={"query": "chain rule"}).json()["data"]
    assert search["evidence"][0]["id"] == "test-course-1"
    old_evidence = search["evidence"][0]["text"]
    withdrawn = client.post("/knowledge/manage/sources/test-course/status", json={
        "status": "withdrawn", "expected_hash": published.json()["source_hash"]})
    assert withdrawn.status_code == 200
    assert not client.get("/knowledge/catalog").json()["chunks"]
    assert client.get("/knowledge/chunks/test-course-1").status_code == 404
    assert search["evidence"][0]["text"] == old_evidence
    assert list((directory / "archive").glob("*.json"))


def test_stale_admin_updates_are_rejected(catalog):
    saved = client.post("/knowledge/manage/save", json=payload())
    assert saved.status_code == 200
    assert client.post("/knowledge/manage/save", json=payload(version="2")).status_code == 409
    current = client.get("/knowledge/manage/sources/test-course").json()
    changed = payload(content="# Chain rule\nUpdated reviewed content.", expected_hash=current["source_hash"])
    assert client.post("/knowledge/manage/save", json=changed).status_code == 422
    changed["version"] = "2"
    assert client.post("/knowledge/manage/save", json=changed).status_code == 200
    stale = client.post("/knowledge/manage/sources/test-course/status", json={
        "status": "withdrawn", "expected_hash": current["source_hash"]})
    assert stale.status_code == 409


def test_publishing_requires_review_and_local_tokenizer(catalog, monkeypatch):
    retriever, _, _ = catalog
    assert client.post("/knowledge/manage/save", json=payload(publish=True)).status_code == 422
    def unavailable(_document):
        raise RuntimeError("Prepare the local embedding model before publishing course material.")
    monkeypatch.setattr(retriever, "validate_document", unavailable)
    response = client.post("/knowledge/manage/preview", json=payload(publish=True, review_confirmed=True))
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "LOCAL_MODEL_REQUIRED"


def test_structured_source_validation_and_duplicate_ids(catalog):
    malformed = payload(filename="course.json", content="[]")
    assert client.post("/knowledge/manage/preview", json=malformed).status_code == 422
    unit = {"id": "same-id", "title": "Rule", "topic": "Derivatives", "section": "1", "text": "Rule text."}
    assert client.post("/knowledge/manage/preview", json=payload(filename="course.json",
        content=json.dumps({"chunks": [unit, unit]}))).status_code == 422
    assert client.post("/knowledge/manage/preview", json=payload(source_id="../outside")).status_code == 422


def test_worked_examples_are_not_in_public_library(catalog):
    unit = {"id": "course-example", "title": "Example", "topic": "Derivatives", "section": "1",
            "text": "A complete solution.", "resource_type": "worked_example"}
    body = payload(filename="course.json", content=json.dumps({"chunks": [unit]}), publish=True, review_confirmed=True)
    assert client.post("/knowledge/manage/save", json=body).status_code == 200
    assert client.get("/knowledge/catalog").json()["chunks"] == []
    assert client.get("/knowledge/search", params={"query": "complete solution"}).json()["data"]["evidence"] == []
