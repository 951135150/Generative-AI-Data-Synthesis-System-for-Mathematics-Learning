"""Autonomous agent base class with Perceive-Think-Act loop.

Each agent runs its own asyncio loop, reads messages from the MessageBus,
uses LLM reasoning to decide what to do, and sends messages or calls
utility tools. The LLM directly produces content — no two-layer waste.
"""

import asyncio
import json
import logging
import time
from enum import Enum
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from openai import OpenAI

from src.config import Config
from src.multi_agent.memory import AgentMemory
from src.multi_agent.messages import Message, MessageType

logger = logging.getLogger(__name__)


class ActionType(Enum):
    SEND_MESSAGE = "SEND_MESSAGE"
    CALL_TOOL = "CALL_TOOL"
    BROADCAST = "BROADCAST"
    WAIT = "WAIT"
    FINISH = "FINISH"


@dataclass
class Action:
    """The result of an agent's reasoning: what to do next."""
    action_type: ActionType
    thought: str = ""
    message: Optional[Message] = None
    tool_name: Optional[str] = None
    tool_args: Optional[Dict[str, Any]] = None


@dataclass
class ToolDefinition:
    """A utility tool available to agents (NO LLM calls inside tools)."""
    name: str
    description: str
    parameters: Dict[str, Any]  # JSON Schema
    handler: Callable  # async (args: dict) -> Any
    agent_scope: List[str] = field(default_factory=list)


