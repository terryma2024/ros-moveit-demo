from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from launch import LaunchContext
from launch.actions import DeclareLaunchArgument, ExecuteProcess, OpaqueFunction
from launch.utilities import perform_substitutions
from so101_demo.runtime import launch_composition
from so101_demo.runtime.provenance import InstalledExecutionIdentity


PACKAGE_ROOT = Path(__file__).parents[1]
LAUNCH_PATH = PACKAGE_ROOT / "launch/so101_mujoco_text_pick_agent_e2e.launch.py"


def _declared(description):
    return {
        action.name: action
        for action in description.entities
        if isinstance(action, DeclareLaunchArgument)
    }


def _default(argument):
    return perform_substitutions(LaunchContext(), argument.default_value)


def _materialize(monkeypatch, tmp_path: Path, **overrides):
    monkeypatch.setattr(
        launch_composition,
        "resolve_installed_execution_identity",
        lambda: InstalledExecutionIdentity("a" * 40, "/tmp/e2e-install"),
    )
    description = launch_composition.build_text_pick_agent_e2e_launch_description()
    context = LaunchContext()
    for name, argument in _declared(description).items():
        if argument.default_value is not None:
            context.launch_configurations[name] = _default(argument)
    context.launch_configurations.update(
        {
            "instruction": "Pick the plastic cup.",
            "run_mode": "execute",
            "execute": "true",
            "skip_confirmation": "true",
            "session_id": "e2e-session-001",
            "evidence_file": str(tmp_path / "run" / "e2e-result.json"),
            "perception_backend": "color_geometry",
            "perception_runtime": "host",
            **{name: str(value) for name, value in overrides.items()},
        }
    )
    opaque = next(x for x in description.entities if isinstance(x, OpaqueFunction))
    return context, opaque.execute(context)


def _record(workflow_id, sequence, component, event, *, status="OK", failure=None, payload=None):
    return (
        "SO101_EVENT "
        + json.dumps(
            {
                "schema_version": 1,
                "workflow_id": workflow_id,
                "sequence": sequence,
                "component": component,
                "event": event,
                "status": status,
                "timestamp_ns": 100,
                "failure_code": failure,
                "payload": payload or {},
            },
            separators=(",", ":"),
        )
        + "\n"
    ).encode()


