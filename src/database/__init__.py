"""Public database API."""

from src.database.core import Database, get_database
from src.database.repositories import (
    AuthRepository,
    GenerationRunRepository,
    ProblemRepository,
    SubmissionRepository,
    UserRepository,
)

__all__ = [
    "Database",
    "AuthRepository",
    "get_database",
    "UserRepository",
    "ProblemRepository",
    "SubmissionRepository",
    "GenerationRunRepository",
]
