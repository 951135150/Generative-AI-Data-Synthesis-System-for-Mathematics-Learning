"""Per-agent conversation memory and internal state tracking.

Each agent maintains its own memory of past interactions,
decisions made, and current internal state. This gives agents
persistent identity and context across multiple reasoning cycles.
"""

from typing import Dict, List, Any
from collections import deque

from src.multi_agent.messages import Message


class AgentMemory:
    """Stores truncated conversation history and internal state for one agent."""

    def __init__(self, agent_id: str, max_history: int = 50):
        self.agent_id = agent_id
        self.max_history = max_history

        self._received: deque = deque(maxlen=max_history)
        self._sent: deque = deque(maxlen=max_history)
        self._thoughts: deque = deque(maxlen=max_history)
        self._observations: deque = deque(maxlen=max_history)

        self.internal_state: Dict[str, Any] = {
            "problems_interacted_with": 0,
            "approvals_given": 0,
            "rejections_given": 0,
            "messages_sent": 0,
            "messages_received": 0,
            "current_focus": None,
        }

        self._event_log: List[str] = []

    def add_received(self, msg: Message) -> None:
        self._received.append(msg)
        self.internal_state["messages_received"] += 1

    def add_sent(self, msg: Message) -> None:
        self._sent.append(msg)
        self.internal_state["messages_sent"] += 1

    def add_thought(self, thought: str) -> None:
        self._thoughts.append(thought)

    def add_observation(self, observation: str) -> None:
        self._observations.append(observation)

    def log(self, event: str) -> None:
        self._event_log.append(event)

    def get_recent_received(self, n: int = 10) -> List[Message]:
        items = list(self._received)
        return items[-n:] if n else items

    def get_recent_sent(self, n: int = 10) -> List[Message]:
        items = list(self._sent)
        return items[-n:] if n else items

    def get_recent_thoughts(self, n: int = 5) -> List[str]:
        items = list(self._thoughts)
        return items[-n:] if n else items

    def get_context(self) -> str:
        """Build a compact summary of recent activity for the LLM prompt."""
        lines = []
        lines.append(f"Internal State: {self.internal_state}")

        recent_received = self.get_recent_received(5)
        if recent_received:
            lines.append("Recent messages received:")
            for m in recent_received:
                lines.append(f"  FROM {m.sender}: [{m.type.value}] {str(m.content)[:6000]}")

        recent_sent = self.get_recent_sent(3)
        if recent_sent:
            lines.append("Recent messages sent:")
            for m in recent_sent:
                lines.append(f"  TO {m.recipient}: [{m.type.value}] {str(m.content)[:6000]}")

        recent_thoughts = self.get_recent_thoughts(3)
        if recent_thoughts:
            lines.append("Recent thoughts:")
            for t in recent_thoughts:
                lines.append(f"  - {t[:150]}")

        return "\n".join(lines)
