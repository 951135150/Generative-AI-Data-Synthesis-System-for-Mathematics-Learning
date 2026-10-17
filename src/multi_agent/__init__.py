"""True Multi-Agent System for Mathematical Problem Synthesis.

Agents communicate via structured messages through a MessageBus,
run concurrently via asyncio, and autonomously decide who to
collaborate with — no hardcoded pipeline.
"""

from src.multi_agent.messages import Message, MessageType, Conversation
from src.multi_agent.message_bus import MessageBus
from src.multi_agent.memory import AgentMemory
from src.multi_agent.autonomous_agent import AutonomousAgent, Action, ActionType
from src.multi_agent.tools import UTILITY_TOOLS, get_tool_by_name
from src.multi_agent.coordinator import Coordinator, SynthesisConfig, SynthesisResult

__all__ = [
    "Message", "MessageType", "Conversation",
    "MessageBus",
    "AgentMemory",
    "AutonomousAgent", "Action", "ActionType",
    "UTILITY_TOOLS", "get_tool_by_name",
    "Coordinator", "SynthesisConfig", "SynthesisResult",
]
