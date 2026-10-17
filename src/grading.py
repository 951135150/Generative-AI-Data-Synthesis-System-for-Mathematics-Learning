"""Deterministic grading helpers for objective question types.

The LLM remains useful for pedagogical feedback, but it must not be the
authority for an MCQ result that can be checked exactly.
"""

from dataclasses import asdict, dataclass
import re
from typing import Any, Dict, Mapping, Optional


class MCQReferenceError(ValueError):
    """Raised when a stored MCQ does not contain a usable answer key."""


class MCQSelectionError(ValueError):
    """Raised when the learner selection is not one of the stored options."""


@dataclass(frozen=True)
class MCQAssessment:
    selected_key: str
    selected_content: str
    answer_key: str
    answer_content: str
    is_correct: bool

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


_LEGACY_SELECTION = re.compile(
    r"^\s*(?:the\s+option\s+i\s+have\s+chosen\s+is\s*:\s*)?([A-Za-z0-9_-]+)\s*$",
    re.IGNORECASE,
)


def is_mcq_problem(problem: Mapping[str, Any]) -> bool:
    question_type = str(problem.get("question_type") or problem.get("type") or "").lower()
    return question_type == "mcq" or (
        isinstance(problem.get("options"), Mapping) and bool(problem.get("answer"))
    )


def _canonical_option_key(value: str, options: Mapping[str, Any]) -> Optional[str]:
    normalized = value.strip().upper()
    for key in options:
        if str(key).strip().upper() == normalized:
            return str(key)
    return None


def extract_selected_option(
    explicit_selection: Optional[str],
    legacy_text: Optional[str],
) -> Optional[str]:
    """Return an option token from the new field or the legacy text payload."""

    if explicit_selection:
        return explicit_selection.strip()
    if not legacy_text:
        return None
    match = _LEGACY_SELECTION.fullmatch(legacy_text)
    return match.group(1) if match else None


def assess_mcq(problem: Mapping[str, Any], selected_option: str) -> MCQAssessment:
    options = problem.get("options")
    if not isinstance(options, Mapping) or len(options) < 2:
        raise MCQReferenceError("The stored question has no usable option set.")

    answer = problem.get("answer")
    if answer is None:
        raise MCQReferenceError("The stored question has no reference answer.")

    answer_key = _canonical_option_key(str(answer), options)
    if answer_key is None:
        raise MCQReferenceError(
            "The stored reference answer does not match any available option."
        )

    selected_key = _canonical_option_key(selected_option, options)
    if selected_key is None:
        allowed = ", ".join(str(key) for key in options)
        raise MCQSelectionError(f"Select one of the available options: {allowed}.")

    return MCQAssessment(
        selected_key=selected_key,
        selected_content=str(options[selected_key]),
        answer_key=answer_key,
        answer_content=str(options[answer_key]),
        is_correct=selected_key == answer_key,
    )
