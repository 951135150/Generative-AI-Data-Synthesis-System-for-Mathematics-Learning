"""Manual feedback replay is an integration test, not independent teacher review."""
import pytest
from fastapi.testclient import TestClient

import api_server
from scripts.evaluate_manual_mentor import ROOT, apply_cases, packet_cases, read_json, verify_reference
from src.rag import get_retriever
from src.simulation import make_problem

ROWS = read_json(ROOT / "data/evaluation/mentor_cases.json")["topics"]


@pytest.mark.parametrize("row", ROWS, ids=[r["topic"] for r in ROWS])
def test_independent_reference_and_reviewed_option_transcriptions(row):
    checks = verify_reference(row, make_problem(row["topic"], difficulty=3, variant=1))
    assert checks["independent_formula_agrees"]
    if row.get("reviewed_options"):
        assert checks["mcq_valid_option_keys"] == ["D"]
        assert checks["mcq_single_answer_valid"] is True


def test_all_manually_authored_reviews_survive_the_real_audit_path():
    cases = packet_cases(ROWS, get_retriever())
    authored = read_json(ROOT / "data/evaluation/manual_mentor_reviews.json")
    results = apply_cases(cases, authored["reviews"], TestClient(api_server.app), api_server)
    assert len(results) == 52
    assert sum(r["baseline"]["status"] == "unsupported_freeform" for r in results) == 13
    unsupported_evidence = [r for r in results if not r["review"]["citation_ids"]]
    assert unsupported_evidence == []
