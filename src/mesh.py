"""Core mesh data models and base interfaces."""
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
import time
import uuid

@dataclass
class WorkflowEvent:
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str = "generic"
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

@dataclass
class AgentSession:
    session_id: str
    tenant_id: str
    state: Dict[str, Any] = field(default_factory=dict)
    total_tokens_used: int = 0
    token_limit: int = 50000
    created_at: float = field(default_factory=time.time)

class BaseStateStore:
    """Interface for state persistence."""
    def get_session(self, session_id: str) -> Optional[AgentSession]:
        raise NotImplementedError

    def save_session(self, session: AgentSession) -> None:
        raise NotImplementedError
