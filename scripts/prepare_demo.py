"""Prepare an isolated demonstration learner through the real API, never personal data."""
import argparse
import json
import logging
import os
import secrets
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def configure(folder):
    folder = Path(folder).resolve()
    if not folder.is_relative_to(ROOT / ".runtime" / "demo"):
        raise ValueError("Demo data must stay inside this project's .runtime/demo directory.")
    os.environ.update(AI_MODE="simulation", ALLOW_PAID_API="false", RAG_ALLOW_DOWNLOAD="false",
                      DATABASE_URL=f"sqlite:///{(folder / 'demo.db').as_posix()}", OUTPUT_DIR=str(folder / "output"))
    return folder


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--folder", required=True, type=Path)
    parser.add_argument("--solve", help="Solve the stored function independently from its symbolic source, not the answer key.")
    args = parser.parse_args()
    folder = configure(args.folder)
    logging.basicConfig(level=logging.WARNING)
    if args.solve:
        import sympy as sp
        from src.database import ProblemRepository
        from src.validation import MathematicalValidator
        problem = ProblemRepository().get(args.solve)
        claim = problem["symbolic_validation"]
        assert claim["operation"] == "differentiate"
        x = sp.Symbol(claim.get("variable", "x"), real=True)
        source = MathematicalValidator()._parse_expression(claim["source_expression"], x)
        print(json.dumps({"expression": str(sp.expand(sp.diff(source, x))), "method": "differentiate_source_expression"}))
        return
    if (folder / "demo.db").exists():
        raise ValueError("Use a new demo folder; existing data is never overwritten.")
    folder.mkdir(parents=True, exist_ok=True)
    import api_server
    from fastapi.testclient import TestClient
    from src.rag import get_retriever
    from src.simulation import SIMULATION_TOPICS
    client = TestClient(api_server.app)
    user_id = "demo_learner"
    password = "Demo-" + secrets.token_urlsafe(20) + "9!"
    registered = client.post("/auth/register", json={"user_id": user_id, "password": password})
    registered.raise_for_status()
    headers = {"Authorization": "Bearer " + registered.json()["access_token"]}
    patterns = {
        "Limits and Continuity": (True, False, True),
        "Vector Calculus": (True, True, False),
        "Techniques of Integration": (True, True, False),
        "Applications of Integration": (True, False, True),
        "Multiple Integrals": (True, False, True),
    }
    strong = {"Derivatives and Differentiation", "Applications of Derivatives", "Multivariable Calculus", "Parametric and Polar Curves"}
    for round_index, kind in enumerate(("mcq", "calculation", "fill_in")):
        for topic in SIMULATION_TOPICS:
            correct = (True, True, True)[round_index] if topic in strong else patterns.get(topic, (False, True, True))[round_index]
            response = client.post("/generate", headers=headers, json={"topics": [topic], "user_id": user_id,
                                  "question_type": kind, "difficulty": 3})
            response.raise_for_status()
            visible = response.json()["data"][0]
            canonical = api_server.problem_repository.get(visible["id"])
            payload = {"user_id": user_id, "problem_id": visible["id"], "attempt_id": uuid4().hex}
            if kind == "mcq":
                payload["selected_option"] = canonical["answer"] if correct else next(k for k in canonical["options"] if k != canonical["answer"])
            else:
                payload["text_answer"] = canonical["expected_expression"] if correct else "0"
            graded = client.post("/audit", json=payload, headers=headers)
            graded.raise_for_status()
            assert graded.json()["is_correct"] is correct
    progress = client.get(f"/user/progress/{user_id}", headers=headers)
    progress.raise_for_status()
    count = sum(s["completed_count"] for s in progress.json()["topics_status"].values())
    assert count == 39
    config = {"user_id": user_id, "password": password, "folder": str(folder),
              "database_url": os.environ["DATABASE_URL"], "initial_independent_attempts": count,
              "seed_note": "39 scripted practice answers via real API, synthetic history, not course grades.",
              "retrieval": get_retriever().status()}
    (folder / "private_config.json").write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"folder": str(folder), "user_id": user_id, "initial_independent_attempts": count,
                      "paid_api_calls": 0, "device": config["retrieval"]["device"]}))


if __name__ == "__main__":
    main()
