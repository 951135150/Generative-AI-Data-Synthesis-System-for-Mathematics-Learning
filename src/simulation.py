"""Explicit offline fixtures. They exercise workflows, not autonomous AI quality."""

import json
import re
import uuid

import sympy as sp

from src.validation import MathematicalValidator


SIMULATION_TOPICS = [
    "Limits and Continuity", "Derivatives and Differentiation", "Integration and FTOC",
    "Multivariable Calculus", "Applications of Derivatives", "Indefinite Integrals",
    "Applications of Integration", "Multiple Integrals", "Vector Calculus", "Sequences and Series",
    "Differential Equations", "Techniques of Integration", "Parametric and Polar Curves",
]


class SimulationInputError(ValueError):
    pass


def make_problem(topic, difficulty=3, question_type="mcq", mode="drill", variant=1):
    """Small parameterized examples; not a full syllabus or calibrated difficulty model."""
    from src.rag.service import topic_matches
    x = sp.Symbol("x", real=True)
    a = variant % 5 + 2
    n = min(4, max(2, difficulty))
    if topic_matches(topic, "Derivatives and Differentiation"):
        source, operation, concept = (a * x + 1) ** n, "differentiate", "chain_rule"
        expected = sp.diff(source, x)
        statement = f"Find the derivative of $ f(x)={sp.latex(source)} $."
        explanation = "Apply the outer power rule, then multiply by the derivative of the inner linear function."
    elif topic_matches(topic, "Applications of Derivatives"):
        source, operation, concept = (x - a) ** 2 + n, "differentiate", "marginal_cost"
        expected = sp.diff(source, x)
        statement = f"The cost function is $ C(x)={sp.latex(source)} $. Find its marginal cost $ C'(x) $."
        explanation = "Marginal cost is the derivative of cost with respect to the modeled quantity."
    elif topic_matches(topic, "Techniques of Integration"):
        source, operation, concept = a * (a * x + 1) ** n, "integrate", "substitution"
        expected = sp.integrate(source, x)
        statement = f"Find one antiderivative of $ {sp.latex(source)} $. An additive constant may be omitted."
        explanation = "Substitute u=ax+1, so du=a dx. Integrate the power in u, then substitute back."
    elif topic_matches(topic, "Limits and Continuity"):
        source, operation, concept = (x ** 2 - a ** 2) / (x - a), "limit", "limits"
        expected = sp.Integer(2 * a)
        statement = f"Evaluate $ \\lim_{{x\\to {a}}} {sp.latex(source)} $."
        explanation = "Factor the numerator, cancel for x different from the limiting point, and evaluate the resulting expression."
    elif topic_matches(topic, "Integration and FTOC"):
        source, operation, concept = a * x ** n, "integrate", "fundamental_theorem"
        expected = sp.integrate(source, x)
        statement = f"For $ G(x)=\\int_0^x {a}t^{n}\\,dt $, find $ G(x) $."
        explanation = "Evaluate the antiderivative at the variable upper endpoint and subtract its value at zero."
    elif topic_matches(topic, "Indefinite Integrals"):
        source, operation, concept = a * x ** n, "integrate", "antiderivative"
        expected = sp.integrate(source, x)
        statement = f"Find one antiderivative of $ {sp.latex(source)} $. An additive constant may be omitted."
        explanation = "Use the power integration rule and differentiate the proposed result to check it."
    elif topic_matches(topic, "Applications of Integration"):
        source, operation, concept = a * x ** n, "integrate", "signed_accumulation"
        expected = sp.integrate(source, x)
        statement = f"A tank starts empty with inflow $ r(t)={a}t^{n} $ for $ t\\geq0 $. Find the accumulated volume $ V(x) $ at $ x\\geq0 $."
        explanation = "Integrate the inflow rate from zero to x and use the zero initial volume."
    elif topic_matches(topic, "Multivariable Calculus"):
        source, operation, concept = 2 * a * x ** n, "differentiate", "partial_derivative"
        expected = sp.diff(source, x)
        statement = f"For $ f(x,y)={a}x^{n}y $, find $ f_x(x,2) $."
        explanation = "Hold y fixed during differentiation, then substitute y=2."
    elif topic_matches(topic, "Multiple Integrals"):
        source, operation, concept = a * x ** n, "integrate", "iterated_integral"
        expected = sp.integrate(source, x)
        statement = f"Evaluate $ I(x)=\\int_0^x\\int_0^1 {a}t^{n}\\,dy\\,dt $ for $ x\\geq0 $."
        explanation = "The inner integration contributes the interval length one; integrate the remaining power from zero to x."
    elif topic_matches(topic, "Vector Calculus"):
        source, operation, concept = a * x ** n, "integrate", "conservative_field"
        expected = sp.integrate(source, x)
        statement = f"For $ \\mathbf{{F}}(u,v)=({a}u^{n},0) $, find the line integral along the x-axis from $ (0,0) $ to $ (x,0) $."
        explanation = "Parameterize the straight path by (t,0); the dot product reduces to the scalar power integral."
    elif topic_matches(topic, "Sequences and Series"):
        source, operation, concept = sum(x ** k for k in range(n + 1)), "simplify", "finite_geometric_sum"
        expected = (1 - x ** (n + 1)) / (1 - x)
        statement = f"For $ x\\ne1 $, express $ S(x)=\\sum_{{k=0}}^{n} x^k $ as one rational expression."
        explanation = "Multiply the finite sum by (1-x); all intermediate powers cancel. Divide by (1-x), which is nonzero."
    elif topic_matches(topic, "Differential Equations"):
        source, operation, concept = a * x ** n, "integrate", "initial_condition"
        expected = sp.integrate(source, x)
        statement = f"Solve $ y'={a}x^{n} $ with $ y(0)=0 $. Give $ y(x) $."
        explanation = "Integrate the right-hand side, then apply the initial condition to set the integration constant to zero."
    elif topic_matches(topic, "Parametric and Polar Curves"):
        source, operation, concept = a * x ** n, "differentiate", "parametric_derivative"
        expected = sp.diff(source, x)
        statement = f"A curve has $ x(t)=t $ and $ y(t)={a}t^{n} $. Find $ dy/dx $ expressed in x."
        explanation = "Divide dy/dt by dx/dt=1, then substitute t=x."
    else:
        raise ValueError("This topic has no offline fixture. External calls are disabled.")
    expression = str(sp.simplify(expected))
    identifier = f"sim_{uuid.uuid4().hex[:12]}"
    problem = {
        "id": identifier, "problem_id": identifier, "topic": topic,
        "difficulty": difficulty, "question_type": question_type, "mode": mode,
        "problem_statement": statement, "solution": f"{explanation} The result is $ {sp.latex(expected)} $.",
        "scaffolding": [{"step": 1, "hint": "Identify the operation and the inner expression first."},
                        {"step": 2, "hint": explanation}],
        "integration_analysis": "Single-concept offline fixture; cross-topic fusion is not evaluated.",
        "concept_ids": [concept], "expected_expression": expression,
        "allow_additive_constant": operation == "integrate" and "one antiderivative" in statement,
        "ai_mode": "simulation", "review_kind": "deterministic_fixture_check",
        "symbolic_validation": {"operation": operation, "source_expression": str(source),
                                "claimed_result": expression, "variable": "x"},
    }
    if operation == "limit":
        problem["symbolic_validation"]["point"] = str(a)
    if question_type == "mcq":
        change = x if problem["allow_additive_constant"] else sp.Integer(1)
        choices = [expected, expected + change, expected - change, -expected]
        choices = [MathematicalValidator()._parse_expression(str(value), x) for value in choices]
        # Nonzero positive limits and nonconstant pilot expressions give distinct distractors.
        offset = variant % 4
        choices = choices[offset:] + choices[:offset]
        problem["options"] = {key: f"$ {sp.latex(MathematicalValidator()._parse_expression(str(value), x, evaluate=False))} $" for key, value in zip("ABCD", choices)}
        problem["answer"] = "ABCD"[(-offset) % 4]
        problem["option_expressions"] = {key: str(value) for key, value in zip("ABCD", choices)}
        problem["answer_equivalence"] = "antiderivative" if problem["allow_additive_constant"] else "exact"
        problem["excluded_points"] = ["1"] if operation == "simplify" else []
        problem["semantic_validation_required"] = True
        problem["fixture_correct_option"] = problem["options"][problem["answer"]]
    elif question_type == "fill_in":
        problem["problem_statement"] += " Answer: [BLANK_1]."
        problem["correct_values"] = [expression]
    return problem


