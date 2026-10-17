"""Idempotent migration from legacy JSON artifacts into SQLite."""

import json
import logging
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from src.config import Config
from src.database.core import Database
from src.database.repositories import (
    GenerationRunRepository,
    ProblemRepository,
    UserRepository,
)

logger = logging.getLogger(__name__)


def extract_problems(payload: Any) -> List[Dict[str, Any]]:
    """Extract problem objects from individual and aggregate JSON formats."""
    if isinstance(payload, list):
        return [
            item
            for item in payload
            if isinstance(item, dict) and "problem_statement" in item
        ]
    if not isinstance(payload, dict):
        return []
    if "problem_statement" in payload:
        return [payload]
    for key in ("problems", "data", "generated_problems"):
        nested = payload.get(key)
        if isinstance(nested, list):
            return [
                item
                for item in nested
                if isinstance(item, dict) and "problem_statement" in item
            ]
    return []


class LegacyJsonMigrator:
    """Imports data without deleting or rewriting the source JSON files."""

    def __init__(
        self,
        database: Optional[Database] = None,
        base_dir: Optional[Path] = None,
    ):
        self.database = database or Database()
        self.base_dir = Path(base_dir or Config.BASE_DIR)
        self.users = UserRepository(self.database)
        self.problems = ProblemRepository(self.database)
        self.runs = GenerationRunRepository(self.database)

    @staticmethod
    def _read_json(path: Path) -> Any:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)

    def import_users(self) -> int:
        imported = 0
        user_dir = self.base_dir / "data" / "users"
        if not user_dir.exists():
            return 0
        for path in sorted(user_dir.glob("*_progress.json")):
            try:
                data = self._read_json(path)
                fallback_id = path.name.removesuffix("_progress.json")
                user_id = str(data.get("metadata", {}).get("user_id") or fallback_id)
                roadmap = list(data.get("topics_status", {}).keys())
                self.users.load_or_create(user_id, roadmap, data)
                imported += 1
            except Exception as exc:
                logger.warning("Skipping user file %s: %s", path, exc)
        return imported

    def import_golden_dataset(self) -> int:
        configured_path = Path(Config.GOLDEN_DATASET_PATH)
        local_candidate = self.base_dir / "data" / configured_path.name
        path = local_candidate if local_candidate.exists() else configured_path
        if not path.is_absolute():
            path = self.base_dir / path
        if not path.exists():
            return 0
        return self.problems.upsert_many(
            extract_problems(self._read_json(path)), source="golden"
        )

    def import_generated_outputs(self) -> int:
        output_dir = self.base_dir / "output"
        if not output_dir.exists():
            return 0
        imported_ids = set()
        skip_names = {"generation_history.json", "synthesis_metadata.json"}
        for path in sorted(output_dir.rglob("*.json")):
            if path.name in skip_names:
                continue
            try:
                source = (
                    "multi_agent"
                    if "multi_agent" in {part.lower() for part in path.parts}
                    else "single_agent"
                )
                for problem in extract_problems(self._read_json(path)):
                    identifier = problem.get("problem_id") or problem.get("id")
                    if not identifier:
                        continue
                    self.problems.upsert(problem, source=source)
                    imported_ids.add(str(identifier))
            except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
                logger.warning("Skipping output file %s: %s", path, exc)
        return len(imported_ids)

    def import_generation_history(self) -> int:
        history_path = self.base_dir / "output" / "generation_history.json"
        if not history_path.exists():
            return 0
        payload = self._read_json(history_path)
        imported = 0
        for batch in payload.get("batches", []):
            run_id = batch.get("batch_id")
            if not run_id:
                continue
            generated = int(batch.get("total_generated", 0) or 0)
            self.runs.create(
                run_id=str(run_id),
                pipeline="single_agent",
                topics=batch.get("topics", []),
                target_count=int(batch.get("target_count", generated) or generated),
                generated_count=generated,
                status="completed" if generated else "empty",
                mode=str(batch.get("mode", "legacy")),
                question_type=str(batch.get("question_type", "mixed")),
                difficulty=int(batch.get("difficulty", 1) or 1),
                created_at=_parse_migration_datetime(batch.get("generated_at")),
            )
            imported += 1
        return imported

    def run(self) -> Dict[str, int]:
        processed = {
            "user_files": self.import_users(),
            "golden_problems": self.import_golden_dataset(),
            "generated_problems": self.import_generated_outputs(),
            "generation_runs": self.import_generation_history(),
        }
        processed["database_users"] = self.users.count()
        processed["database_problems"] = self.problems.count()
        processed["database_generation_runs"] = self.runs.count()
        return processed


def _parse_migration_datetime(value: Any):
    if not value:
        return None
    try:
        from datetime import datetime

        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
