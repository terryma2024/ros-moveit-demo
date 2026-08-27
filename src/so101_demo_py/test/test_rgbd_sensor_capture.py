import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest


def _frame(stamp_ns: int = 20_000_000):
    from so101_demo.cli.rgbd_point_cloud import RgbdPointCloudFrame

    rgb = np.array(
        [[[230, 130, 35], [20, 30, 40]], [[50, 60, 70], [80, 90, 100]]],
        dtype=np.uint8,
    )
    full = np.array(
        [[-0.1, -0.1, 1.0], [0.1, -0.1, 1.0], [-0.1, 0.1, 1.0], [0.1, 0.1, 1.0]]
    )
    cup = full[:3]
    return RgbdPointCloudFrame(
        frame_id="task_camera_frame",
        stamp_ns=stamp_ns,
        image_width=2,
        image_height=2,
        intrinsics_fx_fy_cx_cy=(2.0, 2.0, 0.5, 0.5),
        rgb8=rgb,
        full_points_xyz=full,
        full_colors_rgb=rgb.reshape(-1, 3).astype(float) / 255.0,
        cup_points_xyz=cup,
        cup_colors_rgb=rgb.reshape(-1, 3)[:3].astype(float) / 255.0,
        color_candidate_point_count=3,
    )


class _Source:
    def __init__(self, aligned=(object(), object(), object())) -> None:
        self.aligned = aligned
        self.calls = []

    def capture(self, timeout_s: float):
        self.calls.append(timeout_s)
        return self.aligned


class _Tf:
    def __init__(self, result=object()) -> None:
        self.result = result
        self.calls = []

    def lookup_exact(self, target: str, source: str, stamp_ns: int, timeout_s: float):
        self.calls.append((target, source, stamp_ns, timeout_s))
        if self.result is None:
            raise TimeoutError("exact transform unavailable")
        return self.result


def test_ros_snapshot_source_requests_reliable_depth_ten_subscriptions(
    monkeypatch,
) -> None:
    from so101_demo.ros.rgbd_snapshot import RosRgbdSnapshotSource

    subscription_qos = []

    class FakeNode:
        def create_subscription(self, _type, _topic, _callback, qos):
            subscription_qos.append(qos)
            return object()

    fake_rclpy = SimpleNamespace(
        ok=lambda: True,
        create_node=lambda *_args, **_kwargs: FakeNode(),
    )
    monkeypatch.setitem(sys.modules, "rclpy", fake_rclpy)
    monkeypatch.setitem(
        sys.modules,
        "rclpy.parameter",
        SimpleNamespace(Parameter=lambda *_args, **_kwargs: object()),
    )
    monkeypatch.setitem(
        sys.modules,
        "rclpy.qos",
        SimpleNamespace(qos_profile_sensor_data=object()),
    )
    monkeypatch.setitem(
        sys.modules,
        "sensor_msgs.msg",
        SimpleNamespace(CameraInfo=object, Image=object),
    )
    monkeypatch.setitem(
        sys.modules,
        "tf2_ros",
        SimpleNamespace(
            Buffer=lambda: object(),
            TransformListener=lambda *_args: object(),
        ),
    )

    RosRgbdSnapshotSource(
        camera_info_topic="/test/camera_info",
        color_topic="/test/color",
        depth_topic="/test/depth",
    )

    assert subscription_qos == [10, 10, 10]


def test_snapshot_writes_artifacts_from_one_source_stamp(tmp_path: Path) -> None:
    from so101_demo.ros.rgbd_snapshot import capture_rgbd_snapshot

    source = _Source()
    transform = _Tf()
    result = capture_rgbd_snapshot(
        source,
        transform,
        tmp_path,
        build_cloud=lambda *_args, **_kwargs: _frame(),
    )

    assert result.summary["source_stamp_ns"] == result.frame.stamp_ns
    assert result.summary["cup_center_xyz"] == pytest.approx([-0.1, -0.1, 1.0])
    assert set(result.artifacts) == {
        "rgb",
        "full_cloud",
        "cup_cloud",
        "point_cloud_preview",
        "summary",
    }
    assert result.artifacts["rgb"].read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert result.artifacts["full_cloud"].read_text().startswith("ply\n")
    assert "element vertex 4" in result.artifacts["full_cloud"].read_text()
    assert "element vertex 3" in result.artifacts["cup_cloud"].read_text()
    assert transform.calls == [("world", "task_camera_frame", 20_000_000, 0.2)]


def test_snapshot_missing_exact_tf_writes_no_success_summary(tmp_path: Path) -> None:
    from so101_demo.ros.rgbd_snapshot import capture_rgbd_snapshot

    with pytest.raises(TimeoutError, match="exact transform"):
        capture_rgbd_snapshot(
            _Source(),
            _Tf(result=None),
            tmp_path,
            build_cloud=lambda *_args, **_kwargs: _frame(),
        )

    assert not (tmp_path / "summary.json").exists()


def test_snapshot_artifact_failure_prevents_success_summary(
    tmp_path: Path, monkeypatch
) -> None:
    from so101_demo.ros import rgbd_snapshot

    def fail(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(rgbd_snapshot, "write_full_point_cloud", fail)
    with pytest.raises(OSError, match="disk full"):
        rgbd_snapshot.capture_rgbd_snapshot(
            _Source(),
            _Tf(),
            tmp_path,
            build_cloud=lambda *_args, **_kwargs: _frame(),
        )
    assert not (tmp_path / "summary.json").exists()


def test_sensor_capture_cli_requires_exclusive_absolute_directory() -> None:
    from so101_demo.cli.rgbd_sensor_capture import build_parser

    options = build_parser().parse_args(["--output-directory", "/tmp/capture-1"])
    assert options.output_directory == Path("/tmp/capture-1")
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--output-directory", "relative"])

    setup_source = (Path(__file__).parents[1] / "setup.py").read_text()
    assert "rgbd_sensor_capture = so101_demo.cli.rgbd_sensor_capture:main" in setup_source