def fixture_review(problem):
    report = MathematicalValidator().validate(problem)
    verified = report.symbolic_status == "passed" and report.passed
    if problem.get("question_type") == "mcq":
        # Check the actual option mapping, in addition to the separate symbolic claim.
        expected = problem.get("expected_expression")
        expression = MathematicalValidator()._parse_expression(expected or "0", sp.Symbol("x", real=True))
        verified = verified and problem.get("options", {}).get(problem.get("answer")) == f"$ {sp.latex(expression)} $"
        # Equivalent forms in generated LaTeX can differ; generator stores an explicit expected option below.
        if problem.get("fixture_correct_option"):
            verified = report.passed and report.symbolic_status == "passed" and problem.get("options", {}).get(problem.get("answer")) == problem["fixture_correct_option"]
    return {"math_logic_score": 100 if verified else 0, "pedagogical_score": 80,
            "integration_score": 0, "is_mathematically_correct": verified,
            "mcq_answer_consistent": verified, "logical_gap_detected": not verified,
            "critical_flaw": "Offline fixture check only; no expert semantic review was performed.",
            "improvement_suggestion": "Use a human or live model to assess pedagogical and cross-topic quality.",
            "review_kind": "deterministic_fixture_check"}


class SimulationProvider:
    model_name = "offline-fixtures-v1"

    def generate(self, prompt, **kwargs):
        if kwargs.get("image_bytes"):
            raise ValueError("Offline simulation does not perform image recognition.")
        if "[PROBLEM DATA]" in prompt and "[AUDIT RUBRIC]" in prompt:
            data = prompt.split("[PROBLEM DATA]", 1)[1].split("[AUDIT RUBRIC]", 1)[0]
            return json.dumps(fixture_review(json.loads(data)))
        marker = "[SIMULATION TASK]"
        if marker not in prompt:
            raise ValueError("No offline fixture exists for this model request. External calls are disabled.")
        payload = json.loads(prompt.split(marker, 1)[1].splitlines()[0])
        problem = make_problem(**payload, variant=uuid.uuid4().int % 10000)
        if problem.get("options"):
            problem["fixture_correct_option"] = problem["options"][problem["answer"]]
        return json.dumps(problem, ensure_ascii=False)

    def mentor_review(self, *, problem_data, student_text_answer=None, mcq_assessment=None,
                      evidence_bundle=None, is_exam_mode=False, **kwargs):
        if mcq_assessment:
            correct = mcq_assessment["is_correct"]
        elif problem_data.get("expected_expression"):
            validator = MathematicalValidator()
            x = sp.Symbol("x", real=True)
            try:
                actual = validator._parse_expression((student_text_answer or "").strip(), x)
                expected = validator._parse_expression(problem_data["expected_expression"], x)
                difference = sp.simplify(actual - expected)
                correct = difference == 0 or (
                    problem_data.get("allow_additive_constant") is True
                    and not difference.has(x)
                )
            except Exception as error:
                raise SimulationInputError("In simulation, enter a final expression in SymPy notation, e.g. 6*x+2.") from error
        else:
            raise SimulationInputError("This problem has no offline scoring fixture. A manual review is required.")
        evidence = (evidence_bundle or {}).get("evidence", [])
        references = evidence[:1]
        feedback = "Your answer agrees with the stored reference." if correct else "Your answer does not agree with the stored reference."
        if references:
            feedback += f" Review [{references[0]['citation_id']}] for the relevant course rule."
        hint = "Identify the applicable rule and verify the conditions before calculating."
        if correct:
            hint = "Try another example without consulting the hints."
        return json.dumps({"is_correct": bool(correct), "logic_alignment_score": 100 if correct else 0,
                           "error_analysis": ("Option correct." if mcq_assessment else "Final expression correct.") if correct else "Reference mismatch; the specific misconception is not established.",
                           "tutor_feedback": feedback, "next_hint": hint,
                           "citation_ids": [c["citation_id"] for c in references],
                           "ai_mode": "simulation", "diagnostic_tags": [],
                           "grading_scope": "final_expression_only" if not mcq_assessment else "option_key"})
