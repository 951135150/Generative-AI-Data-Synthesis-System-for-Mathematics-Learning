"""Canonical problem schema for generated and curated calculus content."""

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class QuestionType(str, Enum):
    CALCULATION = "calculation"
    MCQ = "mcq"
    FILL_IN = "fill_in"


class Hint(BaseModel):
    model_config = ConfigDict(extra="ignore")

    step: int = Field(ge=1, le=10)
    hint: str = Field(min_length=3, max_length=4000)


class SymbolicValidation(BaseModel):
    """Optional machine-checkable claim emitted by the generator.

    Expressions use SymPy syntax rather than LaTeX so that validation does not
    depend on a lossy LaTeX parser.
    """

    model_config = ConfigDict(extra="ignore")

    operation: str = Field(
        description="differentiate, integrate, simplify, or limit"
    )
    source_expression: str = Field(min_length=1, max_length=500)
    claimed_result: str = Field(min_length=1, max_length=500)
    variable: str = Field(default="x", pattern=r"^[A-Za-z]$")
    point: Optional[str] = Field(default=None, max_length=100)

    @field_validator("operation")
    @classmethod
    def validate_operation(cls, value: str) -> str:
        normalized = value.strip().lower()
        allowed = {"differentiate", "integrate", "simplify", "limit"}
        if normalized not in allowed:
            raise ValueError(f"operation must be one of {sorted(allowed)}")
        return normalized


class Problem(BaseModel):
    """Single canonical representation used across the application."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    problem_id: str = Field(min_length=1, max_length=100)
    topic: str = Field(min_length=1, max_length=200)
    sub_topic: Optional[str] = Field(default=None, max_length=200)
    problem_statement: str = Field(min_length=10, max_length=20000)
    question_type: QuestionType = QuestionType.CALCULATION
    difficulty: int = Field(default=3, ge=1, le=5)
    solution: str = Field(min_length=1, max_length=30000)
    scaffolding: List[Hint] = Field(default_factory=list, max_length=10)
    integration_analysis: Optional[str] = Field(default=None, max_length=8000)
    options: Optional[Dict[str, str]] = None
    answer: Optional[str] = None
    correct_values: Optional[List[str]] = None
    symbolic_validation: Optional[SymbolicValidation] = None

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        normalized = dict(data)
        canonical_id = normalized.get("problem_id") or normalized.get("id")
        if canonical_id:
            normalized["problem_id"] = str(canonical_id)
            # Keep the legacy key during migration because the current frontend
            # and stored datasets still use it.
            normalized.setdefault("id", str(canonical_id))
        if "question_type" not in normalized and "type" in normalized:
            normalized["question_type"] = normalized["type"]
        if "sub_topic" not in normalized and "subtopic" in normalized:
            normalized["sub_topic"] = normalized["subtopic"]
        return normalized

    @model_validator(mode="after")
    def validate_type_specific_fields(self) -> "Problem":
        if self.question_type == QuestionType.MCQ:
            if not self.options or len(self.options) < 2:
                raise ValueError("MCQ problems require at least two options")
            if not self.answer or self.answer not in self.options:
                raise ValueError("MCQ answer must reference an existing option")
        elif self.question_type == QuestionType.FILL_IN:
            blank_count = self.problem_statement.count("[BLANK_")
            if not self.correct_values:
                raise ValueError("fill-in problems require correct_values")
            if blank_count and len(self.correct_values) < blank_count:
                raise ValueError("each fill-in blank requires a correct value")
        return self

    def to_compatible_dict(self) -> Dict[str, Any]:
        """Return canonical data while retaining `id` for existing clients."""
        data = self.model_dump(mode="json", exclude_none=True)
        data["id"] = self.problem_id
        data["problem_id"] = self.problem_id
        return data
