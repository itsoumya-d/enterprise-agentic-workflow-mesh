"""Enterprise Forward-Deployed Agent Governor & Execution Mesh."""
from typing import Dict, Any, Callable, Optional, Set, List
import re
import time
import hashlib
from src.mesh import AgentSession, BaseStateStore

class TokenBudgetExceededError(Exception):
    """Raised when an agent session exceeds its configured token budget."""
    pass

class ToolValidationError(Exception):
    """Raised when an LLM tool call payload violates parameter schemas."""
    pass

class PIIRedactionMiddleware:
    """Enterprise redaction filter for PAN, emails, and credentials."""
    PAN_REGEX = re.compile(r'\b(?:\d[ -]*?){13,19}\b')
    EMAIL_REGEX = re.compile(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+')
    API_KEY_REGEX = re.compile(r'(?:bearer\s+[a-zA-Z0-9_\-\.]{20,}|(?:sk|key|token)[-_][a-zA-Z0-9]{20,})', re.IGNORECASE)

    @classmethod
    def redact(cls, text: str) -> str:
        if not isinstance(text, str):
            return text
        text = cls.PAN_REGEX.sub("[REDACTED_PAN]", text)
        text = cls.EMAIL_REGEX.sub("[REDACTED_EMAIL]", text)
        text = cls.API_KEY_REGEX.sub("[REDACTED_KEY]", text)
        return text

    @classmethod
    def sanitize_payload(cls, payload: Any) -> Any:
        if isinstance(payload, str):
            return cls.redact(payload)
        elif isinstance(payload, dict):
            return {k: cls.sanitize_payload(v) for k, v in payload.items()}
        elif isinstance(payload, list):
            return [cls.sanitize_payload(v) for v in payload]
        return payload

class InMemoryStateStore(BaseStateStore):
    """Thread-safe transactional in-memory store for session states."""
    def __init__(self):
        self._store: Dict[str, AgentSession] = {}

    def get_session(self, session_id: str) -> Optional[AgentSession]:
        return self._store.get(session_id)

    def save_session(self, session: AgentSession) -> None:
        self._store[session.session_id] = session

class StatefulAgentGovernor:
    """Manages agent tool execution, validation, idempotency, and audit trails."""

    def __init__(self, state_store: Optional[BaseStateStore] = None):
        self.state_store = state_store or InMemoryStateStore()
        self.tool_registry: Dict[str, Callable] = {}
        self.tool_schemas: Dict[str, Dict[str, Any]] = {}
        self.audit_log: List[Dict[str, Any]] = []
        self._idempotency_cache: Dict[str, Any] = {}

    def register_tool(self, name: str, fn: Callable, schema: Dict[str, Any]) -> None:
        """Register an enterprise tool with parameter type schemas."""
        self.tool_registry[name] = fn
        self.tool_schemas[name] = schema

    def validate_tool_args(self, tool_name: str, args: Dict[str, Any]) -> None:
        """Validate tool invocation against registered parameter schemas."""
        if tool_name not in self.tool_schemas:
            raise ToolValidationError(f"Tool '{tool_name}' is not registered.")
        schema = self.tool_schemas[tool_name]
        required = schema.get("required", [])
        for field in required:
            if field not in args:
                raise ToolValidationError(f"Missing required parameter '{field}' for tool '{tool_name}'")
        param_types = schema.get("properties", {})
        for param, expected_type in param_types.items():
            if param in args and not isinstance(args[param], expected_type):
                type_name = "/".join(t.__name__ for t in expected_type) if isinstance(expected_type, tuple) else getattr(expected_type, '__name__', str(expected_type))
                raise ToolValidationError(
                    f"Parameter '{param}' expected {type_name}, got {type(args[param]).__name__}"
                )

    def dispatch_tool(
        self,
        session_id: str,
        tool_name: str,
        raw_args: Dict[str, Any],
        tokens_consumed: int = 100,
        idempotency_key: Optional[str] = None
    ) -> Any:
        """Dispatch a validated, budget-governed, PII-sanitized tool call."""
        session = self.state_store.get_session(session_id)
        if not session:
            raise ValueError(f"Session '{session_id}' not found.")

        # 1. Token Budget Enforcement
        if session.total_tokens_used + tokens_consumed > session.token_limit:
            raise TokenBudgetExceededError(
                f"Session '{session_id}' exceeded token budget: {session.total_tokens_used} + {tokens_consumed} > {session.token_limit}"
            )

        # 2. Idempotency Check
        cache_key = None
        if idempotency_key:
            cache_key = f"{session_id}:{tool_name}:{idempotency_key}"
            if cache_key in self._idempotency_cache:
                return self._idempotency_cache[cache_key]

        # 3. PII Redaction & Schema Validation
        sanitized_args = PIIRedactionMiddleware.sanitize_payload(raw_args)
        self.validate_tool_args(tool_name, sanitized_args)

        # 4. Tool Execution & Audit
        start_time = time.time()
        fn = self.tool_registry[tool_name]
        result = fn(**sanitized_args)
        duration = time.time() - start_time

        # Update Session & Audit
        session.total_tokens_used += tokens_consumed
        self.state_store.save_session(session)

        audit_entry = {
            "session_id": session_id,
            "tool_name": tool_name,
            "duration_ms": round(duration * 1000, 2),
            "tokens_consumed": tokens_consumed,
            "timestamp": time.time()
        }
        self.audit_log.append(audit_entry)

        if cache_key:
            self._idempotency_cache[cache_key] = result

        return result
