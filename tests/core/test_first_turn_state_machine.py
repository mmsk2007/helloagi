from agi_runtime.memory.principals import PrincipalProfileStore


def test_bootstrap_instruction_transitions(tmp_path):
    state_path = tmp_path / "principals.json"
    profiles_dir = tmp_path / "profiles"
    store = PrincipalProfileStore(
        state_path=str(state_path),
        profiles_dir=str(profiles_dir),
    )
    pid = "telegram:dm:test-user"

    store.record_user_message(pid, "hello there")
    first_instruction = store.bootstrap_instruction(pid)
    assert first_instruction is not None
    assert "/help" in first_instruction

    store.record_user_message(pid, "my name is Alex")
    store.record_user_message(pid, "I prefer brief casual responses")
    store.record_user_message(pid, "my goal is ship an autonomous coding agent")
    store.record_user_message(pid, "please avoid risky shell commands")

    state = store.get(pid)
    assert state.bootstrap_completed is True
    assert store.bootstrap_instruction(pid) is None


def test_profile_ids_merge_dm_and_group_aliases(tmp_path):
    state_path = tmp_path / "principals.json"
    profiles_dir = tmp_path / "profiles"
    store = PrincipalProfileStore(
        state_path=str(state_path),
        profiles_dir=str(profiles_dir),
    )

    dm_pid = "telegram:dm:test-user"
    group_pid = "telegram:group:team-room:user:test-user"

    assert store.resolve_profile_id(dm_pid) == "telegram:user:test-user"
    assert store.resolve_profile_id(group_pid) == "telegram:user:test-user"

    store.update(dm_pid, preferred_name="Alex", timezone="Asia/Riyadh", onboarded=True)
    state = store.get(group_pid)

    assert state.preferred_name == "Alex"
    assert state.timezone == "Asia/Riyadh"
    assert state.onboarded is True

