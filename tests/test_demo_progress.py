from src.database import Database, UserRepository
from src.demo_progress import (
    DEMO_TOPICS,
    DEMO_TOTAL_MINUTES,
    apply_demo_progress,
)


def test_b_grade_demo_progress_is_complete_and_idempotent(tmp_path):
    database = Database(f"sqlite:///{(tmp_path / 'demo.db').as_posix()}")
    users = UserRepository(database)
    topics = [topic for topic, _ in DEMO_TOPICS]
    users.load_or_create("student_01", topics)

    first_summary = apply_demo_progress(database)
    first = users.get_progress("student_01")
    second_summary = apply_demo_progress(database)
    second = users.get_progress("student_01")

    assert first_summary == second_summary
    assert first_summary["course_grade"] == "B"
    assert first_summary["average_mastery_percent"] == 84
    assert first_summary["completed_exercises"] == 62
    assert first_summary["accuracy_percent"] == 84
    assert first_summary["next_priority"]["topic"] == "Multiple Integrals"
    assert first["metadata"]["total_minutes"] == DEMO_TOTAL_MINUTES
    assert len(first["learning_history"]) == 62
    assert len(second["learning_history"]) == 62
    assert sum(
        topic["completed_count"] for topic in second["topics_status"].values()
    ) == 62
