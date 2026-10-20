"""Exercise real local APIs against a separate database. No paid model access."""
import argparse
import json
import os
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PROFILES = ("foundation", "differential_strength", "balanced", "advanced")
QUESTION_TYPES = ("mcq", "calculation", "fill_in")
DIFFERENTIAL_TOPICS = {
    "Derivatives and Differentiation", "Applications of Derivatives",
    "Multivariable Calculus", "Parametric and Polar Curves",
}


def planned_outcome(profile, topic, round_index):
    """Scripted behavior, not inferred student ability or measured learning."""
    if profile == "foundation":
        return (False, False, True)[round_index]
    if profile == "differential_strength":
        return topic in DIFFERENTIAL_TOPICS or (True, False, False)[round_index]
    if profile == "balanced":
        return (True, False, True)[round_index]
    if profile == "advanced":
        return (False, True, True)[round_index] if topic == "Vector Calculus" else True
    raise ValueError(f"Unknown synthetic profile: {profile}")


def run_profile(client, repository, profile):
    from src.simulation import SIMULATION_TOPICS
    from src.learning.service import review_schedule
    from src.database import UserRepository

    topics = list(SIMULATION_TOPICS)
    user_id = f"sim_{uuid4().hex[:8]}_{profile}"
    registration = client.post("/auth/register", json={"user_id": user_id, "password": "Simulation-only-2026!"})
    registration.raise_for_status()
    headers = {"Authorization": "Bearer " + registration.json()["access_token"]}
    attempts, rounds = [], []
    expected = {topic: {"mastery_score": 0.0, "completed_count": 0, "current_level": 1} for topic in topics}

    def progress():
        response = client.get(f"/user/progress/{user_id}", headers=headers)
        response.raise_for_status()
        result = response.json()
        persisted = UserRepository().get_progress(user_id)
        assert persisted["topics_status"] == result["topics_status"]
        # History is intentionally not exposed by the dashboard DTO. Check the
        # persisted events via its read-only repository rather than changing API.
        return {**result, "learning_history": persisted["learning_history"]}

    def audit(question, question_type, correct):
        canonical = repository.get(question["id"])
        payload = {"problem_id": question["id"], "user_id": user_id, "attempt_id": uuid4().hex}
        if question_type == "mcq":
            payload["selected_option"] = canonical["answer"] if correct else next(
                k for k in canonical["options"] if k != canonical["answer"])
        else:
            # A constant offset would be a VALID antiderivative; zero is wrong for
            # every nonzero fixture here, including indefinite-integral questions.
            payload["text_answer"] = canonical["expected_expression"] if correct else "0"
        response = client.post("/audit", json=payload, headers=headers)
        response.raise_for_status()
        verdict = response.json()
        assert verdict["is_correct"] is correct, (profile, question["topic"], question_type, verdict)
        assert verdict["logic_alignment_score"] == (100 if correct else 0)
        assert verdict["progress_recorded"] is True
        assert verdict["learning_credit"] == "first_attempt"
        retry = client.post("/audit", json=payload, headers=headers)
        retry.raise_for_status()
        assert retry.json() == verdict
        assert verdict["citations"], (profile, question["topic"], "Missing course evidence")
        for citation in verdict["citations"]:
            source = client.get(f"/knowledge/chunks/{citation['id']}", params={
                "content_hash": citation["content_hash"], "source_version": citation["source_version"]})
            source.raise_for_status()
            assert source.json()["data"]["text"] == citation["text"]
        return payload, verdict

    for round_index, question_type in enumerate(QUESTION_TYPES):
        for topic in topics:
            correct = planned_outcome(profile, topic, round_index)
            generated = client.post("/generate", headers=headers, json={
                "topics": [topic], "question_type": question_type, "difficulty": 2, "user_id": user_id})
            generated.raise_for_status()
            question = generated.json()["data"][0]
            assert question["topic"] == topic and question["question_type"] == question_type
            assert question["difficulty"] == 2 and question["mode"] == "drill"
            assert not {"answer", "solution", "expected_expression", "fixture_correct_option", "retrieval"} & question.keys()
            payload, verdict = audit(question, question_type, correct)
            state = expected[topic]
            state["mastery_score"] = round(.4 * state["mastery_score"] + .6 * int(correct), 2)
            state["completed_count"] += 1
            if state["completed_count"] >= 3 and correct and state["mastery_score"] >= .8:
                state["current_level"] = min(3, state["current_level"] + 1)
            # A fresh request ID on the same question must not award another credit.
            if round_index == 2:
                repeated = client.post("/audit", headers=headers, json={**payload, "attempt_id": uuid4().hex})
                repeated.raise_for_status()
                assert repeated.json()["learning_credit"] == "retry_no_extra_credit"
                assert repeated.json()["progress_recorded"] is False
            attempts.append({"topic": topic, "round": round_index + 1, "question_type": question_type,
                             "is_correct": correct, "citations": len(verdict["citations"]),
                             "retrieval_method": verdict["retrieval_method"], "retry_idempotent": True,
                             "learning_credit": verdict["learning_credit"]})
        snapshot = progress()
        assert len(snapshot["learning_history"]) == len(attempts)
        assert sum(s["completed_count"] for s in snapshot["topics_status"].values()) == len(attempts)
        for topic, state in expected.items():
            assert all(snapshot["topics_status"][topic][key] == value for key, value in state.items()), (profile, topic, snapshot)
        rounds.append({"round": round_index + 1, "question_type": question_type,
                       "independent_attempts": len(attempts), "all_topic_states_verified": True})

    recommendation = snapshot["recommendation"]
    assert recommendation["topic"] in topics and recommendation["reason"]
    if profile == "differential_strength":
        assert recommendation["topic"] not in DIFFERENTIAL_TOPICS
        assert min(expected[t]["mastery_score"] for t in DIFFERENTIAL_TOPICS) > max(
            expected[t]["mastery_score"] for t in topics if t not in DIFFERENTIAL_TOPICS)
    assert snapshot["concept_evidence"] and all(c["attempts"] >= 3 for c in snapshot["concept_evidence"])
    assert snapshot["review_queue"] == []  # Nothing is due immediately after practice.
    future = datetime.now(timezone.utc) + timedelta(days=8)
    projected = review_schedule(snapshot, now=future)
    eligible = {t for t in topics if planned_outcome(profile, t, 2)}
    assert {row["topic"] for row in projected} == eligible

    adaptive = client.post("/generate", headers=headers, json={"user_id": user_id, "topics": [], "question_type": "mcq"})
    adaptive.raise_for_status()
    question = adaptive.json()["data"][0]
    assert all(question[key] == recommendation[key] for key in ("topic", "difficulty", "mode"))
    audit(question, "mcq", True)
    final = progress()
    assert len(final["learning_history"]) == len(attempts) + 1
    assert sum(s["completed_count"] for s in final["topics_status"].values()) == len(attempts) + 1
    assert final["topics_status"][question["topic"]]["completed_count"] == 4
    final_expected = {t: dict(state) for t, state in expected.items()}
    followup_state = final_expected[question["topic"]]
    followup_state["mastery_score"] = round(.4 * followup_state["mastery_score"] + .6, 2)
    followup_state["completed_count"] += 1
    if followup_state["mastery_score"] >= .8:
        followup_state["current_level"] = min(3, followup_state["current_level"] + 1)
    for topic, state in final_expected.items():
        assert all(final["topics_status"][topic][key] == value for key, value in state.items())
    return {"profile": profile, "topics_covered": len(topics), "attempts": attempts,
            "rounds": rounds, "topic_summary": expected, "recommendation": recommendation,
            "concept_evidence": snapshot["concept_evidence"], "fresh_request_retries_without_credit": len(topics),
            "review_check": {"immediate_due_count": 0, "projected_after_days": 8,
                             "projected_due_topics": [r["topic"] for r in projected],
                             "note": "Clock projection over actual API history; database timestamps were not changed."},
            "adaptive_generation_succeeded": True,
            "adaptive_followup": {"topic": question["topic"], "graded": True, "progress_recorded": True,
                                  "verified_topic_state": followup_state},
            "final_independent_attempts": len(attempts) + 1}


