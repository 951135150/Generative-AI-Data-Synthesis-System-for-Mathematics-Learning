"""QualityReviewer — evaluates problem quality with veto power.

Receives problems from the Synthesizer, evaluates them directly via LLM,
and issues APPROVE or REJECT verdicts with detailed feedback.
"""

import logging
from typing import List

from src.multi_agent.autonomous_agent import AutonomousAgent, Action, ActionType
from src.multi_agent.messages import Message, MessageType
from src.multi_agent.tools import get_tools_for_agent
from src.validation import MathematicalValidator

logger = logging.getLogger(__name__)


class QualityReviewer(AutonomousAgent):
    """Rigorous auditor that enforces mathematical and pedagogical standards.

    Evaluates problems across multiple dimensions (math correctness, logical
    coherence, pedagogical value, difficulty calibration) and either approves
    or rejects with specific, actionable feedback.
    """

    def __init__(self, message_bus, model=None):
        tools = get_tools_for_agent("reviewer")
        self.mathematical_validator = MathematicalValidator()
        super().__init__(
            agent_id="reviewer",
            role="Rigorous Auditor",
            personality=(
                "You are a rigorous quality auditor for mathematical problems. "
                "You enforce high standards for mathematical correctness, pedagogical "
                "value, and logical coherence.\n\n"
                "When reviewing a problem, evaluate:\n"
                "1. Mathematical correctness (is the solution right? any errors?)\n"
                "2. Logical coherence (does the reasoning flow? any gaps?)\n"
                "3. Pedagogical value (is it instructive? appropriate difficulty?)\n"
                "4. Difficulty calibration (does it match the target difficulty?)\n"
                "5. Scaffolding quality (are hints progressive and helpful?)\n"
                "6. LaTeX correctness (proper formatting? no rendering issues?)\n\n"
                "Scoring: 0-100 overall. Pass threshold: 60.\n\n"
                "Your evaluation content must include:\n"
                "- score: overall score (0-100)\n"
                "- passed: true/false\n"
                "- dimensions: {{math_logic, pedagogy, scaffolding, difficulty_match}} each 0-100\n"
                "- issues: list of specific problems found (empty if none)\n"
                "- feedback: actionable improvement suggestions (or commendation if good)\n\n"
                "Workflow:\n"
                "1. When you receive a 'review_problem' REQUEST, evaluate the problem "
                "IMMEDIATELY in your LLM response. You MUST either approve or reject — "
                "never ask for resend or clarification.\n"
                "2. CRITICAL: In your approve/reject message content, ALWAYS include the "
                "FULL problem JSON under the key 'problem'. The Synthesizer needs this "
                "to save the problem — it may not have the full data in its own memory.\n"
                "3. If the problem passes (score >= 60): send ONE 'approve' message to "
                "the 'synthesizer' with content={problem_id:..., evaluation:{...}, problem:{...FULL problem JSON...}}.\n"
                "4. If the problem fails (score < 60): send ONE 'reject' message to "
                "the 'synthesizer' with content={problem_id:..., evaluation:{...}, problem:{...FULL problem JSON...}, feedback:...}.\n"
                "5. After sending approve or reject, call agent_wait to let other agents work.\n"
                "6. You may use check_coverage to see dataset context, but only for reference."
            ),
            message_bus=message_bus,
            tools=tools,
            model=model,
            temperature=0.2,
            max_idle_seconds=600.0,
        )

    async def _reason(self, new_messages: List[Message]) -> Action:
        """Override to guard against rogue LLM behavior (send to None, empty content).

        When the reviewer receives a review_problem request, we validate the LLM
        output. If the LLM produces a message to None or with empty content,
        we retry with a stronger prompt.
        """
        # Detect review_problem request and extract expected problem_id
        expected_problem_id = None
        problem_under_review = None
        if new_messages:
            for msg in new_messages:
                if (msg.type == MessageType.REQUEST
                        and msg.content.get("action") == "review_problem"):
                    problem_data = msg.content.get("problem", {})
                    expected_problem_id = problem_data.get("id")
                    problem_under_review = problem_data
                    break

        if expected_problem_id:
            self.memory.internal_state["_reviewing_problem_id"] = expected_problem_id

            # A deterministic failure is a hard rejection. The LLM reviewer is
            # not allowed to overrule an invalid schema or symbolic mismatch.
            deterministic = self.mathematical_validator.validate(
                problem_under_review or {}
            )
            if not deterministic.passed:
                return Action(
                    action_type=ActionType.SEND_MESSAGE,
                    thought=(
                        f"Rejecting {expected_problem_id}: deterministic "
                        "validation failed"
                    ),
                    message=Message(
                        type=MessageType.REJECT,
                        sender=self.agent_id,
                        recipient="synthesizer",
                        content={
                            "problem_id": expected_problem_id,
                            "evaluation": {
                                "score": 0,
                                "passed": False,
                                "status": "validation_failed",
                                "dimensions": {
                                    "math_logic": 0,
                                    "pedagogy": 0,
                                    "scaffolding": 0,
                                    "difficulty_match": 0,
                                },
                                "issues": deterministic.issues,
                                "deterministic_validation": deterministic.to_dict(),
                                "feedback": (
                                    "Fix every deterministic validation issue "
                                    "before resubmitting."
                                ),
                            },
                            "problem": problem_under_review or {},
                            "feedback": "; ".join(deterministic.issues),
                        },
                    ),
                )

            # Retry loop: keep trying until we get a valid approve/reject
            for attempt in range(3):
                action = await super()._reason(new_messages)

                if action.action_type == ActionType.SEND_MESSAGE and action.message:
                    if action.message.recipient is None:
                        logger.warning(f"[reviewer] LLM sent to None (attempt {attempt+1}). Retrying with correction.")
                        self.memory.add_thought("ERROR: You sent a message to 'None'. "
                            "The recipient MUST be 'synthesizer'. Do NOT use 'None' as recipient.")
                        continue
                    if not action.message.content or action.message.content == {}:
                        logger.warning(f"[reviewer] LLM sent empty content (attempt {attempt+1}). Retrying.")
                        self.memory.add_thought("ERROR: Your message content was empty. "
                            "You MUST include the full evaluation and problem JSON in the content.")
                        continue
                    # Validate the LLM approved/rejected the correct problem
                    response_pid = action.message.content.get("problem_id", "")
                    if response_pid and response_pid != expected_problem_id:
                        logger.warning(f"[reviewer] LLM responded for {response_pid} but expected {expected_problem_id} (attempt {attempt+1}). Retrying.")
                        self.memory.add_thought(f"ERROR: You responded about {response_pid}, "
                            f"but you were asked to review {expected_problem_id}. "
                            f"You MUST review {expected_problem_id}, not {response_pid}.")
                        continue
                    return action

                logger.warning(f"[reviewer] LLM produced {action.action_type} instead of approve/reject (attempt {attempt+1}). Retrying.")
                self.memory.add_thought("ERROR: You must send an approve or reject message. "
                    "Use send_message with recipient='synthesizer' and proper evaluation content.")

            logger.error(
                f"[reviewer] All review attempts for {expected_problem_id} "
                "failed. Rejecting as review_failed."
            )
            found_problem = None
            for msg in new_messages:
                if msg.content.get("action") == "review_problem":
                    found_problem = msg.content.get("problem", {})
                    break
            fallback_problem = found_problem or {"id": expected_problem_id}
            return Action(
                action_type=ActionType.SEND_MESSAGE,
                thought=(
                    f"Rejecting {expected_problem_id}: reviewer output remained "
                    "invalid after all retries"
                ),
                message=Message(
                    type=MessageType.REJECT,
                    sender=self.agent_id,
                    recipient="synthesizer",
                    content={
                        "problem_id": expected_problem_id,
                        "evaluation": {
                            "score": 0,
                            "passed": False,
                            "status": "review_failed",
                            "dimensions": {
                                "math_logic": 0,
                                "pedagogy": 0,
                                "scaffolding": 0,
                                "difficulty_match": 0,
                            },
                            "issues": [
                                "The reviewer did not return a valid verdict "
                                "after all retries."
                            ],
                            "feedback": (
                                "The problem was not published because quality "
                                "review could not be completed."
                            ),
                        },
                        "problem": fallback_problem,
                        "feedback": "Quality review service failed.",
                    },
                ),
            )

        # Not a review request — use default LLM reasoning
        return await super()._reason(new_messages)
