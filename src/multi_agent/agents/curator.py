"""DatasetCurator — strategic planner monitoring dataset coverage.

Tracks the growing dataset, analyzes coverage gaps, and guides the
Synthesizer on what topics to generate next. Broadcasts when done.
"""

import logging
from typing import List

from src.multi_agent.autonomous_agent import AutonomousAgent, Action, ActionType
from src.multi_agent.messages import Message, MessageType
from src.multi_agent.tools import get_tools_for_agent

logger = logging.getLogger(__name__)


class DatasetCurator(AutonomousAgent):
    """Strategic planner that monitors dataset coverage and guides generation.

    Receives notifications of approved problems, tracks topic distribution,
    identifies gaps, and tells the Synthesizer what to generate next.
    When the target count is reached, broadcasts dataset_complete.
    """

    def __init__(self, message_bus, model=None):
        tools = get_tools_for_agent("curator")
        super().__init__(
            agent_id="curator",
            role="Strategic Planner",
            personality=(
                "You are a strategic dataset curator who monitors the growing "
                "collection of mathematical problems and ensures balanced coverage "
                "across topics, difficulty levels, and question types.\n\n"
                "Your responsibilities:\n"
                "1. Track how many problems have been approved and saved\n"
                "2. Identify gaps in topic coverage, difficulty distribution, "
                "and question type diversity\n"
                "3. Suggest the next topic/difficulty/type to the Synthesizer\n"
                "4. Announce when the dataset is complete\n\n"
                "Workflow:\n"
                "1. When you receive 'synthesis_started' or 'problem_saved' NOTIFY, call "
                "check_coverage to assess the current dataset state.\n"
                "2. Compare check_coverage's total_problems to the target_count from "
                "synthesis_config in your memory.\n"
                "3. If total_problems < target_count: send a 'consult' message to "
                "'synthesizer' with content={action:'suggest_topic', topic:..., difficulty:..., question_type:..., reason:...}. "
                "Then call agent_wait(reason='Waiting for Synthesizer to generate next problem').\n"
                "4. If total_problems >= target_count: IMMEDIATELY use agent_broadcast "
                "with msg_type='notify' and content={event:'dataset_complete', total_problems:N, topics_covered:[...]}. "
                "Then call agent_finish.\n"
                "5. You can also use get_topics and get_dataset_size for additional context."
            ),
            message_bus=message_bus,
            tools=tools,
            model=model,
            temperature=0.3,
            max_idle_seconds=600.0,
        )

    async def _reason(self, new_messages: List[Message]) -> Action:
        """Override to hardcode critical workflow steps.

        synthesis_started / problem_saved → check_coverage (hardcoded)
        After check_coverage → broadcast complete or consult synthesizer (hardcoded)
        Everything else → LLM.
        """
        # 1. Check if we have a coverage result to act on
        coverage = self.memory.internal_state.get("last_coverage_result")
        if coverage:
            self.memory.internal_state.pop("last_coverage_result", None)
            total = coverage.get("total_problems", 0)
            config = self.memory.internal_state.get("synthesis_config", {})
            target = config.get("target_count", 0)
            topics = config.get("topics", ["Derivatives"])
            diff = config.get("difficulty", 3)
            qtype = config.get("question_type", "calculation")
            covered = coverage.get("covered_topics", [])

            logger.info(f"[curator] Coverage: {total}/{target}, topics: {covered}")

            if total >= target:
                self.memory.add_thought(f"Dataset complete: {total}/{target}")
                return Action(
                    action_type=ActionType.BROADCAST,
                    thought=f"Target reached ({total}>={target}). Broadcasting completion.",
                    message=Message(
                        type=MessageType.NOTIFY,
                        sender=self.agent_id,
                        recipient=None,
                        content={
                            "event": "dataset_complete",
                            "total_problems": total,
                            "topics_covered": covered,
                        },
                    ),
                )
            else:
                # Pick next topic (prefer uncovered, then cycle through config topics)
                next_topic = topics[total % len(topics)] if topics else "Derivatives"
                self.memory.add_thought(f"Need more: {total}/{target}. Suggesting {next_topic}")
                return Action(
                    action_type=ActionType.SEND_MESSAGE,
                    thought=f"Suggesting topic {next_topic} ({total}/{target})",
                    message=Message(
                        type=MessageType.CONSULT,
                        sender=self.agent_id,
                        recipient="synthesizer",
                        content={
                            "action": "suggest_topic",
                            "topic": next_topic,
                            "difficulty": diff,
                            "question_type": qtype,
                            "reason": f"Dataset has {total}/{target} problems. Continue generation.",
                        },
                    ),
                )

        # 2. Check if latest message triggers check_coverage
        if new_messages:
            latest = new_messages[-1]
            is_synthesis_start = (
                latest.type == MessageType.NOTIFY
                and latest.content.get("event") == "synthesis_started"
            )
            is_problem_saved = (
                latest.type == MessageType.NOTIFY
                and latest.content.get("event") == "problem_saved"
            )
            if is_synthesis_start or is_problem_saved:
                self.memory.add_thought("Hardcoded: checking coverage")
                config = self.memory.internal_state.get("synthesis_config", {})
                session_start = config.get("session_start_time", 0)
                output_dir = config.get("output_dir")
                tool_args = {"session_start_time": session_start}
                if output_dir:
                    tool_args["output_dir"] = output_dir
                return Action(
                    action_type=ActionType.CALL_TOOL,
                    thought="Checking dataset coverage",
                    tool_name="check_coverage",
                    tool_args=tool_args,
                )

        # 3. Fall back to LLM
        return await super()._reason(new_messages)
