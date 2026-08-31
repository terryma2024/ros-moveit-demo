from pathlib import Path
from types import SimpleNamespace

import pytest
from launch import LaunchDescription, LaunchService
from launch.action import Action
from launch.actions import OpaqueFunction

from so101_demo.profiling.model import ProfilingMode
from so101_demo.profiling.system_trace import (
    RequiredSystemTraceUnavailable,
    build_system_trace,
)


class _Trace:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs


class _ExecuteFailingTrace(Action):
    trace_directory = None

    def __init__(self, **_kwargs) -> None:
        super().__init__()

    def execute(self, _context):
        raise RuntimeError("LTTng setup failed at action execution")


class _ExecuteSuccessfulTrace(Action):
    def __init__(self, **kwargs) -> None:
        super().__init__()
        self.kwargs = kwargs
        self.trace_directory = None

    def execute(self, _context):
        self.trace_directory = str(
            Path(self.kwargs["base_path"]) / self.kwargs["session_name"]
        )
        return []


def _unexpected(*_args, **_kwargs):
    raise AssertionError("dependency discovery must stay lazy")


@pytest.mark.parametrize(
    ("mode", "platform", "require", "status"),
    [
        (ProfilingMode.OFF, "linux", False, "disabled"),
        (ProfilingMode.OFF, "linux", True, "disabled"),
        (ProfilingMode.SUMMARY, "linux", False, "disabled"),
        (ProfilingMode.SUMMARY, "linux", True, "disabled"),
        (ProfilingMode.TRACE, "darwin", False, "unsupported"),
        (ProfilingMode.TRACE, "darwin", True, "unsupported"),
    ],
)
def test_non_linux_trace_paths_never_discover_or_import_dependency(
    tmp_path: Path,
    mode: ProfilingMode,
    platform: str,
    require: bool,
    status: str,
) -> None:
    result = build_system_trace(
        mode=mode,
        require=require,
        profiling_root=tmp_path,
        session_id="session-1",
        platform_name=platform,
        find_spec=_unexpected,
        import_module=_unexpected,
    )

    assert result.status == status
    assert result.action is None
    assert result.backend is None
    assert result.output_path is None
    assert result.error is None


def test_linux_trace_builds_official_action_with_default_event_arguments(
    tmp_path: Path,
) -> None:
    imported: list[str] = []
    constructed: list[_Trace] = []

    def trace_type(**kwargs):
        trace = _Trace(**kwargs)
        constructed.append(trace)
        return trace

    def import_module(name: str):
        imported.append(name)
        return SimpleNamespace(Trace=trace_type)

    result = build_system_trace(
        mode=ProfilingMode.TRACE,
        require=True,
        profiling_root=tmp_path,
        session_id="session-1",
        platform_name="linux-gnu",
        find_spec=lambda name: object(),
        import_module=import_module,
    )

    assert imported == ["tracetools_launch.action"]
    assert result.status == "configured"
    assert result.backend == "ros2_tracing"
    assert result.output_path is None
    assert len(constructed) == 1
    assert constructed[0].kwargs == {
        "session_name": "so101-session-1",
        "append_timestamp": False,
        "base_path": str(tmp_path / "ros2-tracing"),
    }


def test_missing_linux_dependency_degrades_when_not_required(tmp_path: Path) -> None:
    imported: list[str] = []
    result = build_system_trace(
        mode=ProfilingMode.TRACE,
        require=False,
        profiling_root=tmp_path,
        session_id="session-1",
        platform_name="linux",
        find_spec=lambda _name: None,
        import_module=lambda name: imported.append(name),
    )

    assert imported == []
    assert result.status == "unavailable"
    assert result.action is None
    assert result.backend == "ros2_tracing"
    assert result.output_path is None
    assert result.error == "ModuleNotFoundError"


