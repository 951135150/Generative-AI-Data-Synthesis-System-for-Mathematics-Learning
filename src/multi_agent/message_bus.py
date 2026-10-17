"""Async message bus for agent-to-agent communication.

Each agent gets an asyncio.Queue inbox. Messages are routed by
recipient field. Broadcast messages go to all registered agents
except the sender.
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional

from src.multi_agent.messages import Message, MessageType, Conversation

logger = logging.getLogger(__name__)


class RecipientNotFoundError(Exception):
    """Raised when sending to an unregistered agent."""
    pass


class MessageBus:
    """In-memory async message router for multi-agent communication."""

    def __init__(self):
        self._inboxes: Dict[str, asyncio.Queue] = {}
        self._conversations: Dict[str, Conversation] = {}
        self._all_messages: List[Message] = []
        self._lock = asyncio.Lock()
        self._created_at = time.time()

    async def register(self, agent_id: str) -> None:
        """Register an agent with the bus. Creates its inbox queue."""
        async with self._lock:
            if agent_id not in self._inboxes:
                self._inboxes[agent_id] = asyncio.Queue()
                logger.info(f"[MessageBus] Agent '{agent_id}' registered.")

    async def unregister(self, agent_id: str) -> None:
        """Remove an agent from the bus."""
        async with self._lock:
            if agent_id in self._inboxes:
                del self._inboxes[agent_id]
                logger.info(f"[MessageBus] Agent '{agent_id}' unregistered.")

    async def send(self, message: Message) -> None:
        """Send a message to its recipient(s).

        If recipient is None, broadcasts to all registered agents except sender.
        """
        async with self._lock:
            self._all_messages.append(message)

            conv_id = message.conversation_id or "default"
            if conv_id not in self._conversations:
                self._conversations[conv_id] = Conversation(id=conv_id)
            self._conversations[conv_id].add(message)

        if message.recipient is None:
            # Broadcast
            recipients = [aid for aid in self._inboxes if aid != message.sender]
        else:
            if message.recipient not in self._inboxes:
                raise RecipientNotFoundError(
                    f"Recipient '{message.recipient}' is not registered."
                )
            recipients = [message.recipient]

        for rid in recipients:
            await self._inboxes[rid].put(message)

        logger.debug(
            f"[MessageBus] {message.sender} -> {message.recipient or 'ALL'}: "
            f"{message.type.value} | {str(message.content)[:80]}"
        )

    async def receive(self, agent_id: str, timeout: float = 5.0) -> Optional[Message]:
        """Blocking read with timeout. Returns None if timeout expires."""
        try:
            if agent_id not in self._inboxes:
                return None
            msg = await asyncio.wait_for(self._inboxes[agent_id].get(), timeout=timeout)
            return msg
        except asyncio.TimeoutError:
            return None

    async def drain(self, agent_id: str) -> List[Message]:
        """Non-blocking read of all pending messages for an agent."""
        if agent_id not in self._inboxes:
            return []

        messages = []
        queue = self._inboxes[agent_id]
        while not queue.empty():
            try:
                messages.append(queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return messages

    def get_conversation(self, conversation_id: str) -> Optional[Conversation]:
        """Retrieve a full conversation thread by ID."""
        return self._conversations.get(conversation_id)

    def get_all_conversations(self) -> Dict[str, Conversation]:
        """Return all tracked conversations."""
        return dict(self._conversations)

    def get_all_messages_since(self, index: int) -> List[Message]:
        """Return all messages since a given index (for SSE streaming)."""
        return self._all_messages[index:]

    @property
    def total_messages(self) -> int:
        return len(self._all_messages)

    @property
    def registered_agents(self) -> List[str]:
        return list(self._inboxes.keys())
