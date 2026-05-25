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


def test_verify_goal_artifact_references_records_existence_without_absolute_paths(tmp_path):
    from agi_runtime.context_unrolling import verify_goal_artifact_references

    existing = tmp_path / "src" / "agi_runtime" / "cli.py"
    existing.parent.mkdir(parents=True)
    existing.write_text("print('hello')\n", encoding="utf-8")

    result = verify_goal_artifact_references(
        "Check src/agi_runtime/cli.py and tests/missing_test.py::test_missing",
        root=tmp_path,
    )

    assert result.item_type == "artifact_existence"
    assert result.observed is True
    assert result.verified is True
    assert result.content == {
        "present_files": ["src/agi_runtime/cli.py"],
        "missing_files": ["tests/missing_test.py"],
        "present_tests": [],
        "missing_tests": ["tests/missing_test.py::test_missing"],
    }
    assert str(tmp_path) not in repr(result.content)


def test_verify_goal_artifact_references_ignores_absolute_and_parent_escape_paths(tmp_path):
    from agi_runtime.context_unrolling import verify_goal_artifact_references

    result = verify_goal_artifact_references(
        "Do not capture /home/user/private.py or ../outside.py but do capture docs/context-unrolling.md",
        root=tmp_path,
    )

    assert result.content["present_files"] == []
    assert result.content["missing_files"] == ["docs/context-unrolling.md"]
    assert "/home/user/private.py" not in repr(result.content)
    assert "../outside.py" not in repr(result.content)


def test_summarize_goal_artifact_metadata_records_counts_without_content(tmp_path):
    from agi_runtime.context_unrolling import summarize_goal_artifact_metadata

    existing = tmp_path / "src" / "agi_runtime" / "cli.py"
    existing.parent.mkdir(parents=True)
    existing.write_text("first line\nsecond line\n", encoding="utf-8")

    result = summarize_goal_artifact_metadata(
        "Inspect src/agi_runtime/cli.py and tests/missing_test.py::test_missing",
        root=tmp_path,
    )

    assert result.item_type == "artifact_metadata"
    assert result.observed is True
    assert result.verified is True
    assert result.content == {
        "files": [
            {
                "path": "src/agi_runtime/cli.py",
                "bytes": len("first line\nsecond line\n".encode("utf-8")),
                "lines": 2,
                "kind": "file",
            }
        ],
        "missing_files": ["tests/missing_test.py"],
        "unreadable_files": [],
    }
    assert "first line" not in repr(result.content)
    assert str(tmp_path) not in repr(result.content)


def test_summarize_goal_artifact_metadata_degrades_when_file_read_fails(tmp_path, monkeypatch):
    from pathlib import Path

    from agi_runtime.context_unrolling import summarize_goal_artifact_metadata

    existing = tmp_path / "src" / "agi_runtime" / "cli.py"
    existing.parent.mkdir(parents=True)
    existing.write_text("first line\n", encoding="utf-8")
    original_read_bytes = Path.read_bytes

    def flaky_read_bytes(path):
        if path == existing:
            raise OSError("permission denied")
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", flaky_read_bytes)

    result = summarize_goal_artifact_metadata("Inspect src/agi_runtime/cli.py", root=tmp_path)

    assert result.content == {
        "files": [],
        "missing_files": [],
        "unreadable_files": ["src/agi_runtime/cli.py"],
    }


def test_collect_goal_pytest_references_records_collect_status_without_output_content(tmp_path):
    from agi_runtime.context_unrolling import collect_goal_pytest_references

    test_file = tmp_path / "tests" / "test_sample.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text(
        "def test_ok():\n"
        "    assert True\n",
        encoding="utf-8",
    )

    result = collect_goal_pytest_references(
        "Collect tests/test_sample.py::test_ok and tests/missing_test.py::test_missing",
        root=tmp_path,
    )

    assert result.item_type == "pytest_collection"
    assert result.observed is True
    assert result.verified is True
    assert result.content == {
        "tests": [
            {
                "reference": "tests/missing_test.py::test_missing",
                "status": "missing_file",
                "collected_count": 0,
            },
            {
                "reference": "tests/test_sample.py::test_ok",
                "status": "collected",
                "collected_count": 1,
            },
        ],
        "skipped": [],
    }
    assert "assert True" not in repr(result.content)
    assert str(tmp_path) not in repr(result.content)


def test_collect_goal_pytest_references_counts_parameterized_nodes_statically(tmp_path):
    from agi_runtime.context_unrolling import collect_goal_pytest_references

    test_file = tmp_path / "tests" / "test_params.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text(
        "import pytest\n\n"
        "@pytest.mark.parametrize('value', [1, 2, 3])\n"
        "def test_value(value):\n"
        "    assert value\n",
        encoding="utf-8",
    )

    result = collect_goal_pytest_references("Collect tests/test_params.py::test_value", root=tmp_path)

    assert result.content["tests"] == [
        {
            "reference": "tests/test_params.py::test_value",
            "status": "collected",
            "collected_count": 3,
        }
    ]
    assert "assert value" not in repr(result.content)


def test_collect_goal_pytest_references_does_not_mark_non_tests_collected(tmp_path):
    from agi_runtime.context_unrolling import collect_goal_pytest_references

    test_file = tmp_path / "tests" / "test_helpers.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text(
        "def helper():\n"
        "    return True\n\n"
        "class HelperClass:\n"
        "    def test_method_name_but_not_test_class(self):\n"
        "        return True\n\n"
        "class TestContainer:\n"
        "    def helper_method(self):\n"
        "        return True\n",
        encoding="utf-8",
    )

    result = collect_goal_pytest_references(
        "Collect tests/test_helpers.py::helper "
        "tests/test_helpers.py::HelperClass::test_method_name_but_not_test_class "
        "tests/test_helpers.py::TestContainer::helper_method",
        root=tmp_path,
    )

    assert result.content["tests"] == [
        {"reference": "tests/test_helpers.py::HelperClass::test_method_name_but_not_test_class", "status": "not_collected", "collected_count": 0},
        {"reference": "tests/test_helpers.py::TestContainer::helper_method", "status": "not_collected", "collected_count": 0},
        {"reference": "tests/test_helpers.py::helper", "status": "not_collected", "collected_count": 0},
    ]


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
