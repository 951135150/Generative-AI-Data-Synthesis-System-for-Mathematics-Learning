import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

import api_server
from src.config import Config
from src.database import UserRepository, get_database
from src.database.models import AttemptReceipt, EvidenceSnapshot, Submission
from src.learning.service import LearningService, recommend
from src.llm_client import LLMClient
from src.multi_agent.coordinator import Coordinator, SynthesisConfig
from src.rag.service import RetrievalService, digest, validate_citations
from src.simulation import SIMULATION_TOPICS, make_problem
from src.validation import MathematicalValidator

client = TestClient(api_server.app)
DERIVATIVES = "Derivatives and Differentiation"


def account():
    user_id = f"test_{uuid4().hex[:12]}"
    response = client.post("/auth/register", json={"user_id": user_id, "password": "LocalTest-only-2026!"})
    assert response.status_code == 201
    return user_id, {"Authorization": "Bearer " + response.json()["access_token"]}


def generate(topic=DERIVATIVES, question_type="mcq"):
    response = client.post("/generate", json={"topics": [topic], "num": 1, "question_type": question_type})
    assert response.status_code == 200, response.text
    return response.json()["data"][0]


def test_simulation_cannot_construct_paid_client(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("No paid SDK client may be created.")
    monkeypatch.setattr("src.llm_client.OpenAI", forbidden)
    llm = LLMClient()
    assert llm.model_name == "offline-fixtures-v1"
    monkeypatch.setattr(Config, "AI_MODE", "live")
    with pytest.raises(ValueError, match="disabled"):
        LLMClient()


def test_hybrid_baseline_filters_topics_and_preserves_math(tmp_path):
    retriever = RetrievalService(cache_dir=tmp_path, use_dense=False)
    result = retriever.retrieve("链式法则 inner function", topics=[DERIVATIVES])
    assert result["method"] == "keyword_only"
    assert result["evidence"][0]["id"] == "derivative-chain"
    assert "g'(x)" in result["evidence"][0]["text"]
    assert all(c["topic"] == DERIVATIVES for c in result["evidence"])
    assert retriever.retrieve("quantum chromodynamics") ["status"] == "insufficient"


def test_source_version_withdrawal_invalidates_new_queries(tmp_path):
    doc = json.loads((Config.KNOWLEDGE_PATH / "calculus.json").read_text(encoding="utf-8"))
    path = tmp_path / "course.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    retriever = RetrievalService(knowledge_path=tmp_path, use_dense=False)
    initial = retriever.retrieve("chain rule")
    old_version = initial["index_version"]
    old_chunk = initial["evidence"][0]
    doc["status"] = "withdrawn"
    path.write_text(json.dumps(doc), encoding="utf-8")
    updated = retriever.retrieve("chain rule")
    assert updated["evidence"] == []
    assert updated["index_version"] != old_version
    assert initial["evidence"][0] == old_chunk
    assert retriever.get_chunk(old_chunk["id"]) is None


def test_fabricated_citation_is_not_accepted():
    bundle = {"evidence": [{"citation_id": "C1", "id": "real"}]}
    result = validate_citations({"citation_ids": ["C1", "C999", "C1"]}, bundle)
    assert [c["id"] for c in result["citations"]] == ["real"]
    assert result["support_status"] == "not_independently_verified"


@pytest.mark.parametrize("topic", SIMULATION_TOPICS)
@pytest.mark.parametrize("question_type", ["mcq", "calculation", "fill_in"])
def test_all_pilot_fixtures_pass_symbolic_gate(topic, question_type):
    for variant in range(4):
        problem = make_problem(topic, question_type=question_type, variant=variant)
        report = MathematicalValidator().validate(problem)
        assert report.status.value == "passed", report.issues


def test_student_answer_updates_progress_once_and_citations_resolve():
    user_id, headers = account()
    problem = generate()
    assert not ({"answer", "solution", "expected_expression", "fixture_correct_option", "retrieval"} & problem.keys())
    canonical = api_server.problem_repository.get(problem["id"])
    request = {"problem_id": problem["id"], "selected_option": canonical["answer"],
               "user_id": user_id, "attempt_id": uuid4().hex}
    first = client.post("/audit", json=request, headers=headers)
    assert first.status_code == 200, first.text
    assert first.json()["logic_alignment_score"] == 100
    assert first.json()["progress_recorded"] is True
    assert client.post("/audit", json=request, headers=headers).json() == first.json()
    progress = client.get(f"/user/progress/{user_id}", headers=headers).json()
    assert progress["topics_status"][DERIVATIVES]["completed_count"] == 1
    assert progress["recommendation"]["reason"]
    citation = first.json()["citations"][0]
    source = client.get(f"/knowledge/chunks/{citation['id']}", params={"content_hash": citation["content_hash"]})
    assert source.status_code == 200
    assert source.json()["data"]["text"] == citation["text"]
    assert client.get(f"/knowledge/chunks/{citation['id']}", params={"source_version": "withdrawn-version"}).status_code == 404
    request["selected_option"] = next(key for key in canonical["options"] if key != canonical["answer"])
    assert client.post("/audit", json=request, headers=headers).status_code == 409
    assert client.post("/user/record", headers=headers, json={"user_id": user_id, "topic": DERIVATIVES,
                       "logic_alignment_score": 100, "is_correct": True}).status_code == 410


def test_typed_expression_checks_equivalence_not_string_equality():
    problem = generate(question_type="calculation")
    canonical = api_server.problem_repository.get(problem["id"])
    response = client.post("/audit", json={"problem_id": problem["id"],
        "text_answer": f"({canonical['expected_expression']})+0", "attempt_id": uuid4().hex})
    assert response.status_code == 200, response.text
    assert response.json()["is_correct"] is True


def test_retrieval_failure_cannot_change_mcq_grade(monkeypatch):
    problem = generate()
    canonical = api_server.problem_repository.get(problem["id"])
    monkeypatch.setattr(Config, "RAG_ENABLED", False)
    response = client.post("/audit", json={"problem_id": problem["id"], "selected_option": canonical["answer"]})
    assert response.status_code == 200, response.text
    assert response.json()["logic_alignment_score"] == 100
    assert response.json()["citations"] == []


def test_two_role_runs_do_not_share_directories_or_messages(tmp_path):
    async def run():
        left, right = [Coordinator(SynthesisConfig(topics=[DERIVATIVES], target_count=1,
                       question_type="mcq", output_dir=str(tmp_path / name))) for name in ("left", "right")]
        results = await asyncio.gather(left.synthesize(), right.synthesize())
        return left, right, results
    left, right, results = asyncio.run(run())
    assert all(result.success for result in results), [r.error for r in results]
    assert results[0].problems[0]["id"] != results[1].problems[0]["id"]
    assert results[0].total_llm_calls == results[1].total_llm_calls == 0
    for coordinator, result in zip((left, right), results):
        assert {m["sender"] for m in result.conversation_log} == {"curator", "synthesizer", "scaffolder", "reviewer"}
        assert all(m["content"]["run_id"] == coordinator.run_id for m in result.conversation_log)
        assert result.problems[0]["publishing_status"] == "simulation_checked"


def test_atomic_save_is_idempotent_under_concurrent_retries():
    user_id, _ = account()
    service = LearningService()
    problem = make_problem(DERIVATIVES)
    response = {"is_correct": True, "logic_alignment_score": 100, "tutor_feedback": "ok", "next_hint": "next"}
    key = uuid4().hex
    arguments = dict(user_id=user_id, request_key=key, request_hash=digest(key), problem=problem,
                     response=response, evidence={}, text_answer="A")
    with ThreadPoolExecutor(max_workers=3) as pool:
        outputs = list(pool.map(lambda _: service.save(**arguments), range(3)))
    assert len({out["submission_id"] for out in outputs}) == 1
    assert UserRepository().get_progress(user_id)["topics_status"][DERIVATIVES]["completed_count"] == 1


def test_public_agent_events_remove_answers():
    message = {"content": {"stage": "draft", "problem": {"answer": "A"}, "solution": "secret"}}
    assert api_server.public_agent_message(message)["content"] == {"stage": "draft"}


def test_actual_retrieval_preparation_error_does_not_break_mcq(monkeypatch):
    problem = generate()
    canonical = api_server.problem_repository.get(problem["id"])
    def failed_prepare():
        raise RuntimeError("test index failure")
    monkeypatch.setattr(api_server.get_retriever(), "prepare", failed_prepare)
    response = client.post("/audit", json={"problem_id": problem["id"], "selected_option": canonical["answer"]})
    assert response.status_code == 200
    assert response.json()["logic_alignment_score"] == 100
    assert response.json()["citations"] == []


def test_repeat_answers_do_not_inflate_concept_evidence():
    user_id, headers = account()
    problem = generate()
    canonical = api_server.problem_repository.get(problem["id"])
    wrong = next(k for k in canonical["options"] if k != canonical["answer"])
    for choice in (wrong, canonical["answer"]):
        response = client.post("/audit", headers=headers, json={"problem_id": problem["id"],
            "selected_option": choice, "user_id": user_id, "attempt_id": uuid4().hex})
        assert response.status_code == 200
    progress = client.get(f"/user/progress/{user_id}", headers=headers).json()
    assert progress["topics_status"][DERIVATIVES]["completed_count"] == 1
    concept = progress["concept_evidence"][0]
    assert concept["attempts"] == 1 and concept["correct"] == 0
    assert concept["evidence_status"] == "limited"


def test_initial_value_answers_cannot_add_an_arbitrary_constant():
    problem = generate(topic="Differential Equations", question_type="calculation")
    canonical = api_server.problem_repository.get(problem["id"])
    response = client.post("/audit", json={"problem_id": problem["id"],
        "text_answer": f"({canonical['expected_expression']})+5"})
    assert response.status_code == 200
    assert response.json()["is_correct"] is False


def test_exam_restrictions_follow_stored_problem_not_client_flag():
    response = client.post("/generate", json={"topics": [DERIVATIVES], "question_type": "mcq", "mode": "exam"})
    assert response.status_code == 200
    question = response.json()["data"][0]
    assert question["mode"] == "exam" and question["scaffolding"] == []
    assert "simulation_note" in question


def test_gpu_encoding_retries_small_batch_then_falls_back_to_cpu(tmp_path):
    import numpy as np
    retriever = RetrievalService(cache_dir=tmp_path, use_dense=False)
    class FakeModel:
        calls = 0
        target = "cuda"
        def encode(self, texts, **kwargs):
            self.calls += 1
            if self.calls < 3:
                raise RuntimeError("CUDA out of memory")
            return np.ones((len(texts), 2))
        def to(self, device):
            self.target = device
    retriever._model = FakeModel()
    retriever.device = "cuda"
    assert retriever._encode(["query: derivative"]).shape == (1, 2)
    assert retriever.device == "cpu"
    assert retriever._model.target == "cpu"