class AutonomousAgent:
    """An agent that autonomously perceives, thinks, and acts.

    The agent runs its own event loop, reading messages addressed to it
    from the MessageBus, using LLM reasoning to decide what to do, and
    executing actions (send messages, call utility tools, or finish).

    Key difference from the old BaseAgent: the LLM directly produces
    content in its response — it does NOT route to another LLM-calling tool.
    """

    def __init__(
        self,
        agent_id: str,
        role: str,
        personality: str,
        message_bus,  # MessageBus (circular import avoidance)
        tools: Optional[List[ToolDefinition]] = None,
        model: Optional[str] = None,
        temperature: float = 0.3,
        max_idle_seconds: float = 120.0,
    ):
        self.agent_id = agent_id
        self.role = role
        self.personality = personality
        self.bus = message_bus
        self.tools = tools or []
        self.model = model or Config.LLM_MODEL
        self.temperature = temperature
        self.max_idle_seconds = max_idle_seconds

        self.memory = AgentMemory(agent_id)
        self.running = False
        self._llm_call_count = 0
        self._last_action_time = time.time()

        self.client = None
        if Config.AI_MODE == "live" and Config.ALLOW_PAID_API:
            self.client = OpenAI(api_key=Config.DEEPSEEK_API_KEY, base_url=Config.DEEPSEEK_BASE_URL,
                                 timeout=60, max_retries=0)

        self._tool_schemas = self._build_tool_schemas()
        self._tool_handlers: Dict[str, Callable] = {t.name: t.handler for t in self.tools}

    def _build_tool_schemas(self) -> list:
        """Build tool schemas including communication pseudo-tools."""
        schemas = []

        # Communication pseudo-tools (always available)
        schemas.append({
            "type": "function",
            "function": {
                "name": "send_message",
                "description": "Send a message to another agent. Use this to request work, share results, approve/reject, or consult.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "recipient": {
                            "type": "string",
                            "description": "Agent ID to send to (synthesizer, scaffolder, reviewer, curator)",
                        },
                        "msg_type": {
                            "type": "string",
                            "enum": ["request", "response", "approve", "reject", "delegate", "consult", "notify", "inform"],
                            "description": "Type of message",
                        },
                        "content": {
                            "type": "object",
                            "description": "The message content. Include your FULL work product here (problem JSON, evaluation, scaffolding, etc.).",
                        },
                    },
                    "required": ["recipient", "msg_type", "content"],
                },
            },
        })
        schemas.append({
            "type": "function",
            "function": {
                "name": "agent_broadcast",
                "description": "Broadcast a message to all other agents (for important announcements).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "msg_type": {
                            "type": "string",
                            "enum": ["notify", "inform"],
                            "description": "Type of broadcast",
                        },
                        "content": {
                            "type": "object",
                            "description": "The broadcast content",
                        },
                    },
                    "required": ["msg_type", "content"],
                },
            },
        })
        schemas.append({
            "type": "function",
            "function": {
                "name": "agent_wait",
                "description": "Wait briefly (another agent is working). Use when you have no new messages requiring action.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "reason": {"type": "string", "description": "Why you are waiting"},
                    },
                    "required": ["reason"],
                },
            },
        })
        schemas.append({
            "type": "function",
            "function": {
                "name": "agent_finish",
                "description": "Finish your work. Use when your role is complete.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "summary": {"type": "string", "description": "Summary of what you accomplished"},
                    },
                    "required": ["summary"],
                },
            },
        })

        # Actual utility tools
        for t in self.tools:
            schemas.append({
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            })

        return schemas

    # ── Main loop ──────────────────────────────────────────────

    async def run(self) -> None:
        """Main agent loop: Perceive -> Think -> Act."""
        await self.bus.register(self.agent_id)
        self.running = True
        self.memory.log(f"Agent '{self.agent_id}' ({self.role}) started.")
        logger.info(f"[{self.agent_id}] Started. Role: {self.role}")

        while self.running:
            # 1. PERCEIVE: read incoming messages
            messages = await self.bus.drain(self.agent_id)

            if not messages:
                # Fall through to reasoning if we have pending work
                has_pending = self.memory.internal_state.get("pending_action")
                needs_followup = self.memory.internal_state.pop("_needs_followup_reasoning", False)
                if has_pending or needs_followup:
                    pass  # Let _reason handle the pending action or tool result
                else:
                    if time.time() - self._last_action_time > self.max_idle_seconds:
                        logger.info(f"[{self.agent_id}] Idle timeout. Finishing.")
                        self.running = False
                        break
                    await asyncio.sleep(0.5)
                    continue

            for msg in messages:
                self.memory.add_received(msg)
                # Auto-clear state flags based on incoming messages
                if msg.type.value == "consult" and msg.sender == "curator":
                    self.memory.internal_state.pop("awaiting_curator_suggestion", None)
                if msg.type.value == "broadcast" and msg.content.get("event") == "dataset_complete":
                    self.memory.internal_state["dataset_complete_received"] = True

            self._last_action_time = time.time()

            # 2. THINK: decide what to do
            try:
                action = await self._reason(messages)
            except Exception as e:
                logger.error(f"[{self.agent_id}] Reasoning failed: {e}")
                continue

            self.memory.add_thought(action.thought)

            # 3. ACT: execute the decided action
            try:
                await self._act(action)
            except Exception as e:
                logger.error(f"[{self.agent_id}] Action failed: {e}")

        self.memory.log(f"Agent '{self.agent_id}' finished.")
        logger.info(f"[{self.agent_id}] Finished. LLM calls: {self._llm_call_count}")

    # ── Reasoning ──────────────────────────────────────────────

    async def _reason(self, new_messages: List[Message]) -> Action:
        """Use LLM to decide the next action based on context and new messages."""
        if self._llm_call_count >= 20:
            return Action(action_type=ActionType.FINISH, thought="Per-agent model call budget exhausted.")
        if self.client is None:
            return Action(action_type=ActionType.WAIT, thought="External model access is disabled.")
        prompt = self._build_reasoning_prompt(new_messages)
        if new_messages and Config.RAG_ENABLED:
            from src.rag import get_retriever
            from src.rag.service import evidence_prompt
            config = self.memory.internal_state.get("synthesis_config", {})
            problem = next((m.content.get("problem") for m in new_messages if m.content.get("problem")), {})
            topics = [problem["topic"]] if problem.get("topic") else config.get("topics", [])[:1]
            if topics:
                query = " ".join(topics) + " " + problem.get("problem_statement", "")
                bundle = await asyncio.to_thread(get_retriever().retrieve, query, topics=topics,
                                                  purpose=self.agent_id, top_k=3)
                self.memory.internal_state["last_evidence_bundle_id"] = bundle.get("bundle_id")
                # Evidence is added after message formatting, outside the legacy message truncation.
                prompt += evidence_prompt(bundle)

        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = await asyncio.to_thread(self.client.chat.completions.create,
                    model=self.model,
                    messages=[
                        {"role": "system", "content": self._build_system_prompt()},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=self.temperature,
                    max_tokens=4096,
                    tools=self._tool_schemas if self._tool_schemas else None,
                    tool_choice="auto" if self._tool_schemas else None,
                )
                self._llm_call_count += 1
                return self._parse_action(response)
            except Exception as e:
                logger.warning(f"[{self.agent_id}] LLM attempt {attempt + 1} failed: {e}")
                if attempt == max_retries - 1:
                    return Action(action_type=ActionType.WAIT, thought=f"LLM failed: {e}")
                await asyncio.sleep(2 ** attempt)

        return Action(action_type=ActionType.WAIT, thought="All retries exhausted")

    def _build_system_prompt(self) -> str:
        """Build the agent's system prompt with personality, role, and action schema."""
        other_agents = "ProblemSynthesizer, ScaffoldingDesigner, QualityReviewer, DatasetCurator"
        tool_names = [t.name for t in self.tools] if self.tools else []

        return f"""{self.personality}

You are the {self.role} in a multi-agent mathematical problem synthesis system.
Other agents: {other_agents}
Your agent ID: {self.agent_id}

You can:
- Send messages to specific agents to request work, share results, get opinions
- Call utility tools: {tool_names if tool_names else 'none available'}
- Broadcast important announcements to all agents
- Wait if you have nothing to do (another agent is working)
- Finish when your work is complete

CRITICAL: When generating or evaluating content, you MUST produce the FULL content
directly in your message. Do NOT call a tool that would call another LLM.
Tools are ONLY for utility operations (file I/O, data lookups).
You are the intelligence — produce the content yourself.

Output your Action as JSON with the tool_call format:
- To send a message: use a tool call for "send_message" with recipient, msg_type, and content
- To call a utility tool: use the tool's actual name
- To wait: use a tool call for "agent_wait"
- To finish: use a tool call for "agent_finish"
"""

    def _build_reasoning_prompt(self, new_messages: List[Message]) -> str:
        """Build the user prompt for the reasoning step."""
        parts = []

        parts.append("[YOUR MEMORY]")
        parts.append(self.memory.get_context())

        parts.append("\n[NEW MESSAGES]")
        if new_messages:
            for msg in new_messages:
                parts.append(
                    f"  [{msg.type.value}] FROM {msg.sender}: "
                    f"{json.dumps(msg.content, ensure_ascii=False)[:6000]}"
                )
        else:
            parts.append("  (no new messages)")

        parts.append("\n[TASK]")
        parts.append("Review the new messages and decide what to do next.")
        parts.append("Remember: produce actual content in your response, not just routing decisions.")

        # Highlight pending actions from internal state
        pending = self.memory.internal_state.get("pending_action")
        if pending:
            parts.append(f"\n*** PENDING ACTION: {pending} *** You MUST complete this action NOW.")

        return "\n".join(parts)

    def _parse_action(self, response) -> Action:
        """Parse the LLM response into an Action.

        Handles both tool_call responses (function calling) and plain text.
        """
        choice = response.choices[0]
        msg = choice.message

        # Case A: LLM used function calling to express its action
        if msg.tool_calls:
            tc = msg.tool_calls[0]
            tool_name = tc.function.name
            try:
                tool_args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                tool_args = {}

            thought = msg.content or f"Calling {tool_name}"

            if tool_name == "send_message":
                return Action(
                    action_type=ActionType.SEND_MESSAGE,
                    thought=thought,
                    message=Message(
                        type=MessageType(tool_args.get("msg_type", "notify")),
                        sender=self.agent_id,
                        recipient=tool_args.get("recipient"),
                        content=tool_args.get("content", {}),
                    ),
                )
            elif tool_name == "agent_broadcast":
                return Action(
                    action_type=ActionType.BROADCAST,
                    thought=thought,
                    message=Message(
                        type=MessageType(tool_args.get("msg_type", "notify")),
                        sender=self.agent_id,
                        recipient=None,
                        content=tool_args.get("content", {}),
                    ),
                )
            elif tool_name == "agent_wait":
                return Action(action_type=ActionType.WAIT, thought=thought)
            elif tool_name == "agent_finish":
                return Action(action_type=ActionType.FINISH, thought=thought)
            else:
                return Action(
                    action_type=ActionType.CALL_TOOL,
                    thought=thought,
                    tool_name=tool_name,
                    tool_args=tool_args,
                )

        # Case B: Plain text response — try to parse as JSON Action
        text = msg.content or ""
        try:
            cleaned = text.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[-1]
                if cleaned.endswith("```"):
                    cleaned = cleaned[:-3]
                cleaned = cleaned.strip()
            data = json.loads(cleaned)
            return self._action_from_dict(data)
        except json.JSONDecodeError:
            # Treat unstructured text as the agent thinking/waiting
            return Action(action_type=ActionType.WAIT, thought=text[:200])

    def _action_from_dict(self, data: dict) -> Action:
        """Create an Action from a parsed JSON dict."""
        action_type_str = data.get("action_type", "WAIT")
        try:
            action_type = ActionType(action_type_str)
        except ValueError:
            action_type = ActionType.WAIT

        message = None
        if data.get("message"):
            msg_data = data["message"]
            message = Message(
                type=MessageType(msg_data.get("type", "inform")),
                sender=self.agent_id,
                recipient=msg_data.get("recipient"),
                content=msg_data.get("content", {}),
            )

        return Action(
            action_type=action_type,
            thought=data.get("thought", ""),
            message=message,
            tool_name=data.get("tool_name"),
            tool_args=data.get("tool_args"),
        )

    # ── Execution ──────────────────────────────────────────────

    async def _act(self, action: Action) -> None:
        """Execute the decided action."""
        if action.action_type == ActionType.SEND_MESSAGE and action.message:
            if action.message.conversation_id is None:
                action.message.conversation_id = f"conv_{action.message.id}"
            await self.bus.send(action.message)
            self.memory.add_sent(action.message)
            logger.info(
                f"[{self.agent_id}] -> {action.message.recipient}: "
                f"{action.message.type.value} | {str(action.message.content)[:100]}"
            )
            # Clear pending action when we notify the curator
            if (action.message.recipient == "curator" and
                action.message.content.get("event") == "problem_saved"):
                self.memory.internal_state.pop("pending_action", None)
                self.memory.internal_state["awaiting_curator_suggestion"] = True

        elif action.action_type == ActionType.BROADCAST and action.message:
            action.message.recipient = None
            if action.message.conversation_id is None:
                action.message.conversation_id = f"conv_{action.message.id}"
            await self.bus.send(action.message)
            self.memory.add_sent(action.message)
            logger.info(f"[{self.agent_id}] BROADCAST: {action.message.type.value}")

        elif action.action_type == ActionType.CALL_TOOL:
            handler = self._tool_handlers.get(action.tool_name)
            if handler:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        result = await handler(action.tool_args or {})
                    else:
                        result = handler(action.tool_args or {})
                    self.memory.add_observation(f"Tool {action.tool_name}: {str(result)[:200]}")
                    logger.info(f"[{self.agent_id}] Tool {action.tool_name}: {str(result)[:100]}")

                    # Post-tool state tracking for reliable multi-turn workflows
                    if action.tool_name == "save_problem" and result.get("saved"):
                        self.memory.internal_state["pending_action"] = "notify_curator"
                        self.memory.internal_state["last_saved_problem_id"] = result.get("problem_id", "")
                        self.memory.internal_state["_needs_followup_reasoning"] = True

                    if action.tool_name == "check_coverage":
                        self.memory.internal_state["last_coverage_result"] = result
                        self.memory.internal_state["_needs_followup_reasoning"] = True
                except Exception as e:
                    logger.error(f"[{self.agent_id}] Tool {action.tool_name} error: {e}")
                    self.memory.add_observation(f"Tool {action.tool_name} FAILED: {e}")
            else:
                logger.warning(f"[{self.agent_id}] Unknown tool: {action.tool_name}")

        elif action.action_type == ActionType.WAIT:
            await asyncio.sleep(1.0)

        elif action.action_type == ActionType.FINISH:
            self.running = False
            logger.info(f"[{self.agent_id}] Finished by own decision.")

    # ── Helpers ────────────────────────────────────────────────

    @property
    def llm_call_count(self) -> int:
        return self._llm_call_count
