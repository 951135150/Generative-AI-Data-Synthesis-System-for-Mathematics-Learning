"""Paired, topic-stratified A/B evaluation for generation pipelines."""

import random
from collections import defaultdict
from statistics import mean
from typing import Any, Dict, Iterable, List, Optional

from src.validation import MathematicalValidator


QUESTION_TYPES = ("calculation", "mcq", "fill_in")
MODES = ("drill", "exam")
DIFFICULTIES = (1, 2, 3, 4, 5)


def build_stratified_manifest(
    topics: Iterable[str], cases_per_topic: int = 30, seed: int = 42
) -> Dict[str, Any]:
    """Create paired tasks with balanced type, mode, and difficulty strata."""
    topic_list = list(dict.fromkeys(topics))
    if len(topic_list) < 2:
        raise ValueError("A stratified benchmark requires at least two topics.")
    if cases_per_topic < 6:
        raise ValueError("cases_per_topic must be at least 6.")
    randomizer = random.Random(seed)
    full_factorial = [
        (difficulty, question_type, mode)
        for difficulty in DIFFICULTIES
        for question_type in QUESTION_TYPES
        for mode in MODES
    ]
    tasks: List[Dict[str, Any]] = []
    for topic_index, topic in enumerate(topic_list):
        strata = []
        while len(strata) < cases_per_topic:
            cycle = list(full_factorial)
            randomizer.shuffle(cycle)
            strata.extend(cycle)
        for case_index, (difficulty, question_type, mode) in enumerate(
            strata[:cases_per_topic], start=1
        ):
            pipelines = (
                ["single_agent", "multi_agent"]
                if (topic_index * cases_per_topic + case_index) % 2 == 0
                else ["multi_agent", "single_agent"]
            )
            tasks.append(
                {
                    "case_id": f"t{topic_index + 1:02d}_c{case_index:03d}",
                    "topic": topic,
                    "difficulty": difficulty,
                    "question_type": question_type,
                    "mode": mode,
                    "seed": randomizer.randint(0, 2**31 - 1),
                    "pipelines": pipelines,
                }
            )
    return {
        "benchmark_version": "2.0",
        "design": "paired_topic_stratified",
        "seed": seed,
        "topics": topic_list,
        "cases_per_topic": cases_per_topic,
        "case_count": len(tasks),
        "generation_count": len(tasks) * 2,
        "tasks": tasks,
    }


