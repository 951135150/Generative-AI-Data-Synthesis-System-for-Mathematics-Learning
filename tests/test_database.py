from src.database import (
    Database,
    GenerationRunRepository,
    ProblemRepository,
    SubmissionRepository,
    UserRepository,
)


def make_database(tmp_path):
    return Database(f"sqlite:///{(tmp_path / 'test.db').as_posix()}")


def test_user_progress_and_learning_event_are_transactional(tmp_path):
    database = make_database(tmp_path)
    users = UserRepository(database)
    legacy = {
        "metadata": {
            "user_id": "interview_user",
            "join_date": "2025-01-02",
            "total_minutes": 12.5,
            "dataset_version": "V3",
        },
        "topics_status": {
            "Derivatives": {
                "mastery_score": 0.2,
                "current_level": 1,
                "completed_count": 1,
            }
        },
        "learning_history": [
            {
                "time": "2025-01-03T10:00:00",
                "topic": "Derivatives",
                "score": 60,
                "level_at_time": 1,
            }
        ],
    }
    progress = users.load_or_create("interview_user", ["Derivatives"], legacy)
    assert progress["metadata"]["total_minutes"] == 12.5
    assert len(progress["learning_history"]) == 1

    users.record_result(
        user_id="interview_user",
        topic="Derivatives",
        score=90,
        is_correct=True,
        mastery_score=0.74,
        current_level=2,
        completed_count=2,
    )
    updated = users.get_progress("interview_user")
    assert updated["topics_status"]["Derivatives"]["current_level"] == 2
    assert len(updated["learning_history"]) == 2

    # Running the legacy seed again must not duplicate history.
    users.load_or_create("interview_user", ["Derivatives"], legacy)
    assert len(users.get_progress("interview_user")["learning_history"]) == 2


def test_problem_submission_and_generation_run_repositories(tmp_path):
    database = make_database(tmp_path)
    users = UserRepository(database)
    problems = ProblemRepository(database)
    submissions = SubmissionRepository(database)
    runs = GenerationRunRepository(database)
    users.load_or_create("student", ["Integrals"])

    problem = {
        "id": "INT-DB-1",
        "topic": "Integrals",
        "problem_statement": "Find an antiderivative of the function 2*x.",
        "question_type": "calculation",
        "difficulty": 2,
        "solution": "x^2 + C",
        "scaffolding": [{"step": 1, "hint": "Use the reverse power rule."}],
    }
    problems.upsert(problem, source="test")
    assert problems.get("INT-DB-1")["topic"] == "Integrals"
    assert problems.count() == 1

    submission_id = submissions.create(
        user_id="student",
        problem_id="INT-DB-1",
        topic="Integrals",
        score=88,
        is_correct=True,
    )
    assert submission_id.startswith("sub_")
    assert submissions.count() == 1

    runs.create(
        run_id="run_fixed",
        pipeline="multi_agent",
        topics=["Integrals"],
        target_count=1,
        generated_count=1,
        status="completed",
    )
    runs.create(
        run_id="run_fixed",
        pipeline="multi_agent",
        topics=["Integrals"],
        target_count=1,
        generated_count=1,
        status="completed",
    )
    assert runs.count() == 1