def test_public_contract_and_thin_wrapper() -> None:
    description = launch_composition.build_text_pick_agent_e2e_launch_description()
    declared = _declared(description)
    assert {
        "instruction", "run_mode", "execute", "skip_confirmation", "headless",
        "sensor_rendering", "session_id", "evidence_file", "readiness_timeout_s",
        "mujoco_scene", "mujoco_initial_keyframe", "perception_startup_timeout_s",
        "cup_pose_timeout_s", "perception_backend", "perception_weights",
        "perception_weights_sha256", "perception_model_root",
        "perception_model_manifest_sha256", "perception_device",
        "perception_allow_cpu_fallback", "perception_runtime",
        "perception_container_image", "perception_source_root",
        "grounding_box_threshold", "grounding_text_threshold",
        "grounding_duplicate_iou", "grounding_max_candidates",
        "sam_mask_quality_threshold", "sam_min_mask_pixels",
        "sam_max_mask_area_ratio",
    } <= set(declared)
    assert _default(declared["perception_backend"]) == "yolo_seg"
    assert _default(declared["run_mode"]) == "dry_run"
    assert _default(declared["execute"]) == "false"
    assert _default(declared["skip_confirmation"]) == "false"
    assert "/e2e-result.json" in _default(declared["evidence_file"])
    assert LAUNCH_PATH.is_file()
    source = LAUNCH_PATH.read_text(encoding="utf-8")
    assert "DeclareLaunchArgument" not in source
    spec = importlib.util.spec_from_file_location("e2e_launch", LAUNCH_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert module.generate_launch_description() is not None


@pytest.mark.parametrize(
    "override, pattern",
    [
        ({"instruction": ""}, "instruction"),
        ({"run_mode": "dry_run"}, "run_mode=execute"),
        ({"execute": "false"}, "execute:=true"),
        ({"skip_confirmation": "false"}, "skip_confirmation:=true"),
        ({"sensor_rendering": "false"}, "sensor_rendering=true"),
        ({"perception_weights": "/missing.pt"}, "matching perception backend"),
    ],
)
def test_invalid_preflight_creates_no_stack_or_evidence(monkeypatch, tmp_path, override, pattern):
    calls = []
    monkeypatch.setattr(launch_composition, "_mujoco_stack_actions", lambda *a, **k: calls.append(1))
    with pytest.raises(RuntimeError, match=pattern):
        _materialize(monkeypatch, tmp_path, **override)
    assert calls == []
    assert not (tmp_path / "run").exists()


def test_existing_or_nonexclusive_evidence_root_is_rejected(monkeypatch, tmp_path):
    root = tmp_path / "run"
    root.mkdir()
    with pytest.raises(RuntimeError, match="already exists"):
        _materialize(monkeypatch, tmp_path)


def test_valid_preflight_builds_stack_only_and_exclusive_layout(monkeypatch, tmp_path):
    _context, actions = _materialize(monkeypatch, tmp_path)
    root = tmp_path / "run"
    assert {p.name for p in root.iterdir()} == {"perception", "dynamic", "acceptance"}
    assert not any(
        isinstance(action, ExecuteProcess)
        and not getattr(action, "node_package", None)
        and "text_pick_agent" in repr(action.cmd)
        for action in actions
    )
    assert any(type(action).__name__ == "RegisterEventHandler" for action in actions)


def _supervisor(tmp_path: Path, backend="yolo_seg"):
    text = ExecuteProcess(cmd=["text"])
    perception = ExecuteProcess(cmd=["perception"])
    validator = ExecuteProcess(cmd=["validator"])
    supervisor = launch_composition.E2ESupervisor(
        workflow_id="workflow-1",
        request_id="request-1",
        session_id="session-1",
        backend=backend,
        source_commit="a" * 40,
        installed_prefix="/tmp/install",
        run_root=tmp_path,
        result_file=tmp_path / "e2e-result.json",
        text_agent_action=text,
        perception_action=perception,
        validator_action=validator,
        clock_ns=lambda: 100,
    )
    return supervisor, text, perception, validator


def test_supervisor_drives_children_only_from_strict_events(tmp_path):
    supervisor, text, perception, validator = _supervisor(tmp_path)
    assert supervisor.on_scene_exit(0) == [text]
    assert supervisor.on_stdout(text, _record("workflow-1", 1, "text_agent", "DISPATCH_PREVIEW", payload={"request_id": "request-1"})) == []
    assert supervisor.on_stdout(
        text,
        _record(
            "workflow-1",
            1,
            "dynamic_runtime",
            "RUNTIME_STARTED",
            payload={
                "request_id": "request-1",
                "session_id": "session-1",
                "reset_epoch": 0,
            },
        ),
    )
    actions = supervisor.on_stdout(text, _record("workflow-1", 2, "dynamic_runtime", "RUNTIME_READY", payload={"request_id": "request-1", "session_id": "session-1", "reset_epoch": 0}))
    assert actions[0] is perception
    assert supervisor.on_stdout(perception, _record("workflow-1", 1, "perception", "PERCEPTION_READY"))
    assert supervisor.on_stdout(perception, _record("workflow-1", 2, "perception", "TARGET_SELECTED", payload={"target_id": "cup", "class_name": "plastic_cup"})) == []
    assert supervisor.on_stdout(perception, _record("workflow-1", 3, "perception", "CUP_POSE_PUBLISHED", payload={"source_stamp_ns": 1, "frame_id": "world"})) == []
    actions = supervisor.on_stdout(text, _record("workflow-1", 3, "dynamic_runtime", "RUNTIME_COMPLETED", payload={"manifest_path": str(tmp_path / "dynamic/dynamic-execute-manifest.json"), "runtime_exit_code": 0}))
    assert actions[0] is validator
    cleanup = supervisor.on_stdout(validator, _record("workflow-1", 1, "e2e_validator", "E2E_ACCEPTED", payload={"result_path": str(tmp_path / "acceptance/result.json")}))
    assert cleanup
    assert supervisor.shutting_down is True
    trace = (tmp_path / "workflow-events.ndjson").read_text(encoding="utf-8")
    assert len(trace.splitlines()) == 9


def test_first_failure_is_preserved_and_protocol_error_is_secondary(tmp_path):
    supervisor, text, perception, _validator = _supervisor(tmp_path)
    supervisor.on_scene_exit(0)
    supervisor.on_stdout(text, _record("workflow-1", 1, "text_agent", "DISPATCH_PREVIEW", payload={"request_id": "request-1"}))
    supervisor.on_stdout(text, _record("workflow-1", 1, "dynamic_runtime", "RUNTIME_STARTED", payload={"request_id": "request-1", "session_id": "session-1", "reset_epoch": 0}))
    supervisor.on_stdout(text, _record("workflow-1", 2, "dynamic_runtime", "RUNTIME_READY", payload={"request_id": "request-1", "session_id": "session-1", "reset_epoch": 0}))
    supervisor.on_stdout(perception, _record("workflow-1", 1, "perception", "PERCEPTION_FAILED", status="ERROR", failure="TARGET_AMBIGUOUS"))
    supervisor.on_exit(text, 7)
    assert supervisor.primary_failure["code"] == "TARGET_AMBIGUOUS"
    assert supervisor.secondary_failures


def test_required_child_exit_zero_before_acceptance_fails(tmp_path):
    supervisor, *_ = _supervisor(tmp_path)
    required = ExecuteProcess(cmd=["mujoco"])
    supervisor.register_owned(required, label="MuJoCo runtime", required_long_lived=True, started=True)
    actions = supervisor.on_exit(required, 0)
    assert actions
    assert supervisor.primary_failure["code"] == "REQUIRED_PROCESS_EXITED"


def test_nonzero_exit_without_terminal_event_fails_closed(tmp_path):
    supervisor, text, *_ = _supervisor(tmp_path)
    supervisor.on_scene_exit(0)
    actions = supervisor.on_exit(text, 9)
    assert actions
    assert supervisor.primary_failure["code"] == "CHILD_EXITED_WITHOUT_TERMINAL_EVENT"
    assert supervisor.primary_failure["exit_code"] == 9


def test_stale_timeout_generation_cannot_fail_new_phase(tmp_path):
    supervisor, *_ = _supervisor(tmp_path)
    supervisor.arm_timeout("STACK_READINESS", 1.0)
    supervisor.arm_timeout("STACK_READINESS", 1.0)
    assert supervisor.on_timeout("STACK_READINESS", 1) == []
    assert supervisor.primary_failure is None


def test_acceptance_result_is_written_only_after_owned_cleanup(tmp_path):
    acceptance = tmp_path / "acceptance"
    acceptance.mkdir()
    (acceptance / "result.json").write_text(
        json.dumps(
            {
                "accepted": True,
                "failures": [],
                "physical_outcome": {"stable": True},
                "planning_scene_outcome": {"pose_matches_mujoco": True},
            }
        ),
        encoding="utf-8",
    )
    supervisor, text, perception, validator = _supervisor(tmp_path)
    supervisor.on_scene_exit(0)
    supervisor.on_stdout(text, _record("workflow-1", 1, "text_agent", "DISPATCH_PREVIEW", payload={"request_id": "request-1"}))
    supervisor.on_stdout(text, _record("workflow-1", 1, "dynamic_runtime", "RUNTIME_STARTED", payload={"request_id": "request-1", "session_id": "session-1", "reset_epoch": 0}))
    supervisor.on_stdout(text, _record("workflow-1", 2, "dynamic_runtime", "RUNTIME_READY", payload={"request_id": "request-1", "session_id": "session-1", "reset_epoch": 0}))
    supervisor.on_stdout(perception, _record("workflow-1", 1, "perception", "PERCEPTION_READY"))
    supervisor.on_stdout(perception, _record("workflow-1", 2, "perception", "TARGET_SELECTED", payload={"target_id": "cup", "class_name": "plastic_cup"}))
    supervisor.on_stdout(perception, _record("workflow-1", 3, "perception", "CUP_POSE_PUBLISHED", payload={"source_stamp_ns": 1, "frame_id": "world"}))
    supervisor.on_stdout(text, _record("workflow-1", 3, "dynamic_runtime", "RUNTIME_COMPLETED", payload={"manifest_path": str(tmp_path / "dynamic/dynamic-execute-manifest.json"), "runtime_exit_code": 0}))
    supervisor.on_stdout(validator, _record("workflow-1", 1, "e2e_validator", "E2E_ACCEPTED", payload={"result_path": str(acceptance / "result.json")}))
    assert not (tmp_path / "e2e-result.json").exists()
    supervisor.on_exit(text, 0)
    supervisor.on_exit(perception, 0)
    final_actions = supervisor.on_exit(validator, 0)
    assert final_actions
    result = json.loads((tmp_path / "e2e-result.json").read_text(encoding="utf-8"))
    assert result["machine_accepted"] is True
    assert result["owned_process_cleanup"]["complete"] is True
    assert result["physical_outcome"] == {"stable": True}
