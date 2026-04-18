from agi_runtime.config.settings import RuntimeSettings
from agi_runtime.core.agent import HelloAGIAgent


def _agent() -> HelloAGIAgent:
    settings = RuntimeSettings(
        memory_path="memory/test_identity_state.json",
        journal_path="memory/test_events.jsonl",
    )
    return HelloAGIAgent(settings=settings)


def test_histories_are_isolated_by_principal():
    agent = _agent()
    agent.set_principal("telegram:dm:alice")
    agent._history.append({"role": "user", "content": "hi from alice"})

    agent.set_principal("telegram:dm:bob")
    agent._history.append({"role": "user", "content": "hi from bob"})

    agent.set_principal("telegram:dm:alice")
    assert [m["content"] for m in agent._history] == ["hi from alice"]

    agent.set_principal("telegram:dm:bob")
    assert [m["content"] for m in agent._history] == ["hi from bob"]


def test_clear_history_only_for_target_principal():
    agent = _agent()
    alice = "telegram:dm:alice"
    bob = "telegram:dm:bob"

    agent.set_principal(alice)
    agent._history.append({"role": "user", "content": "a1"})
    agent.set_principal(bob)
    agent._history.append({"role": "user", "content": "b1"})

    agent.clear_history(principal_id=alice)

    agent.set_principal(alice)
    assert agent._history == []
    agent.set_principal(bob)
    assert len(agent._history) == 1

