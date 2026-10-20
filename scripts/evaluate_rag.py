"""Reproducible local retrieval smoke evaluation, never an LLM judge."""
import json
import logging
import os
import sys
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["AI_MODE"] = "simulation"
os.environ["ALLOW_PAID_API"] = "false"
os.environ["RAG_ALLOW_DOWNLOAD"] = "false"


def main():
    from src.rag.service import RetrievalService
    logging.getLogger("httpx").setLevel(logging.WARNING)
    dataset = json.loads((ROOT / "data/evaluation/rag_queries.json").read_text(encoding="utf-8"))
    report = {"split": dataset["split"], "limitations": dataset["note"], "paid_api_calls": 0, "results": {}}
    for method in ("keyword_only", "hybrid"):
        retriever = RetrievalService(use_dense=method == "hybrid")
        status = retriever.prepare()
        results = []
        for case in dataset["cases"]:
            bundle = retriever.retrieve(case["query"], top_k=5)
            ids = [c["id"] for c in bundle["evidence"]]
            relevant = set(case["relevant"])
            recall = len(set(ids) & relevant) / len(relevant) if relevant else None
            reciprocal_rank = next((1 / (i + 1) for i, key in enumerate(ids) if key in relevant), 0) if relevant else None
            results.append({**case, "retrieved": ids, "recall_at_5": recall, "reciprocal_rank": reciprocal_rank,
                            "abstained": not ids, "duration_ms": bundle["duration_ms"]})
        supported = [r for r in results if r["relevant"]]
        unknown = [r for r in results if not r["relevant"]]
        durations = sorted(r["duration_ms"] for r in results)
        report["results"][method] = {"runtime": status, "recall_at_5": mean(r["recall_at_5"] for r in supported),
            "mrr_at_5": mean(r["reciprocal_rank"] for r in supported),
            "out_of_scope_abstention": mean(float(r["abstained"]) for r in unknown),
            "warm_retrieval_p95_ms": durations[min(len(durations) - 1, int(.95 * len(durations)))], "cases": results}
    target = ROOT / "reports/rag_retrieval_smoke.json"
    target.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"report": str(target), "metrics": {k: {m: v for m, v in r.items() if m not in {"cases", "runtime"}}
          for k, r in report["results"].items()}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
