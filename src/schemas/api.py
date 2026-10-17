"""Validated request contracts for the public API."""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from src.schemas.problem import QuestionType


USER_ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"


class GenerateRequest(BaseModel):
    topics: List[str] = Field(default_factory=list, max_length=10)
    num: int = Field(default=1, ge=1, le=10)
    mode: Literal["drill", "exam"] = "drill"
    difficulty: int = Field(default=3, ge=1, le=5)
    question_type: QuestionType = QuestionType.CALCULATION
    user_id: Optional[str] = Field(default=None, pattern=USER_ID_PATTERN)

    @field_validator("topics")
    @classmethod
    def clean_topics(cls, topics: List[str]) -> List[str]:
        cleaned = [topic.strip() for topic in topics if topic.strip()]
        if any(len(topic) > 200 for topic in cleaned):
            raise ValueError("topic names must not exceed 200 characters")
        return list(dict.fromkeys(cleaned))


class AuditRequest(BaseModel):
    problem_id: str = Field(min_length=1, max_length=100)
    student_work_image: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=8_000_000,
    )
    selected_option: Optional[str] = Field(default=None, min_length=1, max_length=20)
    is_exam_mode: bool = False
    user_id: Optional[str] = Field(default=None, pattern=USER_ID_PATTERN)

    @field_validator("selected_option")
    @classmethod
    def clean_selected_option(cls, value: Optional[str]) -> Optional[str]:
        return value.strip().upper() if value is not None else None

    @model_validator(mode="after")
    def require_submission_content(self) -> "AuditRequest":
        if not self.student_work_image and not self.selected_option:
            raise ValueError("student work or a selected option is required")
        return self


class LoginRequest(BaseModel):
    user_id: str = Field(pattern=USER_ID_PATTERN)


class AuthRequest(BaseModel):
    user_id: str = Field(pattern=USER_ID_PATTERN)
    password: str = Field(min_length=10, max_length=128)


class RecordResultRequest(BaseModel):
    user_id: str = Field(pattern=USER_ID_PATTERN)
    topic: str = Field(min_length=1, max_length=200)
    logic_alignment_score: float = Field(default=0, ge=0, le=100)
    is_correct: bool = False


class SynthesizeRequest(BaseModel):
    topics: List[str] = Field(min_length=1, max_length=10)
    count: int = Field(default=5, ge=1, le=20)
    mode: Literal["drill", "exam"] = "drill"
    difficulty: int = Field(default=3, ge=1, le=5)
    question_type: QuestionType = QuestionType.CALCULATION

    @field_validator("topics")
    @classmethod
    def clean_topics(cls, topics: List[str]) -> List[str]:
        cleaned = [topic.strip() for topic in topics if topic.strip()]
        if not cleaned:
            raise ValueError("at least one topic is required")
        return list(dict.fromkeys(cleaned))