class StratifiedABEvaluator:
    def __init__(self, seed: int = 42, bootstrap_samples: int = 2000):
        self.validator = MathematicalValidator()
        self.seed = seed
        self.bootstrap_samples = bootstrap_samples

    def _score(self, record: Dict[str, Any]) -> Dict[str, Any]:
        problem = record.get("problem") if isinstance(record.get("problem"), dict) else {}
        report = self.validator.validate(problem)
        quality = problem.get("quality_score")
        if quality is None and isinstance(problem.get("evaluation"), dict):
            quality = problem["evaluation"].get("score")
        return {
            **record,
            "success": float(bool(record.get("success", problem))),
            "schema_valid": float(report.schema_valid),
            "accepted": float(report.passed),
            "symbolic_coverage": float(report.symbolic_status in {"passed", "failed"}),
            "symbolic_pass": float(report.symbolic_status == "passed"),
            "scaffolding_coverage": float(bool(problem.get("scaffolding"))),
            "integration_coverage": float(bool(problem.get("integration_analysis"))),
            "quality_score": self._number(quality),
            "duration_ms": self._number(record.get("duration_ms")),
            "total_tokens": self._number(record.get("total_tokens")),
        }

    @staticmethod
    def _number(value: Any) -> Optional[float]:
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _aggregate(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        metrics = {}
        for key in (
            "success",
            "schema_valid",
            "accepted",
            "symbolic_coverage",
            "symbolic_pass",
            "scaffolding_coverage",
            "integration_coverage",
            "quality_score",
            "duration_ms",
            "total_tokens",
        ):
            values = [row[key] for row in rows if row.get(key) is not None]
            metrics[key] = round(mean(values), 4) if values else None
        metrics["sample_size"] = len(rows)
        return metrics

    def _paired_interval(
        self, pairs: List[tuple[float, float]]
    ) -> Optional[Dict[str, float]]:
        if not pairs:
            return None
        differences = [multi - single for single, multi in pairs]
        randomizer = random.Random(self.seed)
        estimates = []
        for _ in range(self.bootstrap_samples):
            sample = [randomizer.choice(differences) for _ in differences]
            estimates.append(mean(sample))
        estimates.sort()
        low = estimates[int(0.025 * (len(estimates) - 1))]
        high = estimates[int(0.975 * (len(estimates) - 1))]
        return {
            "delta_multi_minus_single": round(mean(differences), 4),
            "ci95_low": round(low, 4),
            "ci95_high": round(high, 4),
            "matched_pairs": len(pairs),
        }

    def evaluate(self, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        scored = [self._score(record) for record in records]
        by_pipeline = defaultdict(list)
        by_topic_pipeline = defaultdict(list)
        by_case = defaultdict(dict)
        for row in scored:
            pipeline = str(row.get("pipeline", "unknown"))
            by_pipeline[pipeline].append(row)
            by_topic_pipeline[(str(row.get("topic", "Unknown")), pipeline)].append(row)
            by_case[str(row.get("case_id"))][pipeline] = row

        paired_metrics = {}
        for metric in (
            "success",
            "schema_valid",
            "accepted",
            "symbolic_coverage",
            "scaffolding_coverage",
            "integration_coverage",
            "quality_score",
            "duration_ms",
            "total_tokens",
        ):
            pairs = []
            for pipelines in by_case.values():
                single = pipelines.get("single_agent", {}).get(metric)
                multi = pipelines.get("multi_agent", {}).get(metric)
                if single is not None and multi is not None:
                    pairs.append((single, multi))
            paired_metrics[metric] = self._paired_interval(pairs)

        topics = sorted({key[0] for key in by_topic_pipeline})
        return {
            "benchmark_version": "2.0",
            "design": "paired_topic_stratified",
            "pipelines": {
                pipeline: self._aggregate(rows)
                for pipeline, rows in sorted(by_pipeline.items())
            },
            "paired_differences": paired_metrics,
            "by_topic": {
                topic: {
                    pipeline: self._aggregate(by_topic_pipeline[(topic, pipeline)])
                    for pipeline in ("single_agent", "multi_agent")
                    if by_topic_pipeline[(topic, pipeline)]
                }
                for topic in topics
            },
        }


def render_ab_markdown(report: Dict[str, Any]) -> str:
    lines = [
        "# Calculus Atelier Stratified A/B Benchmark",
        "",
        "Paired design: the same topic, difficulty, question type, and mode are sent to both pipelines.",
        "",
        "| Metric | Single-agent | Multi-agent | Paired delta | 95% CI |",
        "|---|---:|---:|---:|---:|",
    ]
    labels = {
        "success": "Generation success",
        "schema_valid": "Schema valid",
        "accepted": "Deterministic acceptance",
        "symbolic_coverage": "Symbolic coverage",
        "scaffolding_coverage": "Scaffolding coverage",
        "integration_coverage": "Integration coverage",
        "quality_score": "Quality score",
        "duration_ms": "Duration (ms)",
        "total_tokens": "Tokens",
    }
    single = report.get("pipelines", {}).get("single_agent", {})
    multi = report.get("pipelines", {}).get("multi_agent", {})
    for key, label in labels.items():
        interval = report.get("paired_differences", {}).get(key)
        delta = interval.get("delta_multi_minus_single") if interval else None
        ci = (
            f"[{interval['ci95_low']}, {interval['ci95_high']}]"
            if interval else "N/A"
        )
        lines.append(
            f"| {label} | {single.get(key, 'N/A')} | {multi.get(key, 'N/A')} | "
            f"{delta if delta is not None else 'N/A'} | {ci} |"
        )
    lines.extend(
        [
            "",
            "Positive deltas favor the multi-agent pipeline except for duration and token use, where lower is preferable.",
        ]
    )
    return "\n".join(lines) + "\n"
