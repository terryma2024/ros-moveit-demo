"""Data-behavior tests for the phase-separated task-camera probe."""

from __future__ import annotations

import importlib.util
import math
import os
import struct
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


PROBE_PATH = Path(__file__).with_name("macos_camera_topic_probe.py")
SPEC = importlib.util.spec_from_file_location("macos_camera_topic_probe", PROBE_PATH)
assert SPEC is not None and SPEC.loader is not None
PROBE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROBE)


def _stamp(stamp_ns: int) -> SimpleNamespace:
    return SimpleNamespace(sec=stamp_ns // 1_000_000_000, nanosec=stamp_ns % 1_000_000_000)


def _header(stamp_ns: int, frame_id: str = "task_camera_frame") -> SimpleNamespace:
    return SimpleNamespace(stamp=_stamp(stamp_ns), frame_id=frame_id)


def _info(stamp_ns: int, *, width: int = 640, height: int = 480, frame_id: str = "task_camera_frame"):
    return SimpleNamespace(header=_header(stamp_ns, frame_id), width=width, height=height)


def _image(
    stamp_ns: int,
    *,
    encoding: str,
    data: bytes,
    width: int = 640,
    height: int = 480,
    frame_id: str = "task_camera_frame",
    is_bigendian: int = 0,
):
    return SimpleNamespace(
        header=_header(stamp_ns, frame_id),
        width=width,
        height=height,
        encoding=encoding,
        data=data,
        is_bigendian=is_bigendian,
    )


def _stamps_at_frequency(frequency_hz: float) -> list[int]:
    elapsed_ns = round(29 / frequency_hz * 1_000_000_000)
    return [round(index * elapsed_ns / 29) for index in range(30)]


def _phase1_colors(frequency_hz: float = 10.0):
    return [_image(stamp, encoding="rgb8", data=b"rgb") for stamp in _stamps_at_frequency(frequency_hz)]


def _phase2_messages():
    common_stamp = 200
    infos = [_info(stamp) for stamp in (100, common_stamp, 300)]
    colors = [_image(stamp, encoding="rgb8", data=b"rgb") for stamp in (50, common_stamp, 400)]
    depths = [
        _image(stamp, encoding="32FC1", data=struct.pack("<ff", 0.5, 1.25))
        for stamp in (20, common_stamp, 500)
    ]
    return infos, colors, depths


@pytest.mark.parametrize(
    ("frequency_hz", "accepted"),
    [(7.99, False), (8.0, True), (12.0, True), (12.01, False)],
)
def test_phase1_uses_strict_end_to_end_frequency_boundaries(frequency_hz: float, accepted: bool) -> None:
    colors = _phase1_colors(frequency_hz)
    if accepted:
        summary = PROBE.summarize_color_phase(colors)
        assert summary["color_frequency_hz"] == pytest.approx(frequency_hz, abs=1e-8)
    else:
        with pytest.raises(RuntimeError, match="unexpected color frequency"):
            PROBE.summarize_color_phase(colors)


def test_phase1_dropped_frames_lower_the_end_to_end_average() -> None:
    ideal = list(range(0, 3_000_000_000, 100_000_000))
    with_drop = ideal[:-1] + [ideal[-1] + 1_000_000_000]

    ideal_summary = PROBE.summarize_color_phase(
        [_image(stamp, encoding="rgb8", data=b"rgb") for stamp in ideal]
    )
    with pytest.raises(RuntimeError, match=r"unexpected color frequency: 7\."):
        PROBE.summarize_color_phase(
            [_image(stamp, encoding="rgb8", data=b"rgb") for stamp in with_drop]
        )
    assert ideal_summary["color_frequency_hz"] == pytest.approx(10.0)


def test_phase1_requires_thirty_unique_actual_header_stamps() -> None:
    colors = _phase1_colors()[:29]
    colors.append(colors[-1])

    with pytest.raises(RuntimeError, match="30 unique color header stamps"):
        PROBE.summarize_color_phase(colors)


@pytest.mark.parametrize("short_topic", ["camera_info", "color", "depth"])
def test_phase2_requires_three_samples_from_each_topic(short_topic: str) -> None:
    infos, colors, depths = _phase2_messages()
    values = {"camera_info": infos, "color": colors, "depth": depths}
    values[short_topic] = values[short_topic][:2]

    with pytest.raises(RuntimeError, match="at least 3 samples per topic"):
        PROBE.summarize_aligned_phase(values["camera_info"], values["color"], values["depth"])


def test_phase2_requires_an_exact_common_header_stamp() -> None:
    infos, colors, depths = _phase2_messages()
    depths[1].header.stamp = _stamp(201)

    with pytest.raises(RuntimeError, match="no timestamp shared"):
        PROBE.summarize_aligned_phase(infos, colors, depths)


@pytest.mark.parametrize(
    ("mutation", "error"),
    [
        (lambda info, color, depth: setattr(info, "width", 320), "dimensions differ"),
        (lambda info, color, depth: setattr(color, "width", 320), "dimensions differ"),
        (lambda info, color, depth: setattr(depth, "height", 240), "dimensions differ"),
        (lambda info, color, depth: setattr(color.header, "frame_id", "wrong"), "frame_id"),
        (lambda info, color, depth: setattr(color, "encoding", "bgr8"), "color encoding"),
        (lambda info, color, depth: setattr(depth, "encoding", "16UC1"), "depth encoding"),
        (lambda info, color, depth: setattr(color, "data", b""), "color image has no data"),
        (lambda info, color, depth: setattr(depth, "data", b""), "depth image has no data"),
        (
            lambda info, color, depth: setattr(depth, "data", struct.pack("<ff", 0.5, math.nan)),
            "depth image contains non-finite or non-positive values",
        ),
        (
            lambda info, color, depth: setattr(depth, "data", struct.pack("<ff", 0.5, 0.0)),
            "depth image contains non-finite or non-positive values",
        ),
    ],
)
def test_phase2_validates_the_messages_at_the_common_stamp(mutation, error: str) -> None:
    infos, colors, depths = _phase2_messages()
    mutation(infos[1], colors[1], depths[1])

    with pytest.raises(RuntimeError, match=error):
        PROBE.summarize_aligned_phase(infos, colors, depths)


def test_phase2_scans_the_complete_depth_payload() -> None:
    infos, colors, depths = _phase2_messages()
    depths[1].data = struct.pack("<fff", 0.5, 1.0, -0.1)

    with pytest.raises(RuntimeError, match="non-finite or non-positive"):
        PROBE.summarize_aligned_phase(infos, colors, depths)


def test_phase2_rejects_a_consistent_wrong_resolution() -> None:
    infos, colors, depths = _phase2_messages()
    for message in (infos[1], colors[1], depths[1]):
        message.width = 320
        message.height = 240

    with pytest.raises(RuntimeError, match="unexpected dimensions: 320x240"):
        PROBE.summarize_aligned_phase(infos, colors, depths)


def test_phase2_rejects_a_consistent_wrong_frame() -> None:
    infos, colors, depths = _phase2_messages()
    for message in (infos[1], colors[1], depths[1]):
        message.header.frame_id = "wrong_frame"

    with pytest.raises(RuntimeError, match="unexpected frame_id: wrong_frame"):
        PROBE.summarize_aligned_phase(infos, colors, depths)


class _FakeContext:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.active = False

    def ok(self) -> bool:
        return self.active


class _FakeNode:
    def __init__(self, events: list[str], *, destroy_result: bool = True) -> None:
        self.events = events
        self.destroy_result = destroy_result

    def destroy_node(self) -> bool:
        self.events.append("destroy_node")
        return self.destroy_result


class _FakeExecutor:
    def __init__(
        self,
        events: list[str],
        *,
        shutdown_result: bool = True,
        shutdown_error: Exception | None = None,
    ) -> None:
        self.events = events
        self.shutdown_result = shutdown_result
        self.shutdown_error = shutdown_error

    def add_node(self, node) -> None:
        del node
        self.events.append("add_node")

    def remove_node(self, node) -> None:
        del node
        self.events.append("remove_node")

    def spin_once(self, timeout_sec: float) -> None:
        del timeout_sec
        self.events.append("spin_once")

    def shutdown(self, timeout_sec: float) -> bool:
        del timeout_sec
        self.events.append("executor_shutdown")
        if self.shutdown_error is not None:
            raise self.shutdown_error
        return self.shutdown_result


def _install_fake_ros_lifecycle(
    monkeypatch,
    events: list[str],
    *,
    shutdown_result: bool = True,
    shutdown_error: Exception | None = None,
) -> None:
    context = _FakeContext(events)
    executor = _FakeExecutor(
        events,
        shutdown_result=shutdown_result,
        shutdown_error=shutdown_error,
    )

    monkeypatch.setattr(PROBE, "Context", lambda: context)
    monkeypatch.setattr(PROBE, "SingleThreadedExecutor", lambda context: executor)

    def fake_init(*, context, signal_handler_options) -> None:
        del signal_handler_options
        events.append("rclpy_init")
        context.active = True

    def fake_shutdown(*, context, uninstall_handlers) -> None:
        del uninstall_handlers
        events.append("rclpy_shutdown")
        context.active = False

    monkeypatch.setattr(PROBE.rclpy, "init", fake_init)
    monkeypatch.setattr(PROBE.rclpy, "shutdown", fake_shutdown)


def test_phase_timeout_still_tears_down_every_created_resource(monkeypatch) -> None:
    events: list[str] = []
    _install_fake_ros_lifecycle(monkeypatch, events)
    node = _FakeNode(events)

    with pytest.raises(RuntimeError, match="timed out"):
        PROBE._run_node_phase(lambda context: node, lambda candidate: False, 0.0)

    assert events == [
        "rclpy_init",
        "add_node",
        "remove_node",
        "executor_shutdown",
        "destroy_node",
        "rclpy_shutdown",
    ]


@pytest.mark.parametrize(
    ("shutdown_result", "shutdown_error"),
    [(False, None), (True, RuntimeError("executor exploded"))],
)
def test_executor_shutdown_failure_makes_the_phase_fail_after_full_cleanup(
    monkeypatch, shutdown_result: bool, shutdown_error: Exception | None
) -> None:
    events: list[str] = []
    _install_fake_ros_lifecycle(
        monkeypatch,
        events,
        shutdown_result=shutdown_result,
        shutdown_error=shutdown_error,
    )
    node = _FakeNode(events)

    with pytest.raises(RuntimeError, match="phase teardown failed"):
        PROBE._run_node_phase(lambda context: node, lambda candidate: True, 1.0)

    assert events[-4:] == [
        "remove_node",
        "executor_shutdown",
        "destroy_node",
        "rclpy_shutdown",
    ]


def test_node_construction_failure_still_shuts_down_executor_and_context(monkeypatch) -> None:
    events: list[str] = []
    _install_fake_ros_lifecycle(monkeypatch, events)

    def fail_node_creation(context):
        del context
        events.append("node_factory")
        raise RuntimeError("node creation failed")

    with pytest.raises(RuntimeError, match="node creation failed"):
        PROBE._run_node_phase(fail_node_creation, lambda candidate: True, 1.0)

    assert events == [
        "rclpy_init",
        "node_factory",
        "executor_shutdown",
        "rclpy_shutdown",
    ]


def test_cli_starts_phase2_only_after_phase1_teardown_and_removes_stale_output(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    output = tmp_path / "camera-topics.json"
    output.write_text('{"stale": true}\n', encoding="utf-8")
    events: list[str] = []

    def color_phase(timeout_s: float) -> dict:
        del timeout_s
        events.extend(["phase1_create", "phase1_full_teardown"])
        return {"color_frequency_hz": 10.0}

    def aligned_phase(timeout_s: float) -> dict:
        del timeout_s
        assert events[-1] == "phase1_full_teardown"
        events.append("phase2_create")
        raise RuntimeError("phase2 failed")

    monkeypatch.setattr(PROBE, "collect_color_phase", color_phase)
    monkeypatch.setattr(PROBE, "collect_aligned_phase", aligned_phase)
    monkeypatch.setattr(
        sys,
        "argv",
        ["macos_camera_topic_probe.py", "--output", str(output)],
    )

    assert PROBE.main() == 1
    assert events == ["phase1_create", "phase1_full_teardown", "phase2_create"]
    assert not output.exists()
    assert "camera probe failed: phase2 failed" in capsys.readouterr().err


def test_both_phases_write_one_atomic_success_json(tmp_path: Path, monkeypatch) -> None:
    infos, colors, depths = _phase2_messages()
    output = tmp_path / "camera-topics.json"
    replacements: list[tuple[Path, Path]] = []
    real_replace = os.replace

    def recording_replace(source, destination) -> None:
        source_path = Path(source)
        destination_path = Path(destination)
        assert source_path.exists()
        assert source_path.parent == output.parent
        assert not destination_path.exists()
        replacements.append((source_path, destination_path))
        real_replace(source, destination)

    monkeypatch.setattr(PROBE.os, "replace", recording_replace)
    result = PROBE.qualify_and_write(output, _phase1_colors(), infos, colors, depths)

    assert replacements and len(replacements) == 1
    assert replacements[0][1] == output
    assert output.exists()
    assert result["phase1"]["unique_color_header_stamps"] == 30
    assert result["phase2"]["aligned_stamp_ns"] == 200
    assert not list(tmp_path.glob(".camera-topics.json.*.tmp"))


def test_phase_failure_removes_stale_output_and_writes_no_success_json(tmp_path: Path) -> None:
    infos, colors, depths = _phase2_messages()
    depths[1].header.stamp = _stamp(201)
    output = tmp_path / "camera-topics.json"
    output.write_text('{"stale": true}\n', encoding="utf-8")

    with pytest.raises(RuntimeError, match="no timestamp shared"):
        PROBE.qualify_and_write(output, _phase1_colors(), infos, colors, depths)

    assert not output.exists()
    assert not list(tmp_path.glob(".camera-topics.json.*.tmp"))
