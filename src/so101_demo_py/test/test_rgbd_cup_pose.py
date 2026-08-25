from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest


def _transform(*, translation, rotation_xyzw):
    return SimpleNamespace(
        transform=SimpleNamespace(
            translation=SimpleNamespace(
                x=translation[0], y=translation[1], z=translation[2]
            ),
            rotation=SimpleNamespace(
                x=rotation_xyzw[0],
                y=rotation_xyzw[1],
                z=rotation_xyzw[2],
                w=rotation_xyzw[3],
            ),
        )
    )


def _camera_partial_cylinder() -> np.ndarray:
    angles = np.linspace(-1.1, 1.2, 80)
    center_xy = np.array([0.02, -0.28])
    radius = 0.04
    xy = center_xy + radius * np.column_stack((np.cos(angles), np.sin(angles)))
    return np.column_stack((xy, np.linspace(0.175, 0.210, len(xy))))


def _world_from_camera_transform():
    return _transform(
        translation=(0.10, -0.05, 0.02),
        rotation_xyzw=(0.0, 0.0, 0.0, 1.0),
    )


def _cloud(*, stamp_ns: int):
    from so101_demo.cli.rgbd_point_cloud import CupPointCloudResult

    return CupPointCloudResult(
        frame_id="task_camera_frame",
        stamp_ns=stamp_ns,
        image_width=640,
        image_height=480,
        intrinsics_fx_fy_cx_cy=(500.0, 500.0, 320.0, 240.0),
        points_xyz=_camera_partial_cylinder(),
        colors_rgb=np.ones((80, 3)),
        full_point_count=1000,
        color_candidate_point_count=100,
    )


def _valid_frame(*, stamp_ns: int = 20):
    from so101_demo.ros.rgbd_cup_pose_node import CupPoseFrame

    return CupPoseFrame(
        stamp_ns=stamp_ns,
        source_frame_id="task_camera_frame",
        center_world_xyz=(0.02, -0.28, 0.165),
        fitted_radius_m=0.04,
        cloud=_cloud(stamp_ns=stamp_ns),
    )


def test_transform_points_applies_rotation_before_translation() -> None:
    from so101_demo.cli.rgbd_cup_pose import transform_points

    points = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 2.0]])
    half_sqrt_two = np.sqrt(0.5)
    transform = _transform(
        translation=(1.0, 2.0, 3.0),
        rotation_xyzw=(0.0, 0.0, half_sqrt_two, half_sqrt_two),
    )

    np.testing.assert_allclose(
        transform_points(points, transform),
        np.array([[1.0, 3.0, 3.0], [0.0, 2.0, 5.0]]),
        atol=1e-12,
    )


def test_estimate_upright_cup_pose_fits_partial_cylinder_surface() -> None:
    from so101_demo.cli.rgbd_cup_pose import estimate_upright_cup_pose

    center, fitted_radius = estimate_upright_cup_pose(
        _camera_partial_cylinder(),
        table_top_z=0.12,
        cup_height=0.09,
        expected_radius=0.04,
        radius_tolerance=0.005,
    )

    np.testing.assert_allclose(center, np.array([0.02, -0.28, 0.165]), atol=1e-10)
    assert fitted_radius == pytest.approx(0.04, abs=1e-10)


def test_estimate_upright_cup_pose_rejects_wrong_radius() -> None:
    from so101_demo.cli.rgbd_cup_pose import estimate_upright_cup_pose

    angles = np.linspace(0.0, 2.0, 30)
    points = np.column_stack(
        (0.10 * np.cos(angles), 0.10 * np.sin(angles), np.full(len(angles), 0.2))
    )

    with pytest.raises(ValueError, match="fitted radius"):
        estimate_upright_cup_pose(
            points,
            table_top_z=0.12,
            cup_height=0.09,
            expected_radius=0.04,
            radius_tolerance=0.005,
        )


