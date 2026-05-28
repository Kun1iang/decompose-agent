from langchain_core.messages import AIMessage, HumanMessage

from agent_starter.memory.extractor import extract_preferences


def test_extract_nickname():
    out = extract_preferences([HumanMessage(content="以后叫我老张")])
    assert [(p.key, p.value) for p in out] == [("nickname", "老张")]


def test_negation_skipped():
    assert extract_preferences([HumanMessage(content="别叫我老张")]) == []


def test_no_pref_returns_empty():
    assert extract_preferences([HumanMessage(content="今天天气不错")]) == []


def test_uses_last_user_message_only():
    msgs = [HumanMessage(content="叫我小李"), AIMessage(content="好的"), HumanMessage(content="查下天气")]
    assert extract_preferences(msgs) == []  # 最后一条不是偏好声明
