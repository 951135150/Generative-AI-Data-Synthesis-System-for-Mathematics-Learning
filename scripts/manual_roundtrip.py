"""Export a real mentor prompt; re-inject a human/assistant response without any API."""
import argparse
import json
import os
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
FOLDER = ROOT / ".runtime" / "manual-review"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--response", type=Path)
    args = parser.parse_args()
    os.environ["AI_MODE"] = "simulation"
    os.environ["ALLOW_PAID_API"] = "false"
    from src.rag import get_retriever
    from src.grading import assess_mcq
    from src.llm_client import LLMClient
    from src.simulation import make_problem
    from src.rag.service import validate_citations
    FOLDER.mkdir(parents=True, exist_ok=True)
    request_path = FOLDER / "request.json"
    if args.prepare:
        problem = make_problem("Derivatives and Differentiation", variant=1)
        assessment = assess_mcq(problem, "A")
        bundle = get_retriever().retrieve("chain rule inner derivative", topics=[problem["topic"]], purpose="tutor")
        captured = {}
        llm = LLMClient.__new__(LLMClient)
        llm.generate = lambda **kwargs: captured.update(kwargs) or "{}"
        llm.mentor_review(problem_data=problem, student_text_answer="Selected option A: " + assessment.selected_content,
                          mcq_assessment=assessment.to_dict(), evidence_bundle=bundle)
        request = {"problem": problem, "assessment": assessment.to_dict(), "evidence": bundle,
                   "actual_mentor_prompt": captured["prompt"], "response_schema": {
                       "is_correct": False, "logic_alignment_score": 0, "error_analysis": "string",
                       "tutor_feedback": "string", "next_hint": "string", "citation_ids": ["C1"]}}
        request_path.write_text(json.dumps(request, indent=2, ensure_ascii=False), encoding="utf-8")
        print(str(request_path))
        return
    if not args.response:
        parser.error("Use --prepare first, then --response path/to/response.json")
    request = json.loads(request_path.read_text(encoding="utf-8"))
    response = json.loads(args.response.read_text(encoding="utf-8"))
    assert response["is_correct"] is request["assessment"]["is_correct"]
    assert response["logic_alignment_score"] == (100 if response["is_correct"] else 0)
    citations = validate_citations(response, request["evidence"])
    assert citations["citations"], "A source-supported response is required for this roundtrip."
    # Run the regular API with only its model reply replaced by the supplied response.
    os.environ["DATABASE_URL"] = f"sqlite:///{(FOLDER / ('roundtrip_' + uuid4().hex[:8] + '.db')).as_posix()}"
    os.environ["OUTPUT_DIR"] = str(FOLDER / "output")
    import api_server
    from fastapi.testclient import TestClient
    from unittest.mock import patch
    from src.database.models import AttemptReceipt
    api_server.problem_repository.upsert(request["problem"], source="manual_test")
    client = TestClient(api_server.app)
    with patch.object(api_server.orchestrator.llm_client, "mentor_review", return_value=json.dumps(response)), \
         patch.object(api_server.get_retriever(), "retrieve", return_value=request["evidence"]):
        result = client.post("/audit", json={"problem_id": request["problem"]["id"],
                             "selected_option": "A", "attempt_id": uuid4().hex})
    result.raise_for_status()
    assert result.json()["is_correct"] is False
    assert result.json()["citations"]
    target = ROOT / "reports" / "rag_manual_roundtrip.json"
    target.write_text(json.dumps({"review_mode": "manual_assistant_response", "paid_api_calls": 0,
        "note": "Response authored in the chat and injected through a test adapter, not an API service.",
        "response": result.json()}, indent=2, ensure_ascii=False), encoding="utf-8")
    print(str(target))


if __name__ == "__main__":
    main()
