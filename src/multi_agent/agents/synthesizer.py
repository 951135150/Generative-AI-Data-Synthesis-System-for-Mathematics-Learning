"""ProblemSynthesizer — generates mathematical problems autonomously.

Receives generation requests, produces complete problem JSON directly
in its LLM response, and sends it to the Reviewer for quality control.
"""

import json
import logging
from typing import List

from src.multi_agent.autonomous_agent import AutonomousAgent, Action, ActionType
from src.multi_agent.messages import Message, MessageType
from src.multi_agent.tools import get_tools_for_agent

logger = logging.getLogger(__name__)


class ProblemSynthesizer(AutonomousAgent):
    """Creative mathematician that generates novel calculus problems.

    When asked to generate, it produces the COMPLETE problem (statement,
    solution, scaffolding) in a single LLM response and sends it to the
    Reviewer. On rejection, it reads the feedback and regenerates.
    """

    def __init__(self, message_bus, model=None):
        tools = get_tools_for_agent("synthesizer")
        self._last_approved_problem = None  # Cache for hardcoded save flow
        super().__init__(
            agent_id="synthesizer",
            role="Creative Mathematician",
            personality=(
                "You are a creative mathematician who generates novel, "
                "pedagogically sound calculus problems. You think deeply about "
                "what makes a problem interesting and instructive.\n\n"
                "When generating a problem, produce the COMPLETE problem as a JSON "
                "object in your message content. The JSON MUST include ALL of these fields:\n"
                '- "id": a unique string ID (e.g. "DERIV-CALC-003")\n'
                '- "topic": the calculus topic\n'
                '- "problem_statement": the problem text\n'
                '- "question_type": "calculation", "mcq", or "fill_in"\n'
                '- "difficulty": integer 1-5\n'
                '- "solution": detailed step-by-step solution with LaTeX ($ for inline, $$ for display, double backslashes)\n'
                '- "scaffolding": a NON-EMPTY array of {{"step": N, "hint": "..."}} objects with 2-4 progressive hints\n'
                '- "integration_analysis": brief note on how this connects to other topics\n'
                "- quality_score: 85\n\n"
                "For MCQ questions, also include 'options' (A/B/C/D) and 'answer'. "
                "For fill-in questions, use [BLANK_1], [BLANK_2] in the statement and "
                "include 'correct_values'.\n\n"
                "LaTeX rules: use $ for inline math, $$ for display math. "
                "Double backslashes for LaTeX commands. NO \\quad macros.\n\n"
                "Workflow (check internal_state for pending_action to know what to do next):\n"
                "1. When you receive a REQUEST to generate, produce the problem IMMEDIATELY "
                "and send it to the 'reviewer' as type 'request' with content={action:'review_problem', problem:...}.\n"
                "2. If you receive a REJECT, read the feedback and regenerate. Send revised "
                "version to 'reviewer' again.\n"
                "3. When you receive an APPROVE: extract the FULL problem from the 'problem' "
                "field and call save_problem tool with it.\n"
                "4. CRITICAL: If internal_state shows pending_action='notify_curator', you MUST "
                "send a 'notify' to 'curator' with content={event:'problem_saved', problem_id:..., topic:...}. "
                "Do NOT call agent_finish — the curator will tell you what to do next.\n"
                "5. If internal_state shows awaiting_curator_suggestion=true and you have no new "
                "messages, call agent_wait. The curator is checking coverage.\n"
                "6. When you receive a CONSULT from curator, generate another problem and "
                "send to 'reviewer'. This cycle repeats until dataset is complete.\n"
                "7. When you receive a BROADCAST with event='dataset_complete', call agent_finish.\n"
                "8. NEVER call agent_finish unless you see dataset_complete broadcast."
            ),
            message_bus=message_bus,
            tools=tools,
            model=model,
            temperature=0.5,
            max_idle_seconds=600.0,
        )

    async def _reason(self, new_messages: List[Message]) -> Action:
        """Override to hardcode critical workflow steps that LLM prompt fails at.

        APPROVE → save_problem (hardcoded, no LLM call needed)
        pending_action='notify_curator' → send notify (hardcoded)
        Everything else → delegate to LLM via parent _reason.
        """
        # Check for pending action first (set by _act after save_problem succeeds)
        pending = self.memory.internal_state.get("pending_action")

        if pending == "notify_curator":
            problem_id = self.memory.internal_state.get("last_saved_problem_id", "unknown")
            saved = self._last_approved_problem or {}
            topic = saved.get("topic", "unknown")
            self.memory.add_thought(f"Hardcoded: notifying curator about saved problem {problem_id}")
            return Action(
                action_type=ActionType.SEND_MESSAGE,
                thought=f"Sending problem_saved notification to curator for {problem_id}",
                message=Message(
                    type=MessageType.NOTIFY,
                    sender=self.agent_id,
                    recipient="curator",
                    content={
                        "event": "problem_saved",
                        "problem_id": problem_id,
                        "topic": topic,
                    },
                ),
            )

        # Check if latest message is an APPROVE → hardcoded save_problem
        if new_messages:
            latest = new_messages[-1]
            if latest.type == MessageType.APPROVE:
                approved_pid = latest.content.get("problem_id", "")
                expected_pid = self.memory.internal_state.get("last_sent_for_review", "")
                if expected_pid and approved_pid and approved_pid != expected_pid:
                    logger.warning(f"[synthesizer] Ignoring late approval for {approved_pid} (expected {expected_pid})")
                    self.memory.add_thought(f"Received late approval for {approved_pid}, ignoring — waiting for {expected_pid}")
                    return Action(action_type=ActionType.WAIT, thought=f"Ignoring late {approved_pid} approval, waiting for {expected_pid}")
                problem_data = latest.content.get("problem", {})
                if problem_data:
                    self._last_approved_problem = problem_data
                    problem_id = problem_data.get("id", "unknown")
                    self.memory.add_thought(f"Hardcoded: saving approved problem {problem_id}")
                    self._llm_call_count += 0  # Don't count this as an LLM call
                    config = self.memory.internal_state.get("synthesis_config", {})
                    output_dir = config.get("output_dir")
                    return Action(
                        action_type=ActionType.CALL_TOOL,
                        thought=f"Problem {problem_id} approved — saving to disk",
                        tool_name="save_problem",
                        tool_args={"problem": problem_data, "output_dir": output_dir} if output_dir else {"problem": problem_data},
                    )

        # Fall back to LLM for all other decisions (with rogue-output guard)
        for attempt in range(3):
            action = await super()._reason(new_messages)

            # Track last problem sent for review (for approval validation)
            if (action.action_type == ActionType.SEND_MESSAGE
                    and action.message
                    and action.message.recipient == "reviewer"
                    and action.message.content.get("action") == "review_problem"):
                problem = action.message.content.get("problem", {})
                pid = problem.get("id")
                if pid:
                    self.memory.internal_state["last_sent_for_review"] = pid

            # Validate: if LLM produces SEND_MESSAGE to None or empty, retry
            if action.action_type == ActionType.SEND_MESSAGE and action.message:
                if action.message.recipient is None:
                    logger.warning(f"[synthesizer] LLM sent to None (attempt {attempt+1}). Retrying.")
                    self.memory.add_thought("ERROR: You sent to 'None'. Recipient must be 'reviewer' or 'curator'.")
                    continue
                if not action.message.content or action.message.content == {}:
                    logger.warning(f"[synthesizer] LLM sent empty content (attempt {attempt+1}). Retrying.")
                    self.memory.add_thought("ERROR: Empty content. Must include problem JSON or notification content.")
                    continue
            elif action.action_type == ActionType.FINISH:
                # Guard: don't finish unless dataset_complete was received
                if not self.memory.internal_state.get("dataset_complete_received"):
                    logger.warning(f"[synthesizer] LLM tried to finish prematurely (attempt {attempt+1}). Retrying.")
                    self.memory.add_thought("ERROR: Do NOT call agent_finish unless you received dataset_complete broadcast.")
                    continue

            return action

        logger.error("[synthesizer] All attempts failed. Falling back to WAIT.")
        return Action(action_type=ActionType.WAIT, thought="All generation attempts exhausted")
