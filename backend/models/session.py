from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import uuid


class DTStage(str, Enum):
    EMPATHIZE = "Empathize"
    DEFINE = "Define"
    IDEATE = "Ideate"
    PROTOTYPE = "Prototype"
    VALIDATE = "Validate"
    COMPLETE = "Complete"


@dataclass
class Message:
    role: str  # "user" | "assistant"
    content: str


@dataclass
class BMCInfo:
    """商业画布九要素，逐步积累"""
    customer_segments: Optional[str] = None
    value_propositions: Optional[str] = None
    channels: Optional[str] = None
    customer_relationships: Optional[str] = None
    revenue_streams: Optional[str] = None
    key_resources: Optional[str] = None
    key_activities: Optional[str] = None
    key_partnerships: Optional[str] = None
    cost_structure: Optional[str] = None

    @property
    def covered_count(self) -> int:
        fields = [
            self.customer_segments, self.value_propositions, self.channels,
            self.customer_relationships, self.revenue_streams, self.key_resources,
            self.key_activities, self.key_partnerships, self.cost_structure,
        ]
        return sum(1 for f in fields if f is not None)

    def update_from_judge(self, extracted: dict) -> None:
        for key, value in extracted.items():
            if value and hasattr(self, key):
                setattr(self, key, value)


@dataclass
class Session:
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    current_stage: DTStage = DTStage.EMPATHIZE
    messages: list[Message] = field(default_factory=list)
    bmc_info: BMCInfo = field(default_factory=BMCInfo)
    turn_count: int = 0
    canvas_generated: bool = False

    def add_message(self, role: str, content: str) -> None:
        self.messages.append(Message(role=role, content=content))
        if role == "user":
            self.turn_count += 1

    def get_history_text(self) -> str:
        return "\n".join(
            f"{m.role.upper()}: {m.content}" for m in self.messages
        )

    def get_history_for_api(self) -> list[dict]:
        return [{"role": m.role, "content": m.content} for m in self.messages]


# In-memory session store (swap to Redis for production)
_sessions: dict[str, Session] = {}


def get_or_create_session(session_id: str) -> Session:
    if session_id not in _sessions:
        _sessions[session_id] = Session(session_id=session_id)
    return _sessions[session_id]
