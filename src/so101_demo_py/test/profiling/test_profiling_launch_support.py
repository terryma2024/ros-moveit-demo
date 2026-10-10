import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from launch import LaunchDescription, LaunchService
from launch.action import Action
from launch.actions import OpaqueFunction

from so101_demo.profiling.launch_support import resolve_launch_profiling
from so101_demo.profiling.system_trace import SystemTraceResult, build_system_trace


class _ExecuteFailingTrace(Action):
    trace_directory = None

    def __init__(self, **_kwargs) -> None:
        super().__init__()

    def execute(self, _context):
        raise RuntimeError("LTTng setup failed at action execution")


def test_off_launch_profiling_creates_nothing(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    run_root.mkdir()

    session = resolve_launch_profiling(
        mode_value="off",
        output_root_value="",
        require_system_trace_value="false",
        run_root=run_root,
        session_id="session-1",
        source_commit="a" * 40,
        installed_prefix="/candidate/install",
    )

    assert session is None
    assert list(run_root.iterdir()) == []


def test_exported_launch_boundary_rejects_unsafe_session_id_before_artifacts(
    tmp_path: Path,
) -> None:
    run_root = tmp_path / "run"
    run_root.mkdir()

    with pytest.raises(RuntimeError, match="session_id"):
        resolve_launch_profiling(
            mode_value="summary",
            output_root_value="",
            require_system_trace_value="false",
            run_root=run_root,
            session_id="../escape",
            source_commit="a" * 40,
            installed_prefix="/candidate/install",
        )

    assert list(run_root.iterdir()) == []


def test_enabled_launch_profiling_uses_run_root_and_writes_launch_stream(
    tmp_path: Path,
) -> None:
    run_root = tmp_path / "run"
    run_root.mkdir()

    session = resolve_launch_profiling(
        mode_value="trace",
        output_root_value="",
        require_system_trace_value="false",
        run_root=run_root,
        session_id="session-1",
        source_commit="a" * 40,
        installed_prefix="/candidate/install",
    )

    assert session is not None
    assert session.profiling_root == run_root / "profiling"
    session.record_scene_exit(0)
    session.record_workflow_exit(0)
    session.record_perception_exit(-15)

    manifest = json.loads((session.profiling_root / "manifest.json").read_text())
    summary = json.loads((session.profiling_root / "summary.json").read_text())
    assert manifest["complete"] is True
    assert manifest["artifacts"]["trace"] == "trace.json"
    assert [span["name"] for span in summary["spans"]] == [
        "launch.total",
        "launch.stack_startup",
        "launch.scene_setup",
    ]


def test_launch_finalizer_keeps_configured_session_when_stale_stream_sorts_first(
    tmp_path: Path,
) -> None:
    run_root = tmp_path / "run"
    run_root.mkdir()
    session = resolve_launch_profiling(
        mode_value="summary",
        output_root_value="",
        require_system_trace_value="false",
        run_root=run_root,
        session_id="session-1",
        source_commit="a" * 40,
        installed_prefix="/candidate/install",
    )
    assert session is not None
    launch_stream = next((session.profiling_root / "processes").glob("launch*.jsonl"))
    stale_events = [
        json.loads(line)
        for line in launch_stream.read_text(encoding="utf-8").splitlines()
    ]
    for event in stale_events:
        event["session_id"] = "stale-session"
    stale_stream = session.profiling_root / "processes/aaa-stale.events.jsonl"
    stale_stream.write_text(
        "".join(json.dumps(event) + "\n" for event in stale_events),
        encoding="utf-8",
    )

    session.finalize_for_shutdown(reason="test complete")

    manifest = json.loads((session.profiling_root / "manifest.json").read_text())
    assert manifest["session_id"] == "session-1"
    assert manifest["mismatched_sessions"] == ["aaa-stale.events.jsonl"]


def test_ready_linux_backend_exposes_prefix_and_manifest_metadata(
    tmp_path: Path,
) -> None:
    run_root = tmp_path / "run"
    run_root.mkdir()
    trace_action = object()

    session = resolve_launch_profiling(
        mode_value="trace",
        output_root_value="",
        require_system_trace_value="true",
        run_root=run_root,
        session_id="session-1",
        source_commit="a" * 40,
        installed_prefix="/candidate/install",
        platform_name="linux",
        system_trace_builder=lambda **_kwargs: SystemTraceResult(
            "ready",
            trace_action,
            "ros2_tracing",
            run_root / "profiling/ros2-tracing/so101-session-1",
        ),
    )

    assert session is not None
    assert session.prefix_actions == (trace_action,)
    session.finalize_for_shutdown(reason="test complete")
    manifest = json.loads((session.profiling_root / "manifest.json").read_text())
    assert manifest["backend"] == {
        "status": "ready",
        "name": "ros2_tracing",
        "output": "ros2-tracing/so101-session-1",
        "error": None,
    }


def test_unavailable_linux_backend_degrades_with_sanitized_warning(
    tmp_path: Path,
) -> None:
    run_root = tmp_path / "run"
    run_root.mkdir()

    session = resolve_launch_profiling(
        mode_value="trace",
        output_root_value="",
        require_system_trace_value="false",
        run_root=run_root,
        session_id="session-1",
        source_commit="a" * 40,
        installed_prefix="/candidate/install",
        platform_name="linux",
        system_trace_builder=lambda **_kwargs: SystemTraceResult(
            "unavailable",
            None,
            "ros2_tracing",
            None,
            "ImportError",
        ),
    )

    assert session is not None
    assert session.prefix_actions == ()
    assert session.warnings == ("ros2_tracing unavailable (ImportError)",)
    session.finalize_for_shutdown(reason="test complete")
    manifest = json.loads((session.profiling_root / "manifest.json").read_text())
    assert manifest["backend"] == {
        "status": "unavailable",
        "name": "ros2_tracing",
        "output": None,
        "error": "ImportError",
    }


def test_execute_time_trace_failure_updates_warning_and_manifest(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ROS_LOG_DIR", str(tmp_path / "ros-logs"))
    run_root = tmp_path / "run"
    run_root.mkdir()

    def trace_builder(**kwargs):
        return build_system_trace(
            **kwargs,
            find_spec=lambda _name: object(),
            import_module=lambda _name: SimpleNamespace(Trace=_ExecuteFailingTrace),
        )

    session = resolve_launch_profiling(
        mode_value="trace",
        output_root_value="",
        require_system_trace_value="false",
        run_root=run_root,
        session_id="session-1",
        source_commit="a" * 40,
        installed_prefix="/candidate/install",
        platform_name="linux",
        system_trace_builder=trace_builder,
    )
    assert session is not None
    application_started: list[bool] = []

    def mark_application_started(_context):
        application_started.append(True)
        return []

    service = LaunchService()
    service.include_launch_description(
        LaunchDescription(
            [
                *session.prefix_actions,
                OpaqueFunction(function=mark_application_started),
            ]
        )
    )

    assert service.run() == 0
    assert application_started == [True]
    assert session.warnings == ("ros2_tracing unavailable (RuntimeError)",)
    session.finalize_for_shutdown(reason="test complete")
    manifest = json.loads((session.profiling_root / "manifest.json").read_text())
    assert manifest["backend"] == {
        "status": "unavailable",
        "name": "ros2_tracing",
        "output": None,
        "error": "RuntimeError",
    }


@pytest.mark.parametrize(
    ("output", "message"),
    [
        ("relative", "absolute"),
        ("{outside}", "registered run evidence root"),
    ],
)
def test_output_root_cannot_escape_registered_run_root(
    tmp_path: Path,
    output: str,
    message: str,
) -> None:
    run_root = tmp_path / "run"
    run_root.mkdir()
    value = str(tmp_path / "outside") if output == "{outside}" else output

    with pytest.raises(RuntimeError, match=message):
        resolve_launch_profiling(
            mode_value="summary",
            output_root_value=value,
            require_system_trace_value="false",
            run_root=run_root,
            session_id="session-1",
            source_commit="a" * 40,
            installed_prefix="/candidate/install",
        )


def test_output_root_rejects_symlink_escape(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    outside = tmp_path / "outside"
    run_root.mkdir()
    outside.mkdir()
    (run_root / "linked").symlink_to(outside, target_is_directory=True)

    with pytest.raises(RuntimeError, match="registered run evidence root"):
        resolve_launch_profiling(
            mode_value="summary",
            output_root_value=str(run_root / "linked"),
            require_system_trace_value="false",
            run_root=run_root,
            session_id="session-1",
            source_commit="a" * 40,
            installed_prefix="/candidate/install",
        )


def test_output_root_rejects_existing_non_directory(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    run_root.mkdir()
    output = run_root / "output-file"
    output.write_text("not a directory", encoding="utf-8")

    with pytest.raises(RuntimeError, match="directory"):
        resolve_launch_profiling(
            mode_value="summary",
            output_root_value=str(output),
            require_system_trace_value="false",
            run_root=run_root,
            session_id="session-1",
            source_commit="a" * 40,
            installed_prefix="/candidate/install",
        )


@pytest.mark.parametrize(
    ("mode", "require", "message"),
    [
        ("enabled", "false", "profiling"),
        ("trace", "yes", "profiling_require_system_trace"),
    ],
)
def test_launch_profiling_rejects_invalid_public_values(
    tmp_path: Path,
    mode: str,
    require: str,
    message: str,
) -> None:
    run_root = tmp_path / "run"
    run_root.mkdir()

    with pytest.raises(RuntimeError, match=message):
        resolve_launch_profiling(
            mode_value=mode,
            output_root_value="",
            require_system_trace_value=require,
            run_root=run_root,
            session_id="session-1",
            source_commit="a" * 40,
            installed_prefix="/candidate/install",
        )
