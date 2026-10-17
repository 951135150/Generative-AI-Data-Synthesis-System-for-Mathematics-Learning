"""SQLAlchemy models for durable runtime data."""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    total_minutes: Mapped[float] = mapped_column(Float, default=0.0)
    dataset_version: Mapped[str] = mapped_column(String(40), default="v3")
    password_hash: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    password_salt: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    password_iterations: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    role: Mapped[str] = mapped_column(String(40), default="student")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    masteries: Mapped[list["TopicMastery"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    learning_events: Mapped[list["LearningEvent"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    auth_sessions: Mapped[list["AuthSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    __table_args__ = (
        Index("ix_auth_session_user_expires", "user_id", "expires_at"),
        UniqueConstraint("token_hash", name="uq_auth_session_token_hash"),
    )

    session_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped["User"] = relationship(back_populates="auth_sessions")


class TopicMastery(Base):
    __tablename__ = "topic_masteries"
    __table_args__ = (
        UniqueConstraint("user_id", "topic", name="uq_topic_mastery_user_topic"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), index=True
    )
    topic: Mapped[str] = mapped_column(String(160))
    mastery_score: Mapped[float] = mapped_column(Float, default=0.0)
    current_level: Mapped[int] = mapped_column(Integer, default=1)
    completed_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    user: Mapped["User"] = relationship(back_populates="masteries")


class LearningEvent(Base):
    __tablename__ = "learning_events"
    __table_args__ = (Index("ix_learning_event_user_created", "user_id", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), index=True
    )
    topic: Mapped[str] = mapped_column(String(160))
    score: Mapped[float] = mapped_column(Float)
    is_correct: Mapped[bool] = mapped_column(Boolean, default=False)
    level_at_time: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    user: Mapped["User"] = relationship(back_populates="learning_events")


class ProblemRecord(Base):
    __tablename__ = "problems"
    __table_args__ = (
        Index("ix_problem_topic_difficulty", "topic", "difficulty"),
        Index("ix_problem_created", "created_at"),
    )

    problem_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    topic: Mapped[str] = mapped_column(String(160), default="Unknown")
    subtopic: Mapped[str] = mapped_column(String(160), default="")
    question_type: Mapped[str] = mapped_column(String(80), default="")
    difficulty: Mapped[int] = mapped_column(Integer, default=1)
    source: Mapped[str] = mapped_column(String(40), default="generated")
    validation_status: Mapped[str] = mapped_column(String(40), default="unknown")
    quality_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    payload_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class Submission(Base):
    __tablename__ = "submissions"
    __table_args__ = (
        Index("ix_submission_user_created", "user_id", "created_at"),
        Index("ix_submission_problem", "problem_id"),
    )

    submission_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    user_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True
    )
    problem_id: Mapped[str] = mapped_column(String(160))
    topic: Mapped[str] = mapped_column(String(160), default="Unknown")
    input_type: Mapped[str] = mapped_column(String(40), default="text")
    score: Mapped[float] = mapped_column(Float, default=0.0)
    is_correct: Mapped[bool] = mapped_column(Boolean, default=False)
    ocr_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_type: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    tutor_feedback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    next_step: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class GenerationRun(Base):
    __tablename__ = "generation_runs"
    __table_args__ = (Index("ix_generation_run_created", "created_at"),)

    run_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    pipeline: Mapped[str] = mapped_column(String(40), default="single_agent")
    mode: Mapped[str] = mapped_column(String(40), default="runtime")
    topics_json: Mapped[str] = mapped_column(Text, default="[]")
    question_type: Mapped[str] = mapped_column(String(80), default="mixed")
    difficulty: Mapped[int] = mapped_column(Integer, default=1)
    target_count: Mapped[int] = mapped_column(Integer, default=0)
    generated_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(40), default="completed")
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    error_code: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