def test_estimate_world_cup_pose_transforms_points_before_circle_fit() -> None:
    from so101_demo.cli.rgbd_cup_pose import estimate_world_cup_pose

    estimate = estimate_world_cup_pose(
        _camera_partial_cylinder() - np.array([0.10, -0.05, 0.02]),
        _world_from_camera_transform(),
        table_top_z=0.12,
        cup_height=0.09,
        expected_radius=0.04,
        radius_tolerance=0.005,
    )

    np.testing.assert_allclose(estimate.center_world_xyz, (0.02, -0.28, 0.165), atol=1e-6)
    assert estimate.fitted_radius_m == pytest.approx(0.04, abs=1e-6)


def test_failed_frame_never_republishes_last_valid_pose() -> None:
    from so101_demo.ros.rgbd_cup_pose_node import CupPoseFrameProcessor

    published = []
    errors = []
    valid = object()

    def estimate(aligned):
        if aligned is valid:
            return _valid_frame()
        raise ValueError("fitted radius is outside tolerance")

    processor = CupPoseFrameProcessor(
        estimate=estimate,
        publish=published.append,
        on_error=errors.append,
    )
    assert processor.process(valid)
    assert not processor.process(object())
    assert len(published) == 1
    assert [str(error) for error in errors] == ["fitted radius is outside tolerance"]


def test_fresh_frame_gate_rejects_duplicate_and_out_of_order_stamps() -> None:
    from so101_demo.ros.rgbd_cup_pose_node import FreshFrameGate

    gate = FreshFrameGate()

    assert gate.accept(20)
    assert not gate.accept(20)
    assert not gate.accept(19)
    assert gate.accept(21)


