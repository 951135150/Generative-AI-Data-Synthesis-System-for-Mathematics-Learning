"""Manual assistant review packets, not a model endpoint or a DeepSeek benchmark.

Prepare real prompts and local evidence, read them, author responses separately,
then apply only those responses through the ordinary audit and persistence path.
"""
import argparse
import json
import logging
import os
import sys
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
KINDS = ("correct", "wrong", "equivalent", "process")


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def verify_reference(row, problem):
    """Compare independently written formulas, including legitimate constants."""
    import sympy as sp
    x = sp.Symbol("x", real=True)
    def parse(value):
        return sp.sympify(value, locals={"x": x}, rational=True)
    reference = parse(row["reference"])
    constant_allowed = problem.get("allow_additive_constant") is True
    def equivalent(value):
        delta = sp.simplify(parse(value) - reference)
        return delta == 0 or (constant_allowed and not delta.has(x))
    assert equivalent(problem["expected_expression"]), row["topic"]
    assert equivalent(row["equivalent"]), row["topic"]
    assert not equivalent(row["wrong"]), row["topic"]
    checks = {"independent_formula_agrees": True, "equivalent_answer_checked": True,
              "wrong_answer_distinct": True}
    if row.get("reviewed_options"):
        from src.grading import assess_mcq
        valid = []
        integrand = parse(problem["symbolic_validation"]["source_expression"])
        for key, expression in row["reviewed_options"].items():
            candidate = parse(expression)
            from src.validation import MathematicalValidator
            displayed = MathematicalValidator()._parse_expression(expression, x, evaluate=False)
            assert problem["options"][key] == f"$ {sp.latex(displayed)} $", "Reviewed transcription no longer matches the actual option."
            if sp.simplify(sp.diff(candidate, x) - integrand) == 0:
                valid.append(key)
        checks["mcq_valid_option_keys"] = valid
        checks["mcq_single_answer_valid"] = len(valid) == 1
        checks["stored_key_verdict_on_valid_options"] = {key: assess_mcq(problem, key).is_correct for key in valid}
    return checks


def packet_cases(rows, retriever):
    from src.simulation import make_problem
    from src.grading import assess_mcq
    from src.llm_client import LLMClient
    from src.validation import MathematicalValidator
    cases = []
    for index, row in enumerate(rows, start=1):
        base = make_problem(row["topic"], difficulty=3, variant=1)
        checks = verify_reference(row, base)
        validator_status = MathematicalValidator().validate(base).status.value
        assert validator_status == "passed"
        checks["existing_validator_status"] = validator_status
        for kind in KINDS:
            problem = dict(base)
            problem["id"] = problem["problem_id"] = f"manual_mentor_{index:02d}_{kind}"
            if kind != "correct":
                problem["question_type"] = "calculation"
                for key in ("options", "answer", "fixture_correct_option"):
                    problem.pop(key, None)
            assessment = assess_mcq(problem, base["answer"]).to_dict() if kind == "correct" else None
            text = (f"Selected option {assessment['selected_key']}: {assessment['selected_content']}"
                    if assessment else row[{"wrong": "wrong", "equivalent": "equivalent", "process": "process"}[kind]])
            bundle = retriever.retrieve(" ".join([row["topic"], " ".join(problem["concept_ids"]), problem["problem_statement"]]),
                                         topics=[row["topic"]], purpose="tutor", required_concepts=problem["concept_ids"])
            assert any(c["id"] == row["source"] for c in bundle["evidence"]), row["topic"]
            captured = {}
            llm = LLMClient.__new__(LLMClient)
            llm.generate = lambda **kwargs: captured.update(kwargs) or "{}"
            llm.mentor_review(problem_data=problem, student_text_answer=text,
                              mcq_assessment=assessment, evidence_bundle=bundle)
            cases.append({"case_id": f"{index:02d}-{kind}", "topic": row["topic"], "kind": kind,
                "problem": problem, "student_text": text, "assessment": assessment, "evidence": bundle,
                "actual_mentor_prompt": captured["prompt"], "source_unit": row["source"],
                "reference_checks": checks,
                "expected": {"is_correct": kind in {"correct", "equivalent"},
                             "score_range": [100, 100] if kind in {"correct", "equivalent"} else [0, 0] if kind == "wrong" else [40, 70]},
                "rubric_note": "Process cases include an explicit invalid step despite a correct final expression; partial credit is an authored rubric, not calibrated pedagogy."})
    return cases


