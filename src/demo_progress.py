"""Deterministic interview-demo learning record for an existing student account."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from sqlalchemy import delete, select

from src.database.core import Database
from src.database.models import LearningEvent, TopicMastery, User


@dataclass(frozen=True)
class DemoTopic:
    mastery_score: float
    current_level: int
    completed_count: int
    incorrect_attempts: int = 0


DEMO_USER_ID = "student_01"
DEMO_TOTAL_MINUTES = 900.0
DEMO_START = datetime(2026, 3, 2, 9, 0, tzinfo=timezone.utc)
DEMO_TOPICS: tuple[tuple[str, DemoTopic], ...] = (
    ("Limits and Continuity", DemoTopic(0.85, 3, 5)),
    ("Derivatives and Differentiation", DemoTopic(0.94, 3, 8)),
    ("Integration and FTOC", DemoTopic(0.85, 3, 5, 1)),
    ("Multivariable Calculus", DemoTopic(0.81, 2, 4, 1)),
    ("Applications of Derivatives", DemoTopic(0.91, 3, 7)),
    ("Indefinite Integrals", DemoTopic(0.84, 3, 5, 1)),
    ("Applications of Integration", DemoTopic(0.82, 2, 4, 1)),
    ("Multiple Integrals", DemoTopic(0.76, 2, 4, 2)),
    ("Vector Calculus", DemoTopic(0.79, 2, 3, 1)),
    ("Sequences and Series", DemoTopic(0.85, 3, 5)),
    ("Differential Equations", DemoTopic(0.81, 2, 3, 1)),
    ("Techniques of Integration", DemoTopic(0.83, 3, 5, 1)),
    ("Parametric and Polar Curves", DemoTopic(0.82, 2, 4, 1)),
)


def _attempt_level(attempt_index: int, spec: DemoTopic) -> int:
    if spec.current_level == 1:
        return 1
    if spec.current_level == 2:
        return 1 if attempt_index < max(1, spec.completed_count // 2) else 2
    first_threshold = max(1, spec.completed_count // 3)
    second_threshold = max(first_threshold + 1, (spec.completed_count * 2) // 3)
    if attempt_index < first_threshold:
        return 1
    if attempt_index < second_threshold:
        return 2
    return 3


def _attempts_for_topic(spec: DemoTopic) -> list[tuple[float, bool, int]]:
    miss_indexes = {
        max(0, round((position + 1) * spec.completed_count / (spec.incorrect_attempts + 1)) - 1)
        for position in range(spec.incorrect_attempts)
    }
    correct_offsets = (-1, 2, 0, 3, -2, 1, 2)
    attempts: list[tuple[float, bool, int]] = []
    for index in range(spec.completed_count):
        is_correct = index not in miss_indexes
        if is_correct:
            baseline = round(spec.mastery_score * 100) + 2
            score = float(max(80, min(99, baseline + correct_offsets[index % len(correct_offsets)])))
        else:
            score = float(74 + ((index * 2 + spec.completed_count) % 5))
        attempts.append((score, is_correct, _attempt_level(index, spec)))
    return attempts


def build_demo_learning_events(user_id: str) -> list[LearningEvent]:
    """Build a deterministic, semester-shaped history that matches topic totals."""
    per_topic = {
        topic: _attempts_for_topic(spec)
        for topic, spec in DEMO_TOPICS
    }
    events: list[LearningEvent] = []
    event_index = 0
    for attempt_index in range(max(spec.completed_count for _, spec in DEMO_TOPICS)):
        for topic, _spec in DEMO_TOPICS:
            attempts = per_topic[topic]
            if attempt_index >= len(attempts):
                continue
            score, is_correct, level = attempts[attempt_index]
            occurred_at = DEMO_START + timedelta(
                hours=32 * event_index + (event_index % 3) * 2
            )
            events.append(
                LearningEvent(
                    user_id=user_id,
                    topic=topic,
                    score=score,
                    is_correct=is_correct,
                    level_at_time=level,
                    created_at=occurred_at,
                )
            )
            event_index += 1
    return events


def apply_demo_progress(database: Database, user_id: str = DEMO_USER_ID) -> Dict[str, Any]:
    """Replace one demo account's progress transactionally; credentials are untouched."""
    expected_topics = {topic for topic, _ in DEMO_TOPICS}
    with database.session() as session:
        user = session.get(User, user_id)
        if user is None:
            raise KeyError(f"Demo account does not exist: {user_id}")

        masteries = {
            row.topic: row
            for row in session.scalars(
                select(TopicMastery).where(TopicMastery.user_id == user_id)
            )
        }
        actual_topics = set(masteries)
        if actual_topics != expected_topics:
            missing = sorted(expected_topics - actual_topics)
            unexpected = sorted(actual_topics - expected_topics)
            raise ValueError(
                "Demo curriculum does not match the account. "
                f"Missing={missing}; unexpected={unexpected}"
            )

        user.total_minutes = DEMO_TOTAL_MINUTES
        for topic, spec in DEMO_TOPICS:
            mastery = masteries[topic]
            mastery.mastery_score = spec.mastery_score
            mastery.current_level = spec.current_level
            mastery.completed_count = spec.completed_count

        session.execute(
            delete(LearningEvent).where(LearningEvent.user_id == user_id)
        )
        events = build_demo_learning_events(user_id)
        session.add_all(events)

    average_mastery = round(
        sum(spec.mastery_score for _, spec in DEMO_TOPICS) / len(DEMO_TOPICS) * 100
    )
    completed = sum(spec.completed_count for _, spec in DEMO_TOPICS)
    correct = sum(event.is_correct for event in events)
    strongest_topic, strongest = max(DEMO_TOPICS, key=lambda item: item[1].mastery_score)
    weakest_topic, weakest = min(DEMO_TOPICS, key=lambda item: item[1].mastery_score)
    return {
        "user_id": user_id,
        "average_mastery_percent": average_mastery,
        "course_grade": "B",
        "completed_exercises": completed,
        "learning_events": len(events),
        "correct_attempts": correct,
        "accuracy_percent": round(correct / len(events) * 100),
        "total_minutes": DEMO_TOTAL_MINUTES,
        "strongest_domain": {
            "topic": strongest_topic,
            "mastery_percent": round(strongest.mastery_score * 100),
        },
        "next_priority": {
            "topic": weakest_topic,
            "mastery_percent": round(weakest.mastery_score * 100),
        },
    }
