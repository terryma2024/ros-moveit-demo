from pathlib import Path
from types import SimpleNamespace

import pytest

from so101_demo.profiling.model import ProfilingMode
from so101_demo.profiling.system_trace import (
    RequiredSystemTraceUnavailable,
    build_system_trace,
)


class _Trace:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs


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

    def import_module(name: str):
        imported.append(name)
        return SimpleNamespace(Trace=_Trace)

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
    assert result.status == "ready"
    assert result.backend == "ros2_tracing"
    assert result.output_path == tmp_path / "ros2-tracing/so101-session-1"
    assert isinstance(result.action, _Trace)
    assert result.action.kwargs == {
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
