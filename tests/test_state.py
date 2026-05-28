from agent_starter.state import AgentState


def test_agentstate_has_generic_working_draft_not_business_fields():
    keys = set(AgentState.__annotations__.keys())
    assert "working_draft" in keys
    assert "messages" in keys
    assert "domain" in keys
    # 去业务化：不允许任何 HR/offer 专属字段
    assert "offer_draft" not in keys
    assert "employee_id" not in keys
