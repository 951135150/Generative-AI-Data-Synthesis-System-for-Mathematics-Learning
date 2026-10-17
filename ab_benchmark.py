"""Prepare, execute, and evaluate the paired stratified A/B benchmark."""

import argparse
import asyncio
import json
import time
from pathlib import Path
from typing import Any, Dict, List

import httpx

from src.config import Config
from src.database.migration import extract_problems
from src.evaluation.stratified_ab import (
    StratifiedABEvaluator,
    build_stratified_manifest,
    render_ab_markdown,
)


def _golden_topics(limit: int) -> List[str]:
    payload = json.loads(Path(Config.GOLDEN_DATASET_PATH).read_text(encoding="utf-8"))
    topics = list(
        dict.fromkeys(
            str(problem.get("topic"))
            for problem in extract_problems(payload)
            if problem.get("topic")
        )
    )
    return topics[:limit]


def prepare(args) -> None:
    manifest = build_stratified_manifest(
        _golden_topics(args.topic_count), args.cases_per_topic, args.seed
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in manifest.items() if key != "tasks"}, indent=2))


def _append_jsonl(path: Path, record: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")


async def execute(args) -> None:
    if not args.confirm_live_calls:
        raise SystemExit("Live execution can incur model cost; pass --confirm-live-calls.")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    completed = set()
    if args.output.exists():
        for line in args.output.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                completed.add((row.get("case_id"), row.get("pipeline")))
    tasks = manifest["tasks"][: args.limit or None]
    async with httpx.AsyncClient(base_url=args.api_url, timeout=700) as client:
        for task in tasks:
            for pipeline in task["pipelines"]:
                key = (task["case_id"], pipeline)
                if key in completed:
                    continue
                request = {
                    "topics": [task["topic"]],
                    "mode": task["mode"],
                    "difficulty": task["difficulty"],
                    "question_type": task["question_type"],
                }
                started = time.perf_counter()
                try:
                    if pipeline == "single_agent":
                        response = await client.post("/generate", json={**request, "num": 1})
                        response.raise_for_status()
                        problem = response.json().get("data", [None])[0]
                        metadata = {}
                    else:
                        response = await client.post("/synthesize", json={**request, "count": 1})
                        response.raise_for_status()
                        body = response.json()
                        problem = body.get("problems", [None])[0]
                        metadata = {"total_llm_calls": body.get("total_llm_calls")}
                    record = {
                        **task,
                        "pipeline": pipeline,
                        "success": bool(problem),
                        "problem": problem,
                        "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                        **metadata,
                    }
                except Exception as exc:
                    record = {
                        **task,
                        "pipeline": pipeline,
                        "success": False,
                        "problem": None,
                        "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                        "error": str(exc),
                    }
                _append_jsonl(args.output, record)


def evaluate(args) -> None:
    records = [
        json.loads(line)
        for line in args.results.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    report = StratifiedABEvaluator(seed=args.seed).evaluate(records)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    args.output.with_suffix(".md").write_text(render_ab_markdown(report), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--topic-count", type=int, default=10)
    prepare_parser.add_argument("--cases-per-topic", type=int, default=30)
    prepare_parser.add_argument("--seed", type=int, default=42)
    prepare_parser.add_argument("--output", type=Path, default=Path("reports/ab_manifest.json"))
    prepare_parser.set_defaults(handler=prepare)

    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--manifest", type=Path, default=Path("reports/ab_manifest.json"))
    run_parser.add_argument("--output", type=Path, default=Path("reports/ab_results.jsonl"))
    run_parser.add_argument("--api-url", default="http://127.0.0.1:8001")
    run_parser.add_argument("--limit", type=int, default=0)
    run_parser.add_argument("--confirm-live-calls", action="store_true")
    run_parser.set_defaults(handler=lambda args: asyncio.run(execute(args)))

    evaluate_parser = subparsers.add_parser("evaluate")
    evaluate_parser.add_argument("--results", type=Path, default=Path("reports/ab_results.jsonl"))
    evaluate_parser.add_argument("--output", type=Path, default=Path("reports/ab_report.json"))
    evaluate_parser.add_argument("--seed", type=int, default=42)
    evaluate_parser.set_defaults(handler=evaluate)

    args = parser.parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
