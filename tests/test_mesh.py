from src.mesh import WorkflowEvent, AgentSession

def test_workflow_event_initialization():
    event = WorkflowEvent(event_type="payment_dispute", payload={"case_id": "c123"})
    assert event.event_type == "payment_dispute"
    assert event.payload["case_id"] == "c123"
    assert event.event_id is not None

def test_agent_session_limits():
    session = AgentSession(session_id="s1", tenant_id="tenant_a", token_limit=1000)
    assert session.total_tokens_used == 0
    assert session.token_limit == 1000
