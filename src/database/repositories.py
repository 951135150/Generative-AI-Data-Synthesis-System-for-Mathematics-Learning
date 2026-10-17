"""Repository layer used by the API, migration, and evaluation tooling."""

import json
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional
from uuid import uuid4

from sqlalchemy import func, select

from src.database.core import Database, get_database
from src.database.models import (
    AuthSession,
    GenerationRun,
    LearningEvent,
    ProblemRecord,
    Submission,
    TopicMastery,
    User,
)


def _parse_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _plain_dict(value: Any) -> Dict[str, Any]:
    if hasattr(value, "to_compatible_dict"):
        return value.to_compatible_dict()
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", exclude_none=True)
    return dict(value)


class UserRepository:
    def __init__(self, database: Optional[Database] = None):
        self.database = database or get_database()

    def load_or_create(
        self,
        user_id: str,
        roadmap: Iterable[str],
        legacy_progress: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        legacy = legacy_progress or {}
        metadata = legacy.get("metadata", {})
        legacy_topics = legacy.get("topics_status", {})
        with self.database.session() as session:
            user = session.get(User, user_id)
            is_new = user is None
            if user is None:
                joined_at = _parse_datetime(metadata.get("join_date"))
                user = User(
                    user_id=user_id,
                    joined_at=joined_at or datetime.now().astimezone(),
                    total_minutes=float(metadata.get("total_minutes", 0) or 0),
                    dataset_version=str(metadata.get("dataset_version", "V3")),
                )
                session.add(user)
                session.flush()

            existing = {
                row.topic: row
                for row in session.scalars(
                    select(TopicMastery).where(TopicMastery.user_id == user_id)
                )
            }
            ordered_topics = list(
                dict.fromkeys([*roadmap, *legacy_topics.keys(), *existing.keys()])
            )
            for topic in ordered_topics:
                if topic in existing:
                    continue
                old = legacy_topics.get(topic, {}) if is_new else {}
                session.add(
                    TopicMastery(
                        user_id=user_id,
                        topic=topic,
                        mastery_score=float(old.get("mastery_score", 0.0) or 0.0),
                        current_level=int(old.get("current_level", 1) or 1),
                        completed_count=int(old.get("completed_count", 0) or 0),
                    )
                )

            has_events = session.scalar(
                select(func.count(LearningEvent.id)).where(
                    LearningEvent.user_id == user_id
                )
            )
            if is_new and not has_events:
                for item in legacy.get("learning_history", []):
                    session.add(
                        LearningEvent(
                            user_id=user_id,
                            topic=str(item.get("topic", "Unknown")),
                            score=float(item.get("score", 0) or 0),
                            is_correct=bool(
                                item.get("is_correct", float(item.get("score", 0) or 0) >= 80)
                            ),
                            level_at_time=int(item.get("level_at_time", 1) or 1),
                            created_at=_parse_datetime(item.get("time"))
                            or datetime.now().astimezone(),
                        )
                    )
        return self.get_progress(user_id)

    def get_progress(self, user_id: str) -> Dict[str, Any]:
        with self.database.session() as session:
            user = session.get(User, user_id)
            if user is None:
                raise KeyError(f"User not found: {user_id}")
            masteries = list(
                session.scalars(
                    select(TopicMastery)
                    .where(TopicMastery.user_id == user_id)
                    .order_by(TopicMastery.id)
                )
            )
            events = list(
                session.scalars(
                    select(LearningEvent)
                    .where(LearningEvent.user_id == user_id)
                    .order_by(LearningEvent.created_at, LearningEvent.id)
                )
            )
            return {
                "metadata": {
                    "user_id": user.user_id,
                    "join_date": user.joined_at.date().isoformat(),
                    "total_minutes": float(user.total_minutes),
                    "dataset_version": user.dataset_version,
                },
                "topics_status": {
                    row.topic: {
                        "mastery_score": row.mastery_score,
                        "current_level": row.current_level,
                        "completed_count": row.completed_count,
                    }
                    for row in masteries
                },
                "learning_history": [
                    {
                        "time": row.created_at.isoformat(),
                        "topic": row.topic,
                        "score": row.score,
                        "is_correct": row.is_correct,
                        "level_at_time": row.level_at_time,
                    }
                    for row in events
                ],
            }

    def save_progress(self, user_id: str, progress: Dict[str, Any]) -> None:
        with self.database.session() as session:
            user = session.get(User, user_id)
            if user is None:
                raise KeyError(f"User not found: {user_id}")
            metadata = progress.get("metadata", {})
            user.total_minutes = float(metadata.get("total_minutes", 0) or 0)
            user.dataset_version = str(metadata.get("dataset_version", user.dataset_version))
            existing = {
                row.topic: row
                for row in session.scalars(
                    select(TopicMastery).where(TopicMastery.user_id == user_id)
                )
            }
            for topic, state in progress.get("topics_status", {}).items():
                mastery = existing.get(topic)
                if mastery is None:
                    mastery = TopicMastery(user_id=user_id, topic=topic)
                    session.add(mastery)
                mastery.mastery_score = float(state.get("mastery_score", 0) or 0)
                mastery.current_level = int(state.get("current_level", 1) or 1)
                mastery.completed_count = int(state.get("completed_count", 0) or 0)

    def record_result(
        self,
        user_id: str,
        topic: str,
        score: float,
        is_correct: bool,
        mastery_score: float,
        current_level: int,
        completed_count: int,
        occurred_at: Optional[datetime] = None,
    ) -> int:
        with self.database.session() as session:
            mastery = session.scalar(
                select(TopicMastery).where(
                    TopicMastery.user_id == user_id, TopicMastery.topic == topic
                )
            )
            if mastery is None:
                mastery = TopicMastery(user_id=user_id, topic=topic)
                session.add(mastery)
            mastery.mastery_score = mastery_score
            mastery.current_level = current_level
            mastery.completed_count = completed_count
            event = LearningEvent(
                user_id=user_id,
                topic=topic,
                score=score,
                is_correct=is_correct,
                level_at_time=current_level,
                created_at=occurred_at or datetime.now().astimezone(),
            )
            session.add(event)
            session.flush()
            return event.id

    def count(self) -> int:
        with self.database.session() as session:
            return int(session.scalar(select(func.count(User.user_id))) or 0)


class AuthRepository:
    """Persistence operations for password credentials and opaque sessions."""

    def __init__(self, database: Optional[Database] = None):
        self.database = database or get_database()

    def create_user(
        self,
        *,
        user_id: str,
        password_hash: str,
        password_salt: str,
        password_iterations: int,
        role: str = "student",
    ) -> str:
        with self.database.session() as session:
            existing = session.get(User, user_id)
            if existing is not None:
                return "exists" if existing.password_hash else "legacy"
            session.add(
                User(
                    user_id=user_id,
                    password_hash=password_hash,
                    password_salt=password_salt,
                    password_iterations=password_iterations,
                    role=role,
                    is_active=True,
                    dataset_version="V3",
                )
            )
        return "created"

    def set_password(
        self,
        user_id: str,
        password_hash: str,
        password_salt: str,
        password_iterations: int,
    ) -> bool:
        with self.database.session() as session:
            user = session.get(User, user_id)
            if user is None:
                return False
            user.password_hash = password_hash
            user.password_salt = password_salt
            user.password_iterations = password_iterations
            user.is_active = True
        return True

    def get_credentials(self, user_id: str) -> Optional[Dict[str, Any]]:
        with self.database.session() as session:
            user = session.get(User, user_id)
            if user is None:
                return None
            return {
                "user_id": user.user_id,
                "password_hash": user.password_hash,
                "password_salt": user.password_salt,
                "password_iterations": user.password_iterations,
                "role": user.role,
                "is_active": user.is_active,
            }

    def create_session(
        self,
        *,
        session_id: str,
        user_id: str,
        token_hash: str,
        expires_at: datetime,
    ) -> None:
        now = datetime.now(timezone.utc)
        with self.database.session() as session:
            session.add(
                AuthSession(
                    session_id=session_id,
                    user_id=user_id,
                    token_hash=token_hash,
                    created_at=now,
                    expires_at=expires_at,
                )
            )

    def resolve_session(self, token_hash: str) -> Optional[Dict[str, Any]]:
        now = datetime.now(timezone.utc)
        with self.database.session() as session:
            auth_session = session.scalar(
                select(AuthSession).where(AuthSession.token_hash == token_hash)
            )
            if auth_session is None or auth_session.revoked_at is not None:
                return None
            expires_at = auth_session.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at <= now:
                return None
            user = session.get(User, auth_session.user_id)
            if user is None or not user.is_active:
                return None
            return {
                "session_id": auth_session.session_id,
                "user_id": user.user_id,
                "role": user.role,
                "expires_at": expires_at,
            }

    def revoke_session(self, token_hash: str) -> bool:
        with self.database.session() as session:
            auth_session = session.scalar(
                select(AuthSession).where(AuthSession.token_hash == token_hash)
            )
            if auth_session is None:
                return False
            auth_session.revoked_at = datetime.now(timezone.utc)
        return True


class ProblemRepository:
    def __init__(self, database: Optional[Database] = None):
        self.database = database or get_database()

    def upsert(self, problem: Any, source: str = "generated") -> str:
        data = _plain_dict(problem)
        problem_id = str(data.get("problem_id") or data.get("id") or "").strip()
        if not problem_id:
            raise ValueError("problem_id or id is required")
        validation = data.get("_validation") or data.get("validation_report") or {}
        validation_status = (
            validation.get("status")
            or ("accepted" if validation.get("accepted") is True else "unknown")
        )
        quality = data.get("quality_score")
        if quality is None and isinstance(data.get("evaluation"), dict):
            quality = data["evaluation"].get("score")
        question_type = data.get("question_type") or data.get("type") or ""
        if hasattr(question_type, "value"):
            question_type = question_type.value
        with self.database.session() as session:
            row = session.get(ProblemRecord, problem_id)
            if row is None:
                row = ProblemRecord(problem_id=problem_id, payload_json="{}")
                session.add(row)
            row.topic = str(data.get("topic", "Unknown"))
            row.subtopic = str(data.get("sub_topic") or data.get("subtopic") or "")
            row.question_type = str(question_type)
            row.difficulty = int(data.get("difficulty", 1) or 1)
            row.source = source
            row.validation_status = str(validation_status)
            row.quality_score = float(quality) if quality is not None else None
            row.payload_json = json.dumps(data, ensure_ascii=False, default=str)
        return problem_id

    def upsert_many(self, problems: Iterable[Any], source: str = "generated") -> int:
        count = 0
        for problem in problems:
            self.upsert(problem, source)
            count += 1
        return count

    def get(self, problem_id: str) -> Optional[Dict[str, Any]]:
        with self.database.session() as session:
            row = session.get(ProblemRecord, problem_id)
            return json.loads(row.payload_json) if row else None

    def count(self) -> int:
        with self.database.session() as session:
            return int(session.scalar(select(func.count(ProblemRecord.problem_id))) or 0)


class SubmissionRepository:
    def __init__(self, database: Optional[Database] = None):
        self.database = database or get_database()

    def create(
        self,
        *,
        problem_id: str,
        topic: str,
        score: float,
        is_correct: bool,
        user_id: Optional[str] = None,
        input_type: str = "text",
        ocr_text: Optional[str] = None,
        error_type: Optional[str] = None,
        tutor_feedback: Optional[str] = None,
        next_step: Optional[str] = None,
        submission_id: Optional[str] = None,
    ) -> str:
        identifier = submission_id or f"sub_{uuid4().hex}"
        with self.database.session() as session:
            session.add(
                Submission(
                    submission_id=identifier,
                    user_id=user_id,
                    problem_id=problem_id,
                    topic=topic,
                    input_type=input_type,
                    score=score,
                    is_correct=is_correct,
                    ocr_text=ocr_text,
                    error_type=error_type,
                    tutor_feedback=tutor_feedback,
                    next_step=next_step,
                )
            )
        return identifier

    def count(self) -> int:
        with self.database.session() as session:
            return int(session.scalar(select(func.count(Submission.submission_id))) or 0)


class GenerationRunRepository:
    def __init__(self, database: Optional[Database] = None):
        self.database = database or get_database()

    def create(
        self,
        *,
        pipeline: str,
        topics: Iterable[str],
        target_count: int,
        generated_count: int,
        status: str,
        mode: str = "runtime",
        question_type: str = "mixed",
        difficulty: int = 1,
        user_id: Optional[str] = None,
        duration_ms: Optional[int] = None,
        model: Optional[str] = None,
        error_code: Optional[str] = None,
        run_id: Optional[str] = None,
        created_at: Optional[datetime] = None,
    ) -> str:
        identifier = run_id or f"run_{uuid4().hex}"
        with self.database.session() as session:
            row = session.get(GenerationRun, identifier)
            if row is None:
                row = GenerationRun(run_id=identifier)
                session.add(row)
            row.user_id = user_id
            row.pipeline = pipeline
            row.mode = mode
            row.topics_json = json.dumps(list(topics), ensure_ascii=False)
            row.question_type = (
                question_type.value if hasattr(question_type, "value") else str(question_type)
            )
            row.difficulty = difficulty
            row.target_count = target_count
            row.generated_count = generated_count
            row.status = status
            row.duration_ms = duration_ms
            row.model = model
            row.error_code = error_code
            if created_at is not None:
                row.created_at = created_at
        return identifier

    def count(self) -> int:
        with self.database.session() as session:
            return int(session.scalar(select(func.count(GenerationRun.run_id))) or 0)
