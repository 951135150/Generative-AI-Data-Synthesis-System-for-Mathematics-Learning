"""Reproducible offline comparison for single- and multi-agent outputs."""

import hashlib
import json
import random
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Iterable, List, Optional

from src.database.migration import extract_problems
from src.validation import MathematicalValidator


def _normalized_statement(problem: Dict[str, Any]) -> str:
    text = str(problem.get("problem_statement", "")).lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text)).strip()


def _quality_score(problem: Dict[str, Any]) -> Optional[float]:
    score = problem.get("quality_score")
    if score is None and isinstance(problem.get("evaluation"), dict):
        score = problem["evaluation"].get("score")
    try:
        return float(score) if score is not None else None
    except (TypeError, ValueError):
        return None


def load_problems(path: Path, exclude_directories: Iterable[str] = ()) -> List[Dict[str, Any]]:
    """Load and de-duplicate individual or aggregate problem artifacts."""
    path = Path(path)
    excluded = {name.lower() for name in exclude_directories}
    files = [path] if path.is_file() else sorted(path.rglob("*.json"))
    unique: Dict[str, Dict[str, Any]] = {}
    for file_path in files:
        if any(part.lower() in excluded for part in file_path.parts):
            continue
        if file_path.name in {"generation_history.json", "synthesis_metadata.json"}:
            continue
        try:
            with file_path.open("r", encoding="utf-8") as file:
                payload = json.load(file)
        except (OSError, json.JSONDecodeError):
            continue
        for problem in extract_problems(payload):
            identifier = str(problem.get("problem_id") or problem.get("id") or "")
            key = identifier or hashlib.sha256(
                _normalized_statement(problem).encode("utf-8")
            ).hexdigest()
            unique[key] = problem
    return list(unique.values())


@dataclass
class BenchmarkMetrics:
    total: int
    schema_valid_rate: float
    deterministic_accept_rate: float
    symbolic_coverage_rate: float
    symbolic_pass_rate: float
    scaffolding_coverage_rate: float
    integration_coverage_rate: float
    duplicate_rate: float
    topic_count: int
    average_quality_score: Optional[float]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class DatasetBenchmark:
    def __init__(self):
        self.validator = MathematicalValidator()

    def evaluate(self, problems: List[Dict[str, Any]]) -> BenchmarkMetrics:
        if not problems:
            return BenchmarkMetrics(0, 0, 0, 0, 0, 0, 0, 0, 0, None)

        reports = [self.validator.validate(problem) for problem in problems]
        symbolic = [
            report
            for report in reports
            if report.symbolic_status in {"passed", "failed"}
        ]
        statements = [_normalized_statement(problem) for problem in problems]
        nonempty_statements = [statement for statement in statements if statement]
        duplicate_count = len(nonempty_statements) - len(set(nonempty_statements))
        quality_scores = [
            value for value in (_quality_score(problem) for problem in problems)
            if value is not None
        ]
        total = len(problems)
        return BenchmarkMetrics(
            total=total,
            schema_valid_rate=round(sum(r.schema_valid for r in reports) / total, 4),
            deterministic_accept_rate=round(sum(r.passed for r in reports) / total, 4),
            symbolic_coverage_rate=round(len(symbolic) / total, 4),
            symbolic_pass_rate=round(
                sum(r.symbolic_status == "passed" for r in symbolic) / len(symbolic), 4
            ) if symbolic else 0.0,
            scaffolding_coverage_rate=round(
                sum(bool(problem.get("scaffolding")) for problem in problems) / total, 4
            ),
            integration_coverage_rate=round(
                sum(bool(problem.get("integration_analysis")) for problem in problems)
                / total,
                4,
            ),
            duplicate_rate=round(duplicate_count / total, 4),
            topic_count=len(
                {str(problem.get("topic")) for problem in problems if problem.get("topic")}
            ),
            average_quality_score=round(mean(quality_scores), 2)
            if quality_scores
            else None,
        )

    def compare(
        self,
        single_agent: List[Dict[str, Any]],
        multi_agent: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        single = self.evaluate(single_agent).to_dict()
        multi = self.evaluate(multi_agent).to_dict()
        delta = {}
        for key in (
            "schema_valid_rate",
            "deterministic_accept_rate",
            "symbolic_coverage_rate",
            "scaffolding_coverage_rate",
            "integration_coverage_rate",
            "duplicate_rate",
            "average_quality_score",
        ):
            left, right = single.get(key), multi.get(key)
            delta[key] = (
                round(right - left, 4)
                if isinstance(left, (int, float)) and isinstance(right, (int, float))
                else None
            )
        return {
            "benchmark_version": "1.0",
            "single_agent": single,
            "multi_agent": multi,
            "delta_multi_minus_single": delta,
        }


def build_task_suite(
    topics: List[str], size: int = 100, seed: int = 42
) -> List[Dict[str, Any]]:
    """Build a fixed task manifest for future live A/B generation runs."""
    randomizer = random.Random(seed)
    question_types = ["calculation", "mcq", "fill_in"]
    modes = ["drill", "exam"]
    suite = []
    for index in range(size):
        suite.append(
            {
                "case_id": f"case_{index + 1:03d}",
                "topic": topics[index % len(topics)],
                "difficulty": 1 + (index % 5),
                "question_type": question_types[index % len(question_types)],
                "mode": modes[index % len(modes)],
                "seed": randomizer.randint(0, 2**31 - 1),
            }
        )
    return suite


def render_markdown(report: Dict[str, Any]) -> str:
    single = report["single_agent"]
    multi = report["multi_agent"]
    labels = [
        ("Problem count", "total", False),
        ("Schema valid", "schema_valid_rate", True),
        ("Deterministic acceptance", "deterministic_accept_rate", True),
        ("Symbolic coverage", "symbolic_coverage_rate", True),
        ("Symbolic pass", "symbolic_pass_rate", True),
        ("Scaffolding coverage", "scaffolding_coverage_rate", True),
        ("Integration coverage", "integration_coverage_rate", True),
        ("Duplicate rate", "duplicate_rate", True),
        ("Topic count", "topic_count", False),
        ("Average quality score", "average_quality_score", False),
    ]
    lines = [
        "# Calculus Atelier Offline Evaluation Report",
        "",
        "| Metric | Single-agent | Multi-agent |",
        "|---|---:|---:|",
    ]
    for label, key, percentage in labels:
        def format_value(value):
            if value is None:
                return "N/A"
            return f"{value * 100:.1f}%" if percentage else str(value)
        lines.append(
            f"| {label} | {format_value(single[key])} | {format_value(multi[key])} |"
        )
    lines.extend(
        [
            "",
            "Generated by deterministic local validation; no paid model calls are made.",
            "The task manifest fixes topic, difficulty, type, mode, and random seed for future live A/B runs.",
        ]
    )
    return "\n".join(lines) + "\n"