def apply_cases(cases, authored, client, api):
    from src.simulation import SimulationInputError
    from src.database import UserRepository
    assert len(authored) == len(cases)
    assert {r["case_id"] for r in authored} == {c["case_id"] for c in cases}
    reviews = {r["case_id"]: r for r in authored}
    learner = f"manual_review_{uuid4().hex[:12]}"
    registered = client.post("/auth/register", json={"user_id": learner, "password": "ManualReview-only-2026!"})
    registered.raise_for_status()
    headers = {"Authorization": "Bearer " + registered.json()["access_token"]}
    results = []
    for case in cases:
        authored_review = reviews[case["case_id"]]
        source = (next(c for c in case["evidence"]["evidence"] if c["id"] == authored_review["source_unit"])
                  if authored_review["source_unit"] else None)
        reply = {k: authored_review[k] for k in ("is_correct", "logic_alignment_score", "error_analysis", "tutor_feedback", "next_hint")}
        reply["tutor_feedback"] = reply["tutor_feedback"].replace("[SOURCE]", f"[{source['citation_id']}]" if source else "")
        reply["citation_ids"] = [source["citation_id"]] if source else []
        assert reply["is_correct"] is case["expected"]["is_correct"]
        lo, hi = case["expected"]["score_range"]
        assert lo <= reply["logic_alignment_score"] <= hi
        # Run the existing simulator as a clearly labeled baseline, not as the
        # author of the evaluated feedback. Free-form process text is unsupported.
        try:
            baseline = json.loads(api.orchestrator.llm_client.mentor_review(
                problem_data=case["problem"], student_text_answer=case["student_text"],
                mcq_assessment=case["assessment"], evidence_bundle=case["evidence"]))
            baseline_result = {"status": "supported", "is_correct": baseline["is_correct"],
                "agrees_with_authored_rubric": baseline["is_correct"] is case["expected"]["is_correct"]}
        except SimulationInputError:
            baseline_result = {"status": "unsupported_freeform", "agrees_with_authored_rubric": None}
        api.problem_repository.upsert(case["problem"], source="manual_evaluation")
        payload = {"problem_id": case["problem"]["id"], "user_id": learner, "attempt_id": uuid4().hex}
        if case["assessment"]:
            payload["selected_option"] = case["assessment"]["selected_key"]
        else:
            payload["text_answer"] = case["student_text"]
        def authored_reply(**kwargs):
            assert kwargs["student_text_answer"] == case["student_text"]
            assert kwargs["problem_data"]["problem_statement"] == case["problem"]["problem_statement"]
            assert kwargs["evidence_bundle"]["bundle_id"] == case["evidence"]["bundle_id"]
            return json.dumps(reply, ensure_ascii=False)
        with patch.object(api.orchestrator.llm_client, "mentor_review", side_effect=authored_reply) as adapter, \
             patch.object(api.get_retriever(), "retrieve", return_value=case["evidence"]):
            response = client.post("/audit", headers=headers, json=payload)
            response.raise_for_status()
            result = response.json()
            replay = client.post("/audit", headers=headers, json=payload)
            replay.raise_for_status()
            assert replay.json() == result and adapter.call_count == 1
        assert result["is_correct"] is reply["is_correct"]
        assert result["logic_alignment_score"] == reply["logic_alignment_score"]
        assert all(result[k] == reply[k] for k in ("error_analysis", "tutor_feedback", "next_hint"))
        assert result["progress_recorded"] is True
        assert [c["id"] for c in result["citations"]] == ([source["id"]] if source else [])
        if source:
            resolved = client.get(f"/knowledge/chunks/{source['id']}", params={
                "content_hash": source["content_hash"], "source_version": source["source_version"]})
            resolved.raise_for_status()
            assert resolved.json()["data"]["text"] == source["text"]
        else:
            assert result["grounding_status"] == "insufficient"
        results.append({"case_id": case["case_id"], "topic": case["topic"], "kind": case["kind"],
            "expected": case["expected"], "baseline": baseline_result,
            "review": reply, "api_result": result,
            "checks": {"verdict_matches_authored_rubric": True, "feedback_survives_api": True,
                       "citation_policy_checked": True, "source_resolves": True if source else None,
                       "retry_idempotent": True, "progress_recorded": True}})
    state = UserRepository().get_progress(learner)
    assert len(state["learning_history"]) == len(cases)
    assert sum(s["completed_count"] for s in state["topics_status"].values()) == len(cases)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--packet", type=Path, default=ROOT / ".runtime/mentor-evaluation/requests.json")
    parser.add_argument("--responses", type=Path)
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)
    folder = ROOT / ".runtime/mentor-evaluation" / uuid4().hex[:12]
    folder.mkdir(parents=True)
    os.environ.update(AI_MODE="simulation", ALLOW_PAID_API="false", RAG_ALLOW_DOWNLOAD="false",
        DATABASE_URL=f"sqlite:///{(folder / 'evaluation.db').as_posix()}", OUTPUT_DIR=str(folder / "output"))
    from src.rag import get_retriever
    retriever = get_retriever()
    if args.prepare:
        rows = read_json(ROOT / "data/evaluation/mentor_cases.json")["topics"]
        status = retriever.prepare()
        cases = packet_cases(rows, retriever)
        args.packet.parent.mkdir(parents=True, exist_ok=True)
        args.packet.write_text(json.dumps({"review_mode": "manual_assistant_file_roundtrip", "retrieval": status,
            "cases": cases}, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps({"packet": str(args.packet), "cases": len(cases), "device": status["device"]}))
        return
    if not args.responses:
        parser.error("Use --prepare, read the packet, then --responses authored.json")
    packet = read_json(args.packet)
    authored = read_json(args.responses)
    assert authored["review_mode"] == "manual_assistant_file_roundtrip"
    from fastapi.testclient import TestClient
    import api_server
    results = apply_cases(packet["cases"], authored["reviews"], TestClient(api_server.app), api_server)
    from src.rag.service import digest
    report = {"review_mode": authored["review_mode"], "paid_api_calls": 0, "database_isolated": True,
        "runtime_ai_mode": "simulation_with_manual_mentor_adapter", "retrieval_at_preparation": packet["retrieval"],
        "packet_hash": digest(packet), "response_hash": digest(authored),
        "summary": {"topics": len({c["topic"] for c in results}), "cases": len(results),
                    "api_roundtrips_passed": len(results), "independent_learning_events": len(results),
                    "baseline_supported_cases": sum(r["baseline"]["status"] == "supported" for r in results),
                    "baseline_unsupported_cases": sum(r["baseline"]["status"] != "supported" for r in results),
                    "cases_with_no_supporting_citation": sum(not r["review"]["citation_ids"] for r in results),
                    "symbolically_confirmed_ambiguous_mcqs": sum(c["kind"] == "correct" and
                        c["reference_checks"].get("mcq_single_answer_valid") is False for c in packet["cases"])},
        "mathematical_reference_checks": [{"case_id": c["case_id"], **c["reference_checks"]}
                                         for c in packet["cases"] if c["kind"] == "correct"],
        "limitations": ["Feedback and rubric were authored by the same assistant; no independent teaching-quality score.",
            "Authored development cases over small existing fixtures, not held out or a full syllabus.",
            "No live DeepSeek calls, quality estimates, latency estimates, OCR or image evaluation.",
            "MCQ verdicts remain server-key controlled; not independent AI grading accuracy.",
            "The response adapter checks integration, not whether a future model will produce these replies."],
        "manual_question_and_evidence_findings": authored["findings"],
        "results": results}
    path = ROOT / "reports/rag_mentor_remediation.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"report": str(path), **report["summary"], "paid_api_calls": 0}))


if __name__ == "__main__":
    main()