def test_pose_message_preserves_source_stamp_world_frame_and_identity_orientation() -> None:
    from so101_demo.ros.rgbd_cup_pose_node import pose_message_from_frame

    message = SimpleNamespace(
        header=SimpleNamespace(stamp=None, frame_id=""),
        pose=SimpleNamespace(
            position=SimpleNamespace(x=0.0, y=0.0, z=0.0),
            orientation=SimpleNamespace(x=1.0, y=1.0, z=1.0, w=0.0),
        ),
    )

    result = pose_message_from_frame(
        _valid_frame(stamp_ns=20_000_000),
        pose_factory=lambda: message,
        stamp_from_ns=lambda stamp_ns: (stamp_ns // 1_000_000_000, stamp_ns % 1_000_000_000),
    )

    assert result.header.stamp == (0, 20_000_000)
    assert result.header.frame_id == "world"
    assert (result.pose.position.x, result.pose.position.y, result.pose.position.z) == (
        0.02,
        -0.28,
        0.165,
    )
    assert (
        result.pose.orientation.x,
        result.pose.orientation.y,
        result.pose.orientation.z,
        result.pose.orientation.w,
    ) == (0.0, 0.0, 0.0, 1.0)


def test_first_valid_evidence_is_written_once_while_fresh_frames_publish() -> None:
    from so101_demo.ros.rgbd_cup_pose_node import (
        CupPoseFrameProcessor,
        FirstValidEvidencePublisher,
    )

    published = []
    ply_stamps = []
    json_stamps = []
    evidence_publisher = FirstValidEvidencePublisher(
        write_ply=lambda frame: ply_stamps.append(frame.stamp_ns),
        write_json=lambda frame: json_stamps.append(frame.stamp_ns),
        publish=published.append,
    )
    frames = iter((_valid_frame(stamp_ns=20), _valid_frame(stamp_ns=21)))
    processor = CupPoseFrameProcessor(
        estimate=lambda _aligned: next(frames),
        publish=evidence_publisher,
        on_error=lambda error: pytest.fail(str(error)),
    )

    assert processor.process(object())
    assert processor.process(object())
    assert [frame.stamp_ns for frame in published] == [20, 21]
    assert ply_stamps == [20]
    assert json_stamps == [20]


def test_evidence_failure_is_fatal_and_prevents_publication() -> None:
    from so101_demo.ros.rgbd_cup_pose_node import FirstValidEvidencePublisher

    published = []

    def fail(_frame) -> None:
        raise RuntimeError("evidence disk is full")

    publisher = FirstValidEvidencePublisher(
        write_ply=fail,
        write_json=lambda _frame: None,
        publish=published.append,
    )

    with pytest.raises(RuntimeError, match="evidence disk is full"):
        publisher(_valid_frame())
    assert published == []


def test_open3d_absence_is_an_actionable_preflight_error(monkeypatch) -> None:
    from so101_demo.ros import rgbd_cup_pose_node

    def missing(_name: str):
        raise ModuleNotFoundError("No module named 'open3d'")

    monkeypatch.setattr(rgbd_cup_pose_node.importlib, "import_module", missing)

    with pytest.raises(RuntimeError, match="python3 -m pip install open3d"):
        rgbd_cup_pose_node._require_open3d()


def test_startup_deadline_is_monotonic_and_fails_after_only_invalid_frames(capsys) -> None:
    from so101_demo.ros.rgbd_cup_pose_node import (
        CupPoseFrameProcessor,
        RgbdCupPoseOptions,
        run_rgbd_cup_pose,
    )

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

    monotonic_values = iter((10.0, 10.25, 10.50, 11.01))
    result = run_rgbd_cup_pose(
        RgbdCupPoseOptions(startup_timeout_s=1.0),
        runtime_factory=lambda _options: FakeRuntime(),
        monotonic=lambda: next(monotonic_values),
        open3d_preflight=lambda: None,
    )

    assert result != 0
    assert len(errors) == 2
    assert "RGBD_CUP_POSE_TIMEOUT" in capsys.readouterr().out


def test_run_continues_after_first_valid_frame_until_orderly_shutdown() -> None:
    from so101_demo.ros.rgbd_cup_pose_node import (
        RgbdCupPoseOptions,
        run_rgbd_cup_pose,
    )

    class FakeRuntime:
        def __init__(self) -> None:
            self.spins = 0
            self.closed = False

        @property
        def first_valid_published(self) -> bool:
            return self.spins >= 1

        def spin_once(self, _timeout_s: float) -> None:
            self.spins += 1

        def ok(self) -> bool:
            return self.spins < 3

        def close(self) -> None:
            self.closed = True

    runtime = FakeRuntime()
    result = run_rgbd_cup_pose(
        RgbdCupPoseOptions(startup_timeout_s=1.0),
        runtime_factory=lambda _options: runtime,
        monotonic=lambda: 10.0,
        open3d_preflight=lambda: None,
    )

    assert result == 0
    assert runtime.spins == 3
    assert runtime.closed


def test_runtime_evidence_io_failure_returns_explicit_nonzero(capsys) -> None:
    from so101_demo.ros.rgbd_cup_pose_node import (
        RgbdCupPoseOptions,
        run_rgbd_cup_pose,
    )

    class FakeRuntime:
        first_valid_published = False
        closed = False

        def spin_once(self, _timeout_s: float) -> None:
            raise OSError("evidence disk is full")

        def ok(self) -> bool:
            return True

        def close(self) -> None:
            self.closed = True

    runtime = FakeRuntime()
    result = run_rgbd_cup_pose(
        RgbdCupPoseOptions(startup_timeout_s=1.0),
        runtime_factory=lambda _options: runtime,
        monotonic=lambda: 10.0,
        open3d_preflight=lambda: None,
    )

    assert result != 0
    assert runtime.closed
    output = capsys.readouterr().out
    assert "RGBD_CUP_POSE_FATAL" in output
    assert "evidence disk is full" in output


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (["--startup-timeout-s", "nan"], "finite and positive"),
        (["--output-topic", "cup_pose"], "absolute ROS topic"),
        (["--output-ply", ""], "non-empty path"),
        (["--evidence-json", "relative.json"], "absolute output file path"),
    ],
)
def test_cli_rejects_invalid_options(arguments, message, capsys) -> None:
    from so101_demo.cli.rgbd_cup_pose import main

    with pytest.raises(SystemExit) as error:
        main(arguments)
    assert error.value.code == 2
    assert message in capsys.readouterr().err


def test_package_registers_rgbd_cup_pose_executable() -> None:
    package_root = Path(__file__).resolve().parents[1]
    setup_source = (package_root / "setup.py").read_text(encoding="utf-8")

    assert "rgbd_cup_pose = so101_demo.cli.rgbd_cup_pose:main" in setup_source