def test_optional_linux_trace_execute_failure_degrades_and_launch_continues(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ROS_LOG_DIR", str(tmp_path / "ros-logs"))
    result = build_system_trace(
        mode=ProfilingMode.TRACE,
        require=False,
        profiling_root=tmp_path,
        session_id="session-1",
        platform_name="linux",
        find_spec=lambda _name: object(),
        import_module=lambda _name: SimpleNamespace(Trace=_ExecuteFailingTrace),
    )
    application_started: list[bool] = []

    def mark_application_started(_context):
        application_started.append(True)
        return []

    service = LaunchService()
    service.include_launch_description(
        LaunchDescription(
            [
                result.action,
                OpaqueFunction(function=mark_application_started),
            ]
        )
    )

    assert service.run() == 0
    assert application_started == [True]
    assert result.status == "unavailable"
    assert result.output_path is None
    assert result.error == "RuntimeError"


def test_linux_trace_becomes_ready_only_after_official_action_starts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ROS_LOG_DIR", str(tmp_path / "ros-logs"))
    result = build_system_trace(
        mode=ProfilingMode.TRACE,
        require=True,
        profiling_root=tmp_path,
        session_id="session-1",
        platform_name="linux",
        find_spec=lambda _name: object(),
        import_module=lambda _name: SimpleNamespace(Trace=_ExecuteSuccessfulTrace),
    )
    assert result.status == "configured"
    assert result.output_path is None

    service = LaunchService()
    service.include_launch_description(LaunchDescription([result.action]))

    assert service.run() == 0
    assert result.status == "ready"
    assert result.output_path == tmp_path / "ros2-tracing/so101-session-1"
    assert result.error is None


def test_required_linux_trace_execute_failure_stops_following_launch_actions(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ROS_LOG_DIR", str(tmp_path / "ros-logs"))
    result = build_system_trace(
        mode=ProfilingMode.TRACE,
        require=True,
        profiling_root=tmp_path,
        session_id="session-1",
        platform_name="linux",
        find_spec=lambda _name: object(),
        import_module=lambda _name: SimpleNamespace(Trace=_ExecuteFailingTrace),
    )
    application_started: list[bool] = []

    def mark_application_started(_context):
        application_started.append(True)
        return []

    service = LaunchService()
    service.include_launch_description(
        LaunchDescription(
            [
                result.action,
                OpaqueFunction(function=mark_application_started),
            ]
        )
    )

    assert service.run() != 0
    assert application_started == []
    assert result.status == "unavailable"
    assert result.output_path is None
    assert result.error == "RuntimeError"


def test_missing_linux_dependency_fails_when_required(tmp_path: Path) -> None:
    with pytest.raises(RequiredSystemTraceUnavailable, match="ros2_tracing"):
        build_system_trace(
            mode=ProfilingMode.TRACE,
            require=True,
            profiling_root=tmp_path,
            session_id="session-1",
            platform_name="linux",
            find_spec=lambda _name: None,
            import_module=_unexpected,
        )


@pytest.mark.parametrize("session_id", ("../escape", "safe/../../escape", ""))
def test_linux_trace_rejects_unsafe_session_id_before_dependency_discovery(
    tmp_path: Path,
    session_id: str,
) -> None:
    with pytest.raises(ValueError, match="session_id"):
        build_system_trace(
            mode=ProfilingMode.TRACE,
            require=False,
            profiling_root=tmp_path,
            session_id=session_id,
            platform_name="linux",
            find_spec=_unexpected,
            import_module=_unexpected,
        )


@pytest.mark.parametrize("require", [False, True])
def test_import_failure_is_sanitized_and_obeys_required_policy(
    tmp_path: Path,
    require: bool,
) -> None:
    def fail_import(_name: str):
        raise ImportError("host-specific secret path")

    if require:
        with pytest.raises(RequiredSystemTraceUnavailable) as raised:
            build_system_trace(
                mode=ProfilingMode.TRACE,
                require=True,
                profiling_root=tmp_path,
                session_id="session-1",
                platform_name="linux",
                find_spec=lambda _name: object(),
                import_module=fail_import,
            )
        assert "host-specific" not in str(raised.value)
    else:
        result = build_system_trace(
            mode=ProfilingMode.TRACE,
            require=False,
            profiling_root=tmp_path,
            session_id="session-1",
            platform_name="linux",
            find_spec=lambda _name: object(),
            import_module=fail_import,
        )
        assert result.status == "unavailable"
        assert result.error == "ImportError"
