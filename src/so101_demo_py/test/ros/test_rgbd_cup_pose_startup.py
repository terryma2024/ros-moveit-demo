"""Preflight, the startup deadline, shutdown and interrupt handling of the node."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_open3d_absence_is_an_actionable_preflight_error(monkeypatch) -> None:
    import importlib.util

    from so101_demo.ros.rgbd_cup_pose import frames as rgbd_cup_pose_node_frames

    monkeypatch.setattr(importlib.util, "find_spec", lambda _name: None)

    with pytest.raises(RuntimeError, match="python3 -m pip install open3d"):
        rgbd_cup_pose_node_frames._require_open3d(1.0)


def test_open3d_discoverable_but_import_broken_fails_preflight() -> None:
    from so101_demo.ros.rgbd_cup_pose import frames as rgbd_cup_pose_node_frames

    def broken_import(_name: str):
        raise ImportError("dlopen native library failed")

    with pytest.raises(RuntimeError, match="Open3D is unusable.*dlopen"):
        rgbd_cup_pose_node_frames._require_open3d(
            1.0,
            find_spec=lambda _name: object(),
            importer=broken_import,
        )


def test_startup_deadline_is_monotonic_and_fails_after_only_invalid_frames(capsys) -> None:
    from so101_demo.ros.rgbd_cup_pose.frames import CupPoseFrameProcessor, RgbdCupPoseOptions
    from so101_demo.ros.rgbd_cup_pose_node import run_rgbd_cup_pose

    errors = []

    def reject(_aligned):
        raise ValueError("fitted radius is outside tolerance")

    processor = CupPoseFrameProcessor(
        estimate=reject,
        publish=lambda _frame: pytest.fail("invalid frame was published"),
        on_error=errors.append,
    )

    class FakeRuntime:
        first_valid_published = False

        def spin_once(self, _timeout_s: float) -> None:
            assert not processor.process(object())

        def ok(self) -> bool:
            return True

        def close(self) -> None:
            return None

    monotonic_values = iter((10.0, 10.05, 10.10, 10.15, 10.25, 10.50, 11.01))
    result = run_rgbd_cup_pose(
        RgbdCupPoseOptions(startup_timeout_s=1.0),
        runtime_factory=lambda _options, _deadline, _monotonic: FakeRuntime(),
        monotonic=lambda: next(monotonic_values),
        open3d_preflight=lambda _remaining_s: None,
    )

    assert result != 0
    assert len(errors) == 2
    assert "RGBD_CUP_POSE_TIMEOUT" in capsys.readouterr().out


def test_run_profiles_total_without_changing_success_result(tmp_path: Path) -> None:
    from so101_demo.profiling.model import ProfilingConfig, ProfilingMode
    from so101_demo.profiling.session import build_profiler
    from so101_demo.ros.rgbd_cup_pose.frames import RgbdCupPoseOptions
    from so101_demo.ros.rgbd_cup_pose_node import run_rgbd_cup_pose

    class FakeRuntime:
        first_valid_published = True

        def ok(self) -> bool:
            return False

        def spin_once(self, _timeout_s: float) -> None:
            raise AssertionError("stopped runtime spun")

        def close(self) -> None:
            pass

    profiler = build_profiler(
        ProfilingConfig(
            mode=ProfilingMode.SUMMARY,
            output_root=tmp_path / "profiling",
            session_id="session-1",
            process_role="perception",
        )
    )
    assert profiler is not None

    result = run_rgbd_cup_pose(
        RgbdCupPoseOptions(),
        runtime_factory=lambda *_args: FakeRuntime(),
        monotonic=lambda: 10.0,
        open3d_preflight=lambda _remaining: None,
        profiler=profiler,
    )
    profiler.close()

    assert result == 0
    complete = [
        json.loads(line)
        for line in (
            tmp_path / "profiling/processes/perception.events.jsonl"
        ).read_text().splitlines()
        if '"event_type":"span_complete"' in line
    ]
    assert complete[-1]["name"] == "perception.total"
    assert complete[-1]["outcome"] == "published"


def test_startup_budget_begins_before_preflight_and_runtime_construction(capsys) -> None:
    from so101_demo.ros.rgbd_cup_pose.frames import RgbdCupPoseOptions
    from so101_demo.ros.rgbd_cup_pose_node import run_rgbd_cup_pose

    class FakeRuntime:
        first_valid_published = False
        closed = False

        def spin_once(self, _timeout_s: float) -> None:
            pytest.fail("expired startup budget reached spin")

        def ok(self) -> bool:
            return True

        def close(self) -> None:
            self.closed = True

    times = iter((10.0, 10.4, 11.1))
    observed_preflight_budgets = []

    result = run_rgbd_cup_pose(
        RgbdCupPoseOptions(startup_timeout_s=1.0),
        runtime_factory=lambda *_args: pytest.fail("expired preflight reached construction"),
        monotonic=lambda: next(times),
        open3d_preflight=observed_preflight_budgets.append,
    )

    assert result != 0
    assert observed_preflight_budgets == [pytest.approx(0.6)]
    assert "RGBD_CUP_POSE_TIMEOUT" in capsys.readouterr().out


def test_runtime_construction_overrun_is_closed_before_spin(capsys) -> None:
    from so101_demo.ros.rgbd_cup_pose.frames import RgbdCupPoseOptions
    from so101_demo.ros.rgbd_cup_pose_node import run_rgbd_cup_pose

    class FakeRuntime:
        first_valid_published = False
        closed = False

        def spin_once(self, _timeout_s: float) -> None:
            pytest.fail("expired construction reached spin")

        def ok(self) -> bool:
            return True

        def close(self) -> None:
            self.closed = True

    runtime = FakeRuntime()
    times = iter((10.0, 10.1, 10.2, 10.3, 11.1))

    def construct(_options, _deadline, construction_clock):
        assert construction_clock() == 10.3
        return runtime

    result = run_rgbd_cup_pose(
        RgbdCupPoseOptions(startup_timeout_s=1.0),
        runtime_factory=construct,
        monotonic=lambda: next(times),
        open3d_preflight=lambda _remaining_s: None,
    )

    assert result != 0
    assert runtime.closed
    assert "RGBD_CUP_POSE_TIMEOUT" in capsys.readouterr().out


def test_prevalid_spin_wait_cannot_exceed_remaining_startup_budget() -> None:
    from so101_demo.ros.rgbd_cup_pose.frames import RgbdCupPoseOptions
    from so101_demo.ros.rgbd_cup_pose_node import run_rgbd_cup_pose

    class FakeRuntime:
        first_valid_published = False

        def __init__(self) -> None:
            self.running = True
            self.spin_timeouts = []

        def spin_once(self, timeout_s: float) -> None:
            self.spin_timeouts.append(timeout_s)
            self.running = False

        def ok(self) -> bool:
            return self.running

        def close(self) -> None:
            return None

    runtime = FakeRuntime()
    times = iter((10.0, 10.1, 10.2, 10.3, 10.98))
    result = run_rgbd_cup_pose(
        RgbdCupPoseOptions(startup_timeout_s=1.0),
        runtime_factory=lambda _options, _deadline, _monotonic: runtime,
        monotonic=lambda: next(times),
        open3d_preflight=lambda _remaining_s: None,
    )

    assert result != 0
    assert runtime.spin_timeouts == [pytest.approx(0.02)]


def test_context_shutdown_before_first_valid_pose_is_nonzero(capsys) -> None:
    from so101_demo.ros.rgbd_cup_pose.frames import RgbdCupPoseOptions
    from so101_demo.ros.rgbd_cup_pose_node import run_rgbd_cup_pose

    class FakeRuntime:
        first_valid_published = False
        closed = False

        def spin_once(self, _timeout_s: float) -> None:
            pytest.fail("stopped runtime reached spin")

        def ok(self) -> bool:
            return False

        def close(self) -> None:
            self.closed = True

    runtime = FakeRuntime()
    result = run_rgbd_cup_pose(
        RgbdCupPoseOptions(startup_timeout_s=1.0),
        runtime_factory=lambda _options, _deadline, _monotonic: runtime,
        monotonic=lambda: 10.0,
        open3d_preflight=lambda _remaining_s: None,
    )

    assert result != 0
    assert runtime.closed
    assert "RGBD_CUP_POSE_SHUTDOWN_BEFORE_FIRST_VALID" in capsys.readouterr().out


@pytest.mark.parametrize("interrupt_phase", ["preflight", "construction"])
def test_setup_sigint_is_actionable_nonzero_without_traceback(interrupt_phase, capsys) -> None:
    from so101_demo.ros.rgbd_cup_pose.frames import RgbdCupPoseOptions
    from so101_demo.ros.rgbd_cup_pose_node import run_rgbd_cup_pose

    def preflight(_remaining_s: float) -> None:
        if interrupt_phase == "preflight":
            raise KeyboardInterrupt

    def construct(_options, _deadline, _monotonic):
        if interrupt_phase == "construction":
            raise KeyboardInterrupt
        pytest.fail("preflight interrupt reached construction")

    result = run_rgbd_cup_pose(
        RgbdCupPoseOptions(startup_timeout_s=1.0),
        runtime_factory=construct,
        monotonic=lambda: 10.0,
        open3d_preflight=preflight,
    )

    assert result != 0
    output = capsys.readouterr().out
    assert "RGBD_CUP_POSE_INTERRUPTED_BEFORE_FIRST_VALID" in output
    assert "Traceback" not in output


def test_sigint_before_first_valid_pose_is_nonzero(capsys) -> None:
    from so101_demo.ros.rgbd_cup_pose.frames import RgbdCupPoseOptions
    from so101_demo.ros.rgbd_cup_pose_node import run_rgbd_cup_pose

    class FakeRuntime:
        first_valid_published = False

        def spin_once(self, _timeout_s: float) -> None:
            raise KeyboardInterrupt

        def ok(self) -> bool:
            return True

        def close(self) -> None:
            return None

    result = run_rgbd_cup_pose(
        RgbdCupPoseOptions(startup_timeout_s=1.0),
        runtime_factory=lambda _options, _deadline, _monotonic: FakeRuntime(),
        monotonic=lambda: 10.0,
        open3d_preflight=lambda _remaining_s: None,
    )

    assert result != 0
    assert "RGBD_CUP_POSE_INTERRUPTED_BEFORE_FIRST_VALID" in capsys.readouterr().out


def test_sigint_after_first_valid_pose_is_orderly(capsys) -> None:
    from so101_demo.ros.rgbd_cup_pose.frames import RgbdCupPoseOptions
    from so101_demo.ros.rgbd_cup_pose_node import run_rgbd_cup_pose

    class FakeRuntime:
        first_valid_published = True

        def spin_once(self, _timeout_s: float) -> None:
            raise KeyboardInterrupt

        def ok(self) -> bool:
            return True

        def close(self) -> None:
            return None

    result = run_rgbd_cup_pose(
        RgbdCupPoseOptions(startup_timeout_s=1.0),
        runtime_factory=lambda _options, _deadline, _monotonic: FakeRuntime(),
        monotonic=lambda: 10.0,
        open3d_preflight=lambda _remaining_s: None,
    )

    assert result == 0
    assert '"status": "STOPPED"' in capsys.readouterr().out


def test_context_shutdown_runtime_error_after_first_valid_pose_is_orderly(
    capsys,
) -> None:
    from so101_demo.ros.rgbd_cup_pose.frames import RgbdCupPoseOptions
    from so101_demo.ros.rgbd_cup_pose_node import run_rgbd_cup_pose

    class FakeRuntime:
        first_valid_published = True
        running = True
        closed = False

        def spin_once(self, _timeout_s: float) -> None:
            self.running = False
            raise RuntimeError("publisher's context is invalid")

        def ok(self) -> bool:
            return self.running

        def close(self) -> None:
            self.closed = True

    runtime = FakeRuntime()
    result = run_rgbd_cup_pose(
        RgbdCupPoseOptions(startup_timeout_s=1.0),
        runtime_factory=lambda _options, _deadline, _monotonic: runtime,
        monotonic=lambda: 10.0,
        open3d_preflight=lambda _remaining_s: None,
    )

    assert result == 0
    assert runtime.closed
    output = capsys.readouterr().out
    assert '"status": "STOPPED"' in output
    assert "RGBD_CUP_POSE_FATAL" not in output


def test_live_context_runtime_error_after_first_valid_pose_remains_fatal(
    capsys,
) -> None:
    from so101_demo.ros.rgbd_cup_pose.frames import RgbdCupPoseOptions
    from so101_demo.ros.rgbd_cup_pose_node import run_rgbd_cup_pose

    class FakeRuntime:
        first_valid_published = True
        closed = False

        def spin_once(self, _timeout_s: float) -> None:
            raise RuntimeError("publisher serialization failed")

        def ok(self) -> bool:
            return True

        def close(self) -> None:
            self.closed = True

    runtime = FakeRuntime()
    result = run_rgbd_cup_pose(
        RgbdCupPoseOptions(startup_timeout_s=1.0),
        runtime_factory=lambda _options, _deadline, _monotonic: runtime,
        monotonic=lambda: 10.0,
        open3d_preflight=lambda _remaining_s: None,
    )

    assert result != 0
    assert runtime.closed
    output = capsys.readouterr().out
    assert "RGBD_CUP_POSE_FATAL" in output
    assert "publisher serialization failed" in output
