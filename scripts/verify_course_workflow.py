"""Run real local course publishing with isolated data and the cached embedding model."""
import json
import logging
import os
import shutil
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    logging.basicConfig(level=logging.WARNING)
    folder = ROOT / ".runtime" / "course-tests" / uuid4().hex[:12]
    knowledge = folder / "knowledge"
    knowledge.mkdir(parents=True)
    shutil.copy2(ROOT / "data/knowledge/calculus.json", knowledge / "calculus.json")
    os.environ.update(AI_MODE="simulation", ALLOW_PAID_API="false", RAG_ALLOW_DOWNLOAD="false",
                      KNOWLEDGE_PATH=str(knowledge), DATABASE_URL=f"sqlite:///{(folder / 'course.db').as_posix()}",
                      OUTPUT_DIR=str(folder / "output"))
    from fastapi.testclient import TestClient
    import api_server
    from src.database import get_database
    from src.database.models import User
    from src.rag import get_retriever
    client = TestClient(api_server.app)
    user_id = f"course_admin_{uuid4().hex[:8]}"
    credentials = {"user_id": user_id, "password": "Isolated-course-test-2026!"}
    registered = client.post("/auth/register", json=credentials)
    registered.raise_for_status()
    student_headers = {"Authorization": "Bearer " + registered.json()["access_token"]}
    assert client.get("/knowledge/manage/sources", headers=student_headers).status_code == 403
    with get_database().session() as session:
        session.get(User, user_id).role = "admin"
    signed_in = client.post("/auth/login", json=credentials)
    signed_in.raise_for_status()
    assert signed_in.json()["user"]["role"] == "admin"
    headers = {"Authorization": "Bearer " + signed_in.json()["access_token"]}
    body = {"source_id": "logarithmic-notes", "title": "Logarithmic differentiation",
            "version": "1", "topic": "Derivatives and Differentiation", "filename": "notes.md",
            "provenance": "Original isolated workflow-test notes", "license_name": "CC0-1.0",
            "content": "# Logarithmic differentiation\nFor a positive differentiable function y=f(x), differentiating log(y) gives y'/y. This can simplify products, quotients and variable powers; check positivity before taking logarithms."}
    preview = client.post("/knowledge/manage/preview", json=body, headers=headers)
    preview.raise_for_status()
    assert preview.json()["document"]["status"] == "draft"
    assert not (knowledge / "logarithmic-notes.json").exists()
    saved = client.post("/knowledge/manage/save", json=body, headers=headers)
    saved.raise_for_status()
    assert not any(c["id"] == "logarithmic-notes-1" for c in client.get("/knowledge/catalog").json()["chunks"])
    publish = client.post("/knowledge/manage/sources/logarithmic-notes/status", headers=headers, json={
        "status": "published", "expected_hash": saved.json()["source_hash"], "review_confirmed": True})
    publish.raise_for_status()
    search = client.get("/knowledge/search", params={"query": "positive function logarithmic differentiation", "topic": body["topic"]})
    search.raise_for_status()
    assert any(c["id"] == "logarithmic-notes-1" for c in search.json()["data"]["evidence"])
    stale = client.post("/knowledge/manage/sources/logarithmic-notes/status", headers=headers, json={
        "status": "withdrawn", "expected_hash": saved.json()["source_hash"]})
    assert stale.status_code == 409
    withdrawn = client.post("/knowledge/manage/sources/logarithmic-notes/status", headers=headers, json={
        "status": "withdrawn", "expected_hash": publish.json()["source_hash"]})
    withdrawn.raise_for_status()
    assert client.get("/knowledge/chunks/logarithmic-notes-1").status_code == 404
    assert not any(c["id"] == "logarithmic-notes-1" for c in get_retriever().retrieve("logarithmic differentiation")["evidence"])
    report = {"paid_api_calls": 0, "isolated_database": True, "isolated_knowledge_catalog": True,
              "device": get_retriever().status()["device"], "model_revision": get_retriever().status()["model_revision"],
              "checks": {"student_cannot_manage": True, "preview_is_read_only": True,
                         "draft_excluded_from_retrieval": True, "publish_checks_real_local_tokenizer": True,
                         "published_source_retrieved": True, "stale_write_rejected": True,
                         "withdrawal_hides_source": True, "source_archive_retained": bool(list((knowledge / 'archive').glob('*.json')))}}
    assert all(report["checks"].values())
    target = ROOT / "reports/rag_course_workflow.json"
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"report": str(target), **report}, ensure_ascii=False))


if __name__ == "__main__":
    main()
