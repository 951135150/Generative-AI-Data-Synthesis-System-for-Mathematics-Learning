"""Structured message protocol for inter-agent communication.

Each agent sends and receives Message objects through the MessageBus.
Messages form conversation threads identified by conversation_id.
"""

import time
import uuid
from enum import Enum
from dataclasses import dataclass, field
from typing import Any, Optional


class MessageType(Enum):
    """Types of messages agents can send to each other."""
    REQUEST = "request"       # "Please do X for me"
    RESPONSE = "response"     # "Here is what you asked for"
    APPROVE = "approve"       # "I approve this work"
    REJECT = "reject"         # "I reject this work because..."
    DELEGATE = "delegate"     # "I assign task Z to you"
    CONSULT = "consult"       # "I want your opinion/advice"
    NOTIFY = "notify"         # "FYI: state changed"
    BROADCAST = "broadcast"   # "Everyone should know this"
    ERROR = "error"           # "Something went wrong"


@dataclass
class Message:
    """A single message between agents in the system."""
    type: MessageType
    sender: str
    content: dict = field(default_factory=dict)
    recipient: Optional[str] = None  # None = broadcast to all
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    conversation_id: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
    reply_to: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type.value,
            "sender": self.sender,
            "recipient": self.recipient,
            "conversation_id": self.conversation_id,
            "content": self.content,
            "timestamp": self.timestamp,
            "reply_to": self.reply_to,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Message":
        return cls(
            id=d.get("id", uuid.uuid4().hex[:12]),
            type=MessageType(d["type"]),
            sender=d["sender"],
            recipient=d.get("recipient"),
            conversation_id=d.get("conversation_id"),
            content=d.get("content", {}),
            timestamp=d.get("timestamp", time.time()),
            reply_to=d.get("reply_to"),
        )


@dataclass
class Conversation:
    """A thread of messages forming a single conversation."""
    id: str
    messages: list = field(default_factory=list)

    def add(self, msg: Message) -> None:
        self.messages.append(msg)

    @property
    def thread(self) -> list:
        return self.messages


def create_request(sender: str, recipient: str, content: dict,
                   conversation_id: Optional[str] = None) -> Message:
    return Message(
        type=MessageType.REQUEST, sender=sender, recipient=recipient,
        content=content, conversation_id=conversation_id or f"conv_{uuid.uuid4().hex[:8]}",
    )


def create_response(sender: str, recipient: str, content: dict,
                    reply_to: str, conversation_id: Optional[str] = None) -> Message:
    return Message(
        type=MessageType.RESPONSE, sender=sender, recipient=recipient,
        content=content, reply_to=reply_to,
        conversation_id=conversation_id or f"conv_{uuid.uuid4().hex[:8]}",
    )
