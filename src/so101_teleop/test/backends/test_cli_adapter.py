from pathlib import Path
import subprocess
from unittest.mock import Mock

from so101_teleop.backends.cli_adapter import CliBackendAdapter, build_scene_args
from so101_teleop.backends.protocol import BackendOperation
from so101_teleop.backends.protocol import ResetRequest, SceneRequest, WorkflowRequest
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


def test_adapter_never_uses_shell_or_request_selected_program(tmp_path):
    adapter, runner = adapter_for(tmp_path)

    adapter.run_workflow(workflow_request("run"))

    argv = runner.call_args.args[0]
    assert runner.call_args.kwargs["shell"] is False
    assert argv[0].endswith("/lib/so101_gazebo_demo_py/pick_place_state_machine")
    assert argv[1:] == [
        "--live-runtime", "--mode", "execute", "--checkpoint",
        "/tmp/checkpoint.json", "--session-id", "session-a",
    ]


def test_workflow_operation_mapping_is_fixed(tmp_path):
    adapter, runner = adapter_for(tmp_path)

    adapter.run_workflow(workflow_request("start"))
    assert runner.call_args.args[0][-1] == "--step"
    adapter.run_workflow(workflow_request("resume"))
    assert runner.call_args.args[0][-2:] == ["--resume", "true"]
    adapter.run_workflow(workflow_request("force-continue"))
    assert runner.call_args.args[0][-3:] == ["--resume", "true", "--force-continue"]


def test_scene_styles_do_not_drift_between_owners(tmp_path):
    cpp, cpp_runner = adapter_for(tmp_path / "cpp", "gazebo_cpp")
    py_profile = load_backend_profile("gazebo_py", PACKAGE)

    cpp.scene_operation(SceneRequest("observe", "session-a"))

    assert cpp_runner.call_args.args[0][-1:] == ["observe"]
    assert build_scene_args(
        py_profile.operations[BackendOperation.SCENE],
        SceneRequest("observe", "session-a"),
    ) == ["--operation", "observe"]


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


def test_reset_accepts_owner_exit_success_without_stdout(tmp_path):
    completed = subprocess.CompletedProcess(["owner"], 0, "", "")
    adapter, runner = adapter_for(tmp_path, "gazebo_cpp", completed)

    result = adapter.reset_world(ResetRequest("session-a"))

    assert result.ok is True
    assert result.result == {"status": "SUCCEEDED"}
    assert runner.call_args.args[0][-1].endswith("reset_so101_world")


def test_unsupported_operation_does_not_call_subprocess(tmp_path):
    adapter, runner = adapter_for(tmp_path, "mujoco_py")

    workflow = adapter.run_workflow(workflow_request("run"))
    reset = adapter.reset_world(ResetRequest("session-a"))
    scene = adapter.scene_operation(SceneRequest("observe", "session-a"))

    assert {workflow.error.code, reset.error.code, scene.error.code} == {
        "BACKEND_CAPABILITY_UNAVAILABLE"
    }
    runner.assert_not_called()
