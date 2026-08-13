import subprocess
from pathlib import Path
from unittest.mock import Mock

from so101_teleop.backends.cli_adapter import CliBackendAdapter
from so101_teleop.backends.protocol import (
    CameraPresetRequest,
    ResetRequest,
    SceneRequest,
    WorkflowRequest,
)
from so101_teleop.backends.registry import load_backend_profile

PACKAGE = Path(__file__).resolve().parents[2]


def executable_prefix(tmp_path, package, executable):
    path = tmp_path / "lib" / package / executable
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n")
    path.chmod(0o755)
    return path


def adapter_for(tmp_path, backend="gazebo_py", completed=None):
    profile = load_backend_profile(backend, PACKAGE)
    for spec in (profile.probe, *profile.operations.values()):
        executable_prefix(tmp_path, spec.package, spec.executable)
    runner = Mock(return_value=completed or subprocess.CompletedProcess(
        ["owner"], 0, "status=DONE\ntrace=BOOTSTRAP -> DONE\n", ""
    ))
    adapter = CliBackendAdapter(
        profile,
        package_prefix_resolver=lambda _package: str(tmp_path),
        run_process=runner,
        diagnostics_root=tmp_path / "diagnostics",
    )
    return adapter, runner


def workflow_request(operation="run"):
    return WorkflowRequest(
        operation=operation,
        session_id="session-a",
        checkpoint=Path("/tmp/checkpoint.json"),
    )


def test_probe_normalizes_missing_package(tmp_path):
    profile = load_backend_profile("gazebo_cpp", PACKAGE)
    runner = Mock()

    def missing_package(_package):
        raise RuntimeError("owner package is absent")

    adapter = CliBackendAdapter(
        profile,
        package_prefix_resolver=missing_package,
        run_process=runner,
        diagnostics_root=tmp_path,
    )
    result = adapter.probe()

    assert result.ok is False
    assert result.error.code == "BACKEND_PACKAGE_NOT_FOUND"
    runner.assert_not_called()


def test_gazebo_python_probe_uses_canonical_owner(tmp_path):
    adapter, runner = adapter_for(tmp_path)

    result = adapter.probe()

    assert result.ok is True
    assert result.owner_package == "so101_demo_py"
    assert result.owner_executable == "pick_place"
    runner.assert_not_called()


def test_workflow_operation_mapping_is_fixed(tmp_path):
    adapter, runner = adapter_for(tmp_path, "gazebo_cpp")

    adapter.run_workflow(workflow_request("start"))
    assert runner.call_args.args[0][-1] == "--step"
    adapter.run_workflow(workflow_request("resume"))
    assert runner.call_args.args[0][-2:] == ["--resume", "true"]
    adapter.run_workflow(workflow_request("force-continue"))
    assert runner.call_args.args[0][-3:] == ["--resume", "true", "--force-continue"]


def test_cpp_scene_style_is_positional(tmp_path):
    cpp, cpp_runner = adapter_for(tmp_path / "cpp", "gazebo_cpp")

    cpp.scene_operation(SceneRequest("observe", "session-a"))

    assert cpp_runner.call_args.args[0][-1:] == ["observe"]


def test_gazebo_python_run_uses_canonical_execute_and_other_operations_fail_closed(
    tmp_path,
):
    adapter, runner = adapter_for(tmp_path)

    run = adapter.run_workflow(workflow_request("run"))
    argv = runner.call_args.args[0]
    assert run.ok is True
    assert runner.call_args.kwargs["shell"] is False
    assert argv[0].endswith("/lib/so101_demo_py/gazebo_execute")
    assert argv[1:] == [
        "--mode", "execute", "--checkpoint", "/tmp/checkpoint.json",
        "--session-id", "session-a",
    ]

    runner.reset_mock()
    results = (
        adapter.run_workflow(workflow_request("start")),
        adapter.reset_world(ResetRequest("session-a")),
        adapter.scene_operation(SceneRequest("observe", "session-a")),
        adapter.apply_camera_preset(CameraPresetRequest("overview", "session-a")),
    )

    assert {result.error.code for result in results} == {
        "BACKEND_CAPABILITY_UNAVAILABLE"
    }
    runner.assert_not_called()


