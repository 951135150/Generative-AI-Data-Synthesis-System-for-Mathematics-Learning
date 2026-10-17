"""Deterministic validation for generated calculus problems.

The validator deliberately separates machine-checkable mathematical claims
from open-ended pedagogical review. It never marks a failed symbolic check as
approved merely because an LLM considers the prose convincing.
"""

import re
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

import sympy as sp
from pydantic import ValidationError
from sympy.parsing.sympy_parser import parse_expr

from src.schemas.problem import Problem, QuestionType, SymbolicValidation


class ValidationStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    PARTIAL = "partial"


@dataclass
class ValidationReport:
    status: ValidationStatus
    schema_valid: bool
    symbolic_status: str
    checks: Dict[str, bool] = field(default_factory=dict)
    issues: List[str] = field(default_factory=list)
    normalized_problem: Optional[Dict[str, Any]] = None

    @property
    def passed(self) -> bool:
        return self.status != ValidationStatus.FAILED

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        data["passed"] = self.passed
        return data


class MathematicalValidator:
    """Validate structure, type-specific invariants, and symbolic claims."""

    _SAFE_EXPRESSION = re.compile(r"^[A-Za-z0-9+\-*/^()., \t]+$")
    _ALLOWED_FUNCTIONS = {
        "sin": sp.sin,
        "cos": sp.cos,
        "tan": sp.tan,
        "exp": sp.exp,
        "log": sp.log,
        "sqrt": sp.sqrt,
        "Abs": sp.Abs,
        "pi": sp.pi,
        "E": sp.E,
        "oo": sp.oo,
    }

    def validate(self, problem_data: Dict[str, Any]) -> ValidationReport:
        checks: Dict[str, bool] = {}
        issues: List[str] = []

        try:
            problem = Problem.model_validate(problem_data)
        except ValidationError as exc:
            issues.extend(
                f"{'.'.join(map(str, error['loc']))}: {error['msg']}"
                for error in exc.errors()
            )
            return ValidationReport(
                status=ValidationStatus.FAILED,
                schema_valid=False,
                symbolic_status="not_run",
                checks={"schema": False},
                issues=issues,
            )

        checks["schema"] = True
        self._run_type_checks(problem, checks, issues)

        symbolic_status = "not_provided"
        if problem.symbolic_validation:
            symbolic_ok, symbolic_issue = self._validate_symbolic_claim(
                problem.symbolic_validation
            )
            checks["symbolic_claim"] = symbolic_ok
            symbolic_status = "passed" if symbolic_ok else "failed"
            if symbolic_issue:
                issues.append(symbolic_issue)

        hard_failure = any(value is False for value in checks.values())
        if hard_failure:
            status = ValidationStatus.FAILED
        elif symbolic_status == "not_provided":
            status = ValidationStatus.PARTIAL
        else:
            status = ValidationStatus.PASSED

        normalized = problem.to_compatible_dict()
        return ValidationReport(
            status=status,
            schema_valid=True,
            symbolic_status=symbolic_status,
            checks=checks,
            issues=issues,
            normalized_problem=normalized,
        )

    def _run_type_checks(
        self, problem: Problem, checks: Dict[str, bool], issues: List[str]
    ) -> None:
        checks["nonempty_scaffolding"] = bool(problem.scaffolding)
        if not problem.scaffolding:
            issues.append("At least one progressive hint is required.")

        if problem.question_type == QuestionType.MCQ and problem.options:
            normalized_options = [str(value).strip() for value in problem.options.values()]
            checks["mcq_options_unique"] = len(normalized_options) == len(
                set(normalized_options)
            )
            if not checks["mcq_options_unique"]:
                issues.append("MCQ options must be unique.")
            checks["mcq_answer_exists"] = problem.answer in problem.options

        if problem.question_type == QuestionType.FILL_IN:
            blank_count = problem.problem_statement.count("[BLANK_")
            checks["fill_in_values_match"] = bool(problem.correct_values) and (
                blank_count == 0 or len(problem.correct_values or []) >= blank_count
            )
            if not checks["fill_in_values_match"]:
                issues.append("Fill-in answers do not cover all blanks.")

    def _parse_expression(self, expression: str, variable: sp.Symbol) -> sp.Expr:
        if (
            len(expression) > 500
            or "__" in expression
            or not self._SAFE_EXPRESSION.fullmatch(expression)
        ):
            raise ValueError("expression contains unsupported characters")

        local_dict = dict(self._ALLOWED_FUNCTIONS)
        local_dict[variable.name] = variable
        local_dict["e"] = sp.E
        global_dict = {
            "__builtins__": {},
            "Symbol": sp.Symbol,
            "Integer": sp.Integer,
            "Float": sp.Float,
            "Rational": sp.Rational,
        }
        return parse_expr(
            expression.replace("^", "**"),
            local_dict=local_dict,
            global_dict=global_dict,
            evaluate=True,
        )

    def _validate_symbolic_claim(
        self, claim: SymbolicValidation
    ) -> tuple[bool, Optional[str]]:
        try:
            variable = sp.Symbol(claim.variable, real=True)
            source = self._parse_expression(claim.source_expression, variable)
            result = self._parse_expression(claim.claimed_result, variable)

            if claim.operation == "differentiate":
                difference = sp.simplify(sp.diff(source, variable) - result)
            elif claim.operation == "integrate":
                # Indefinite integrals are equivalent up to an additive constant,
                # so differentiating the claimed antiderivative is the robust check.
                difference = sp.simplify(sp.diff(result, variable) - source)
            elif claim.operation == "simplify":
                difference = sp.simplify(source - result)
            elif claim.operation == "limit":
                if claim.point is None:
                    return False, "A limit claim requires a point."
                point = self._parse_expression(claim.point, variable)
                difference = sp.simplify(sp.limit(source, variable, point) - result)
            else:
                return False, f"Unsupported operation: {claim.operation}"

            if difference == 0:
                return True, None
            return (
                False,
                "Symbolic verification failed: the claimed result is not "
                "mathematically equivalent to the source expression.",
            )
        except Exception as exc:
            return False, f"Symbolic verification could not be completed: {exc}"
