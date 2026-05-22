from agi_runtime.context_unrolling import (
    ContextPrimitive,
    ContextUnrollingController,
    ContextWorkspace,
    PrimitiveResult,
    WorkspaceItem,
)


def test_workspace_records_provenance_confidence_and_verification_state():
    workspace = ContextWorkspace(goal="Fix checkout bug")

    item = workspace.add(
        item_type="evidence",
        content={"first_failure": "checkout_total_mismatch"},
        source="pytest_log",
        confidence=0.92,
        observed=True,
        verified=True,
        relation="root-cause evidence",
    )

    assert item.id.startswith("ctx_")
    assert item.type == "evidence"
    assert item.source == "pytest_log"
    assert item.confidence == 0.92
    assert item.observed is True
    assert item.verified is True
    assert workspace.by_type("evidence") == [item]


def test_controller_selects_task_relevant_primitives_without_unrolling_everything():
    controller = ContextUnrollingController(
        primitives=[
            ContextPrimitive(name="extract_constraints", produces="text_constraints", task_types={"coding", "business"}),
            ContextPrimitive(name="inspect_failing_tests", produces="test_evidence", task_types={"coding"}),
            ContextPrimitive(name="ocr", produces="visual_text", task_types={"browser", "document"}),
            ContextPrimitive(name="estimate_depth", produces="geometry", task_types={"spatial", "robotics"}),
        ],
        max_primitives=2,
    )

    selected = controller.select(task_type="coding", workspace=ContextWorkspace(goal="Fix checkout bug"))

    assert [primitive.name for primitive in selected] == ["extract_constraints", "inspect_failing_tests"]


def test_generated_context_requires_verification_before_final_action():
    workspace = ContextWorkspace(goal="Click the correct checkout button")
    workspace.add(
        item_type="ui_text",
        content="Button label: Submit order",
        source="ocr",
        confidence=0.87,
        observed=True,
        verified=True,
    )
    workspace.add(
        item_type="predicted_action_result",
        content="Clicking Submit order will charge the card",
        source="action_predictor",
        confidence=0.61,
        observed=False,
        verified=False,
    )

    assert workspace.has_unverified_generated_context() is True
    assert workspace.ready_for_action(risk="high") is False
    assert workspace.ready_for_action(risk="low") is True


def test_primitive_result_writes_typed_context_into_workspace():
    workspace = ContextWorkspace(goal="Understand uploaded paper")
    result = PrimitiveResult(
        item_type="paper_claims",
        content=["Build a typed workspace before final action"],
        confidence=0.8,
        observed=False,
        verified=False,
        relation="implementation insight",
    )

    item = workspace.record_result(source="claim_extractor", result=result)

    assert isinstance(item, WorkspaceItem)
    assert item.type == "paper_claims"
    assert item.source == "claim_extractor"
    assert item.content == ["Build a typed workspace before final action"]
    assert item.observed is False
    assert item.verified is False


def test_extract_goal_artifact_references_records_public_safe_file_and_test_mentions():
    from agi_runtime.context_unrolling import extract_goal_artifact_references

    result = extract_goal_artifact_references(
        "Fix tests/test_cli_contract.py::TestCLIContract::test_context_plan and src/agi_runtime/cli.py"
    )

    assert result.item_type == "artifact_references"
    assert result.observed is True
    assert result.verified is True
    assert result.content == {
        "files": ["src/agi_runtime/cli.py", "tests/test_cli_contract.py"],
        "tests": ["tests/test_cli_contract.py::TestCLIContract::test_context_plan"],
    }


def test_workspace_summary_omits_content_by_default_and_can_include_it():
    workspace = ContextWorkspace(goal="Audit runtime evidence")
    workspace.add(
        item_type="sensitive_observation",
        content={"path": "private/runtime/path.txt"},
        source="tool:file_read",
        confidence=1.0,
        observed=True,
        verified=True,
    )

    default_summary = workspace.summarize()
    content_summary = workspace.summarize(include_content=True)

    assert "content" not in default_summary["items"][0]
    assert content_summary["items"][0]["content"] == {"path": "private/runtime/path.txt"}