def run(report_path=None):
    logging.basicConfig(level=logging.WARNING)
    folder = ROOT / ".runtime" / "student-tests" / uuid4().hex[:12]
    folder.mkdir(parents=True)
    os.environ["AI_MODE"] = "simulation"
    os.environ["ALLOW_PAID_API"] = "false"
    os.environ["RAG_ALLOW_DOWNLOAD"] = "false"
    os.environ["DATABASE_URL"] = f"sqlite:///{(folder / 'students.db').as_posix()}"
    os.environ["OUTPUT_DIR"] = str(folder / "output")
    from fastapi.testclient import TestClient
    import api_server
    from src.rag import get_retriever
    from src.simulation import SIMULATION_TOPICS

    client = TestClient(api_server.app)
    retrieval_status = get_retriever().prepare()
    results = [run_profile(client, api_server.problem_repository, profile) for profile in PROFILES]
    synthesis = client.post("/synthesize", json={"topics": ["Derivatives and Differentiation"], "count": 2, "question_type": "mcq"})
    synthesis.raise_for_status()
    assert synthesis.json()["success"]
    assert synthesis.json()["total_llm_calls"] == 0
    coverage = []
    for topic in SIMULATION_TOPICS:
        for question_type in ("mcq", "calculation", "fill_in"):
            generated = client.post("/generate", json={"topics": [topic], "question_type": question_type})
            generated.raise_for_status()
            visible = generated.json()["data"][0]
            canonical = api_server.problem_repository.get(visible["id"])
            assert not {"answer", "solution", "expected_expression"} & visible.keys()
            payload = {"problem_id": visible["id"], "attempt_id": uuid4().hex}
            if question_type == "mcq":
                payload["selected_option"] = canonical["answer"]
            else:
                payload["text_answer"] = canonical["expected_expression"]
            audit = client.post("/audit", json=payload)
            audit.raise_for_status()
            assert audit.json()["is_correct"]
            coverage.append({"topic": topic, "question_type": question_type, "passed": True})
    report = {"created_at": datetime.now(timezone.utc).isoformat(), "ai_mode": "simulation",
              "paid_api_calls": 0, "database_isolated": True, "retrieval": retrieval_status,
              "learning_coverage": {"topics": list(SIMULATION_TOPICS), "profiles": len(results),
                  "rounds_per_topic": len(QUESTION_TYPES), "question_types": list(QUESTION_TYPES),
                  "graded_curriculum_attempts": sum(len(r["attempts"]) for r in results),
                  "graded_adaptive_followups": len(results),
                  "same_id_replays": sum(len(r["attempts"]) + 1 for r in results),
                  "fresh_id_retries_without_credit": sum(r["fresh_request_retries_without_credit"] for r in results)},
              "profiles": results, "role_simulation": {"count": synthesis.json()["total_problems"],
              "total_llm_calls": 0, "note": "Scripted role replies; autonomous AI quality was not measured."},
              "fixture_coverage": coverage,
              "limitations": ["Synthetic behavior does not establish real learning gains.",
                              "No DeepSeek quality, latency or cost measurements.",
                              "All thirteen topics have small parameterized fixtures; these do not cover the complete syllabus or validate difficulty."]}
    target = Path(report_path) if report_path else ROOT / "reports" / "rag_student_simulation.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"report": str(target), "profiles": len(results),
                      "attempts": sum(len(r["attempts"]) for r in results),
                      "paid_api_calls": 0, "device": retrieval_status["device"]}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--report")
    run(parser.parse_args().report)
