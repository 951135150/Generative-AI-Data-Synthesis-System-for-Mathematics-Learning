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
        elif symbolic_status == "not_provided" or (problem.question_type == QuestionType.MCQ and not problem.option_expressions):
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
            if problem.option_expressions:
                self._check_mcq_semantics(problem, checks, issues)
            elif problem.semantic_validation_required:
                checks["mcq_semantics_present"] = False
                issues.append("New MCQs require option_expressions for mathematical uniqueness checks.")
            else:
                issues.append("Legacy MCQ semantic uniqueness was not checked.")

        if problem.question_type == QuestionType.FILL_IN:
            blank_count = problem.problem_statement.count("[BLANK_")
            checks["fill_in_values_match"] = bool(problem.correct_values) and (
                blank_count == 0 or len(problem.correct_values or []) >= blank_count
            )
            if not checks["fill_in_values_match"]:
                issues.append("Fill-in answers do not cover all blanks.")

    def _check_mcq_semantics(self, problem, checks, issues):
        """Bind symbolic options to display and check equivalence on real domains.

        This checks declared expressions/conditions, not arbitrary natural-language
        questions. Unsupported domains fail closed instead of certifying a guess.
        """
        from sympy.calculus.util import continuous_domain
        try:
            if not problem.symbolic_validation or set(problem.option_expressions) != set(problem.options):
                raise ValueError("A claim and matching symbolic/display option keys are required.")
            x = sp.Symbol(problem.symbolic_validation.variable, real=True)
            parse = lambda value: self._parse_expression(value, x, evaluate=False)
            exclusions = [parse(value) for value in problem.excluded_points]
            if any(value.free_symbols or value.is_real is not True or value.is_finite is not True for value in exclusions):
                raise ValueError("Domain exclusions must be finite real constants.")
            domain = sp.S.Reals - sp.FiniteSet(*exclusions)
            reference = parse(problem.symbolic_validation.claimed_result)
            expressions = {key: parse(value) for key, value in problem.option_expressions.items()}
            # Rendering a parsed expression binds the checked mathematics to the
            # actual displayed option. No separate unverified symbolic answer map.
            display_ok = all(re.sub(r"\s+", "", problem.options[key]) == re.sub(
                r"\s+", "", f"$ {sp.latex(expressions[key])} $")
                for key in expressions)
            checks["mcq_expression_display_match"] = display_ok
            if not display_ok:
                raise ValueError("Symbolic options must match their canonical LaTeX display.")
            primitive = problem.answer_equivalence == "antiderivative"
            if primitive and (not problem.allow_additive_constant or problem.symbolic_validation.operation != "integrate"):
                raise ValueError("Antiderivative equivalence requires an indefinite integral without a fixed constant.")
            def same(left, right, *, cover_domain=True):
                if left.free_symbols - {x} or right.free_symbols - {x}:
                    raise ValueError("Only the declared variable is supported in symbolic MCQ options.")
                left_domain = continuous_domain(left, x, sp.S.Reals).intersect(domain)
                right_domain = continuous_domain(right, x, sp.S.Reals).intersect(domain)
                # Every candidate must be defined throughout the stated domain;
                # cancelling an extra hole must not silently make it equivalent.
                if left_domain != right_domain or (cover_domain and left_domain != domain):
                    return False
                delta = sp.simplify(left - right)
                return delta == 0 or (primitive and sp.simplify(sp.diff(delta, x)) == 0)
            checks["mcq_reference_domain_valid"] = continuous_domain(reference, x, sp.S.Reals).intersect(domain) == domain
            valid_keys = [key for key, value in expressions.items() if same(value, reference)]
            checks["mcq_single_correct_option"] = valid_keys == [problem.answer]
            pairs = list(expressions.values())
            checks["mcq_semantic_options_unique"] = all(not same(left, right, cover_domain=False)
                for index, left in enumerate(pairs) for right in pairs[index + 1:])
            checks["mcq_semantics_checked"] = all(checks[k] for k in (
                "mcq_reference_domain_valid", "mcq_single_correct_option", "mcq_semantic_options_unique"))
            if not checks["mcq_semantics_checked"]:
                issues.append(f"MCQ semantic validation failed; valid option keys: {valid_keys}.")
        except Exception as error:
            checks["mcq_semantics_checked"] = False
            issues.append(f"MCQ semantic check could not certify uniqueness: {error}")

    def _parse_expression(self, expression: str, variable: sp.Symbol, *, evaluate=True) -> sp.Expr:
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
            "Add": sp.Add,
            "Mul": sp.Mul,
            "Pow": sp.Pow,
        }
        return parse_expr(
            expression.replace("^", "**"),
            local_dict=local_dict,
            global_dict=global_dict,
            evaluate=evaluate,
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
