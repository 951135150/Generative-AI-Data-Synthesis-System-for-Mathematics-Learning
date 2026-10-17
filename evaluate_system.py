"""Generate a reproducible local comparison report without LLM calls."""

import argparse
import json
from pathlib import Path

from src.config import Config
from src.evaluation import (
    DatasetBenchmark,
    build_task_suite,
    load_problems,
    render_markdown,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Calculus Atelier generated datasets.")
    parser.add_argument("--single", type=Path, default=Path("output"))
    parser.add_argument("--multi", type=Path, default=Path("output/multi_agent"))
    parser.add_argument("--report-dir", type=Path, default=Path("reports"))
    parser.add_argument("--task-count", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    single = load_problems(args.single, exclude_directories={"multi_agent"})
    multi = load_problems(args.multi)
    report = DatasetBenchmark().compare(single, multi)

    dataset_path = Path(Config.GOLDEN_DATASET_PATH)
    golden = load_problems(dataset_path)
    topics = list(
        dict.fromkeys(
            str(problem.get("topic")) for problem in golden if problem.get("topic")
        )
    ) or ["Limits and Continuity", "Derivatives", "Integrals"]
    tasks = build_task_suite(topics, args.task_count, args.seed)
    report["task_manifest"] = {
        "seed": args.seed,
        "case_count": len(tasks),
        "file": "benchmark_tasks.json",
    }

    args.report_dir.mkdir(parents=True, exist_ok=True)
    (args.report_dir / "evaluation_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (args.report_dir / "evaluation_report.md").write_text(
        render_markdown(report), encoding="utf-8"
    )
    (args.report_dir / "benchmark_tasks.json").write_text(
        json.dumps(tasks, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
