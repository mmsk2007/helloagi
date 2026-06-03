from agi_runtime.context_unrolling import ContextWorkspace
from agi_runtime.events import EventSpine, OrganEvent


def test_organ_event_schema_serializes_json_safe_provenance_and_verification_state():
    event = OrganEvent.create(
        trace_id="trace-123",
        organ="brain",
        kind="context_plan_created",
        payload={"workspace_items": 2},
        provenance="cli:context-plan",
        confidence=0.93,
        verified=True,
    )

    row = event.to_dict()

    assert row["event_id"].startswith("evt_")
    assert row["trace_id"] == "trace-123"
    assert row["organ"] == "brain"
    assert row["kind"] == "context_plan_created"
    assert row["payload"] == {"workspace_items": 2}
    assert row["provenance"] == "cli:context-plan"
    assert row["confidence"] == 0.93
    assert row["verified"] is True
    assert isinstance(row["timestamp"], str)


def test_organ_event_rejects_non_json_safe_payloads():
    try:
        OrganEvent.create(
            trace_id="trace-123",
            organ="brain",
            kind="bad_payload",
            payload={"not_json_safe": object()},
            provenance="test",
            confidence=1.0,
            verified=False,
        )
    except ValueError as exc:
        assert "payload must be JSON-safe" in str(exc)
    else:
        raise AssertionError("expected non-JSON-safe payload to be rejected")


def test_event_spine_appends_and_reads_immutable_event_snapshots():
    spine = EventSpine()
    event = spine.append(
        trace_id="trace-abc",
        organ="nervous",
        kind="agent_turn_start",
        payload={"input_present": True},
        provenance="agent:think",
        confidence=1.0,
        verified=True,
    )

    first_read = spine.read()
    second_read = spine.read(trace_id="trace-abc")

    assert first_read == [event]
    assert second_read == [event]
    first_read.clear()
    assert spine.read() == [event]


def test_context_plan_event_is_not_verified_when_any_workspace_item_is_unverified():
    spine = EventSpine()
    workspace = ContextWorkspace(goal="Inspect unverified observation", trace_id="trace-unverified")
    workspace.add(
        item_type="tool_observation",
        content={"summary": "Tool output was parsed but not checked"},
        source="tool:file_read",
        confidence=0.7,
        observed=True,
        verified=False,
    )

    event = spine.record_context_plan(workspace, provenance="cli:context-plan")

    assert event.payload["items_count"] == 1
    assert event.payload["verified_items"] == 0
    assert event.verified is False


def test_context_plan_and_agent_turn_events_share_trace_id_and_distinguish_state():
    spine = EventSpine()
    workspace = ContextWorkspace(goal="Diagnose failing tests", trace_id="trace-shared")
    workspace.add(
        item_type="user_goal",
        content={"summary": "Diagnose failing tests"},
        source="cli",
        confidence=1.0,
        observed=True,
        verified=True,
    )
    workspace.add(
        item_type="primitive_selection",
        content={"selected": ["inspect_failing_tests"]},
        source="primitive_selector",
        confidence=0.8,
        observed=False,
        verified=False,
    )

    start = spine.record_agent_turn_start(trace_id=workspace.trace_id, input_present=True)
    plan = spine.record_context_plan(workspace, provenance="cli:context-plan")
    end = spine.record_agent_turn_end(trace_id=workspace.trace_id, success=True)

    assert {event.trace_id for event in (start, plan, end)} == {"trace-shared"}
    assert plan.organ == "brain"
    assert plan.kind == "context_plan_created"
    assert plan.payload["items_count"] == 2
    assert plan.payload["observed_items"] == 1
    assert plan.payload["generated_items"] == 1
    assert plan.payload["verified_items"] == 1
    assert plan.verified is False
    assert end.payload == {"success": True}
