"""Tests for Enterprise Forward-Deployed Agent Governor."""
import pytest
from src.mesh import AgentSession
from src.governor import (
    StatefulAgentGovernor,
    PIIRedactionMiddleware,
    TokenBudgetExceededError,
    ToolValidationError,
    InMemoryStateStore
)

def test_pii_redaction_middleware():
    sample_text = "Customer card: 4532-1234-5678-9012 and email support@example.com with key sk-abcdef123456789012345678."
    redacted = PIIRedactionMiddleware.redact(sample_text)
    assert "[REDACTED_PAN]" in redacted
    assert "[REDACTED_EMAIL]" in redacted
    assert "[REDACTED_KEY]" in redacted
    assert "4532-1234-5678-9012" not in redacted
    assert "support@example.com" not in redacted

def test_governor_tool_registration_and_validation():
    store = InMemoryStateStore()
    session = AgentSession(session_id="sess_101", tenant_id="t1", token_limit=500)
    store.save_session(session)

    governor = StatefulAgentGovernor(state_store=store)

    schema = {
        "required": ["account_id", "amount"],
        "properties": {"account_id": str, "amount": (int, float)}
    }
    def mock_refund(account_id: str, amount: float):
        return {"status": "success", "account": account_id, "refunded": amount}

    governor.register_tool("process_refund", mock_refund, schema)

    # Valid execution
    res = governor.dispatch_tool("sess_101", "process_refund", {"account_id": "acc_99", "amount": 49.99}, tokens_consumed=150)
    assert res["status"] == "success"
    assert session.total_tokens_used == 150

    # Missing required parameter
    with pytest.raises(ToolValidationError) as exc:
        governor.dispatch_tool("sess_101", "process_refund", {"account_id": "acc_99"})
    assert "Missing required parameter 'amount'" in str(exc.value)

    # Parameter type mismatch
    with pytest.raises(ToolValidationError) as exc:
        governor.dispatch_tool("sess_101", "process_refund", {"account_id": "acc_99", "amount": "invalid_number"})
    assert "Parameter 'amount' expected" in str(exc.value)

def test_governor_token_budget_enforcement():
    store = InMemoryStateStore()
    session = AgentSession(session_id="sess_102", tenant_id="t1", token_limit=300)
    store.save_session(session)

    governor = StatefulAgentGovernor(state_store=store)
    governor.register_tool("dummy_op", lambda: {"done": True}, {"required": [], "properties": {}})

    governor.dispatch_tool("sess_102", "dummy_op", {}, tokens_consumed=200)
    assert session.total_tokens_used == 200

    with pytest.raises(TokenBudgetExceededError) as exc:
        governor.dispatch_tool("sess_102", "dummy_op", {}, tokens_consumed=150)
    assert "exceeded token budget" in str(exc.value)

def test_governor_idempotency_caching():
    store = InMemoryStateStore()
    session = AgentSession(session_id="sess_103", tenant_id="t1", token_limit=1000)
    store.save_session(session)

    invocations = 0
    def side_effecting_calc():
        nonlocal invocations
        invocations += 1
        return {"calc_id": invocations}

    governor = StatefulAgentGovernor(state_store=store)
    governor.register_tool("calc", side_effecting_calc, {"required": [], "properties": {}})

    res1 = governor.dispatch_tool("sess_103", "calc", {}, tokens_consumed=50, idempotency_key="tx_abc_123")
    res2 = governor.dispatch_tool("sess_103", "calc", {}, tokens_consumed=50, idempotency_key="tx_abc_123")

    assert res1 == res2
    assert invocations == 1
    assert session.total_tokens_used == 50  # cached execution skipped token increment

def test_governor_audit_logging():
    store = InMemoryStateStore()
    session = AgentSession(session_id="sess_104", tenant_id="t1", token_limit=1000)
    store.save_session(session)

    governor = StatefulAgentGovernor(state_store=store)
    governor.register_tool("echo", lambda msg: msg, {"required": ["msg"], "properties": {"msg": str}})

    governor.dispatch_tool("sess_104", "echo", {"msg": "hello"}, tokens_consumed=80)
    assert len(governor.audit_log) == 1
    assert governor.audit_log[0]["tool_name"] == "echo"
    assert governor.audit_log[0]["tokens_consumed"] == 80
