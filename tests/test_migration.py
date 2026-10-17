import json

from src.database import Database, GenerationRunRepository, ProblemRepository, UserRepository
from src.database.migration import LegacyJsonMigrator


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def sample_problem(identifier):
    return {
        "id": identifier,
        "topic": "Derivatives",
        "problem_statement": "Differentiate the function x squared with respect to x.",
        "question_type": "calculation",
        "difficulty": 1,
        "solution": "The derivative is 2x.",
        "scaffolding": [{"step": 1, "hint": "Apply the power rule."}],
    }


def test_json_migration_is_idempotent(tmp_path):
    write_json(
        tmp_path / "data" / "golden_dataset_v3.json",
        {"problems": [sample_problem("GOLD-1")]},
    )
    write_json(
        tmp_path / "data" / "users" / "learner_progress.json",
        {
            "metadata": {"user_id": "learner", "dataset_version": "V3"},
            "topics_status": {
                "Derivatives": {
                    "mastery_score": 0.5,
                    "current_level": 1,
                    "completed_count": 1,
                }
            },
            "learning_history": [
                {
                    "time": "2025-02-01T10:00:00",
                    "topic": "Derivatives",
                    "score": 75,
                    "level_at_time": 1,
                }
            ],
        },
    )
    write_json(tmp_path / "output" / "GEN-1.json", sample_problem("GEN-1"))
    write_json(
        tmp_path / "output" / "generation_history.json",
        {
            "batches": [
                {
                    "batch_id": "batch_fixed",
                    "topics": ["Derivatives"],
                    "total_generated": 1,
                    "mode": "drill",
                }
            ]
        },
    )

    database = Database(f"sqlite:///{(tmp_path / 'migration.db').as_posix()}")
    migrator = LegacyJsonMigrator(database=database, base_dir=tmp_path)
    first = migrator.run()
    second = migrator.run()

    assert first["database_users"] == second["database_users"] == 1
    assert ProblemRepository(database).count() == 2
    assert GenerationRunRepository(database).count() == 1
    assert len(UserRepository(database).get_progress("learner")["learning_history"]) == 1
