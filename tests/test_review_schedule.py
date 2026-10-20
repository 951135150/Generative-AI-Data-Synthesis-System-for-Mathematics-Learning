from datetime import datetime, timedelta, timezone

from src.learning.service import recommend, review_schedule
from src.rag.service import RetrievalService

NOW = datetime(2026, 10, 20, 10, tzinfo=timezone.utc)
TOPIC = "Derivatives and Differentiation"


def progress(count=3, days=9, correct=True):
    return {"topics_status": {TOPIC: {"mastery_score": .9, "completed_count": count, "current_level": 3}},
            "learning_history": [{"topic": TOPIC, "time": (NOW - timedelta(days=days, minutes=count-i)).isoformat(),
                                  "score": 100 if correct else 0, "is_correct": correct} for i in range(count)]}


def test_review_dates_follow_recorded_streaks():
    result = review_schedule(progress(), NOW)
    assert len(result) == 1
    assert result[0]["interval_days"] == 7
    assert result[0]["overdue_days"] == 2
    assert review_schedule(progress(count=5, days=15), NOW)[0]["interval_days"] == 14


def test_recent_future_and_insufficient_records_do_not_create_due_reviews():
    assert review_schedule(progress(days=1), NOW) == []
    assert review_schedule(progress(count=2), NOW) == []
    assert review_schedule(progress(days=-1), NOW) == []
    assert review_schedule(progress(correct=False), NOW) == []
    malformed = progress()
    for item in malformed["learning_history"]:
        item["time"] = "unknown"
    assert review_schedule(malformed, NOW) == []


def test_due_review_is_explained_and_prerequisites_still_apply(tmp_path):
    retriever = RetrievalService(cache_dir=tmp_path, use_dense=False)
    response = recommend(progress(), retriever, now=NOW)
    assert response["topic"] == TOPIC
    assert response["basis"] == "spaced_review_rule"
    assert "after 7 days" in response["reason"]


def test_unpracticed_foundations_are_not_displaced_by_recent_strength(tmp_path):
    state = progress(days=1)
    state["topics_status"]["Limits and Continuity"] = {"mastery_score": 0, "completed_count": 0, "current_level": 1}
    response = recommend(state, RetrievalService(cache_dir=tmp_path, use_dense=False), now=NOW)
    assert response["topic"] == "Limits and Continuity"