def test_nonzero_owner_result_preserves_sanitized_failure_code(tmp_path):
    completed = subprocess.CompletedProcess(
        ["owner"], 7, "", "failure_code=Q6_NOT_STATIONARY\nsecret=no"
    )
    adapter, _runner = adapter_for(tmp_path, "gazebo_cpp", completed)

    result = adapter.run_workflow(workflow_request("run"))

    assert result.ok is False
    assert result.error.code == "BACKEND_OPERATION_FAILED"
    assert result.error.owner_failure_code == "Q6_NOT_STATIONARY"
    diagnostic = tmp_path / "diagnostics" / "session-a" / "last-workflow_run.log"
    assert diagnostic.is_file()
    assert "environment" not in diagnostic.read_text().casefold()


def test_unparseable_owner_output_returns_backend_output_invalid(tmp_path):
    completed = subprocess.CompletedProcess(["owner"], 0, "unstructured", "")
    adapter, _runner = adapter_for(tmp_path, "gazebo_cpp", completed)

    result = adapter.run_workflow(workflow_request("run"))

    assert result.ok is False
    assert result.error.code == "BACKEND_OUTPUT_INVALID"


def test_cpp_owner_trace_preserves_every_state(tmp_path):
    completed = subprocess.CompletedProcess(
        ["owner"], 0,
        "status=DONE\ntrace=BOOTSTRAP -> PREPARE_OPEN_GRIPPER -> DONE\n", "",
    )
    adapter, _runner = adapter_for(tmp_path, "gazebo_cpp", completed)

    result = adapter.run_workflow(workflow_request("run"))

    assert result.ok is True
    assert result.result["trace"] == (
        "BOOTSTRAP -> PREPARE_OPEN_GRIPPER -> DONE"
    )


def test_mujoco_owner_state_trace_is_normalized_to_backend_trace(tmp_path):
    completed = subprocess.CompletedProcess(
        ["owner"], 0,
        "status=SUCCEEDED\nstate_trace=IDLE,PREPARE_OPEN_GRIPPER,DONE\n", "",
    )
    adapter, _runner = adapter_for(tmp_path, "mujoco_py", completed)

    result = adapter.run_workflow(workflow_request("run"))

    assert result.ok is True
    assert result.result["trace"] == "IDLE -> PREPARE_OPEN_GRIPPER -> DONE"


def test_reset_accepts_owner_exit_success_without_stdout(tmp_path):
    completed = subprocess.CompletedProcess(["owner"], 0, "", "")
    adapter, runner = adapter_for(tmp_path, "gazebo_cpp", completed)

    result = adapter.reset_world(ResetRequest("session-a"))

    assert result.ok is True
    assert result.result == {"status": "SUCCEEDED"}
    assert runner.call_args.args[0][-1].endswith("reset_so101_world")


def test_mujoco_routes_workflow_reset_session_and_camera_to_owner(tmp_path):
    adapter, runner = adapter_for(tmp_path, "mujoco_py")

    workflow = adapter.run_workflow(workflow_request("run"))
    assert workflow.ok is True
    assert runner.call_args.args[0][0].endswith("/teleop_workflow")
    reset = adapter.reset_world(ResetRequest("session-a"))
    assert reset.ok is True
    assert runner.call_args.args[0][-2:] == ["--session-id", "session-a"]
    camera = adapter.apply_camera_preset(
        CameraPresetRequest("table_corner_nw", "session-a")
    )
    assert camera.ok is True
    assert runner.call_args.args[0][0].endswith("/camera_preset")
    assert runner.call_args.args[0][-1] == "table_corner_nw"


def test_mujoco_unsupported_operations_do_not_call_subprocess(tmp_path):
    adapter, runner = adapter_for(tmp_path, "mujoco_py")

    start = adapter.run_workflow(workflow_request("start"))
    scene = adapter.scene_operation(SceneRequest("observe", "session-a"))

    assert {start.error.code, scene.error.code} == {
        "BACKEND_CAPABILITY_UNAVAILABLE"
    }
    runner.assert_not_called()


def test_unknown_camera_preset_fails_before_subprocess(tmp_path):
    adapter, runner = adapter_for(tmp_path, "mujoco_py")

    result = adapter.apply_camera_preset(CameraPresetRequest("unknown"))

    assert result.ok is False
    assert result.error.code == "CAMERA_PRESET_NOT_FOUND"
    runner.assert_not_called()
