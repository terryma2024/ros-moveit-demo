from pathlib import Path
from types import SimpleNamespace
import sys

import numpy as np

from so101_demo.cli import rgbd_point_cloud


def _message(
    *,
    stamp_ns: int,
    frame_id: str = "task_camera_frame",
) -> SimpleNamespace:
    return SimpleNamespace(
        header=SimpleNamespace(
            frame_id=frame_id,
            stamp=SimpleNamespace(sec=stamp_ns // 1_000_000_000, nanosec=stamp_ns % 1_000_000_000),
        )
    )


def _camera_info() -> SimpleNamespace:
    message = _message(stamp_ns=20_000_000)
    message.width = 2
    message.height = 2
    message.k = [2.0, 0.0, 0.5, 0.0, 2.0, 0.5, 0.0, 0.0, 1.0]
    return message


def _rgb_message(*, step: int = 6) -> SimpleNamespace:
    message = _message(stamp_ns=20_000_000)
    message.width = 2
    message.height = 2
    message.encoding = "rgb8"
    message.step = step
    message.data = bytes(
        [
            230,
            130,
            35,
            230,
            130,
            35,
            230,
            130,
            35,
            92,
            61,
            36,
        ]
    )
    return message


def _depth_message(*, step: int = 8) -> SimpleNamespace:
    message = _message(stamp_ns=20_000_000)
    message.width = 2
    message.height = 2
    message.encoding = "32FC1"
    message.is_bigendian = False
    message.step = step
    message.data = np.array([[1.0, 1.0], [1.0, 1.0]], dtype="<f4").tobytes()
    return message


class _FakeCloud:
    def __init__(self, points: np.ndarray, colors: np.ndarray) -> None:
        self.points = np.asarray(points, dtype=np.float64)
        self.colors = np.asarray(colors, dtype=np.float64)

    def select_by_index(self, indices: list[int]) -> "_FakeCloud":
        return _FakeCloud(self.points[indices], self.colors[indices])

    def cluster_dbscan(
        self, *, eps: float, min_points: int, print_progress: bool
    ) -> np.ndarray:
        assert eps == 0.02
        assert min_points == 2
        assert not print_progress
        return np.zeros(len(self.points), dtype=np.int32)


def _fake_open3d_cloud(
    points: np.ndarray, colors: np.ndarray
) -> tuple[object, _FakeCloud]:
    return object(), _FakeCloud(points, colors)


def test_open3d_boundary_copies_frozen_arrays_to_writable_c_memory(monkeypatch) -> None:
    received = []

    class PointCloud:
        pass

    def vector(array):
        received.append(array)
        return array

    fake_open3d = SimpleNamespace(
        geometry=SimpleNamespace(PointCloud=PointCloud),
        utility=SimpleNamespace(Vector3dVector=vector),
    )
    monkeypatch.setitem(sys.modules, "open3d", fake_open3d)
    points = np.arange(9, dtype=np.float64).reshape(3, 3)
    colors = np.full((3, 3), 0.5, dtype=np.float64)
    points.setflags(write=False)
    colors.setflags(write=False)

    _module, cloud = rgbd_point_cloud._open3d_cloud(points, colors)

    assert cloud.points is received[0]
    assert cloud.colors is received[1]
    assert all(array.flags.writeable and array.flags.c_contiguous for array in received)
    assert not np.shares_memory(received[0], points)
    assert not np.shares_memory(received[1], colors)


def test_aligned_buffer_emits_only_an_exact_three_message_stamp() -> None:
    buffer = rgbd_point_cloud.AlignedRgbdBuffer(max_samples=3)

    assert buffer.add_camera_info(_message(stamp_ns=10)) is None
    assert buffer.add_color(_message(stamp_ns=11)) is None
    assert buffer.add_depth(_message(stamp_ns=10)) is None

    aligned = buffer.add_color(_message(stamp_ns=10))
    assert aligned is not None
    assert tuple(rgbd_point_cloud.message_stamp_ns(item) for item in aligned) == (10, 10, 10)


def test_build_cup_point_cloud_returns_selected_points_without_ply_roundtrip(
    monkeypatch,
) -> None:
    monkeypatch.setattr(rgbd_point_cloud, "_open3d_cloud", _fake_open3d_cloud)

    result = rgbd_point_cloud.build_cup_point_cloud(
        _camera_info(),
        _rgb_message(),
        _depth_message(),
        depth_trunc_m=3.0,
        cluster_eps_m=0.02,
        cluster_min_points=2,
        minimum_cup_points=2,
    )

    assert result.frame_id == "task_camera_frame"
    assert result.stamp_ns == 20_000_000
    assert result.points_xyz.shape[1] == 3
    assert result.colors_rgb.shape == result.points_xyz.shape
    assert np.isfinite(result.points_xyz).all()
    assert result.rgb8.shape == (2, 2, 3)
    assert result.full_points_xyz.shape == result.full_colors_rgb.shape
    assert result.cup_points_xyz.shape == result.cup_colors_rgb.shape
    assert result.full_point_count > result.cup_point_count > 0


def test_decode_rgb_rejects_padded_row_stride() -> None:
    with np.testing.assert_raises_regex(ValueError, "rgb step"):
        rgbd_point_cloud._decode_rgb(_rgb_message(step=7))


def test_decode_depth_rejects_padded_row_stride() -> None:
    with np.testing.assert_raises_regex(ValueError, "depth step"):
        rgbd_point_cloud._decode_depth(_depth_message(step=9))


def test_back_projects_depth_with_camera_intrinsics() -> None:
    from so101_demo.cli.rgbd_point_cloud import back_project_depth

    depth = np.array([[2.0, 2.0], [2.0, 2.0]], dtype=np.float32)
    points, pixel_rows, pixel_columns = back_project_depth(
        depth,
        fx=2.0,
        fy=2.0,
        cx=0.0,
        cy=0.0,
        depth_trunc_m=3.0,
    )

    np.testing.assert_allclose(
        points,
        np.array(
            [
                [0.0, 0.0, 2.0],
                [1.0, 0.0, 2.0],
                [0.0, 1.0, 2.0],
                [1.0, 1.0, 2.0],
            ]
        ),
    )
    np.testing.assert_array_equal(pixel_rows, np.array([0, 0, 1, 1]))
    np.testing.assert_array_equal(pixel_columns, np.array([0, 1, 0, 1]))


def test_orange_mask_keeps_cup_color_but_rejects_table_and_target() -> None:
    from so101_demo.cli.rgbd_point_cloud import orange_cup_mask

    rgb = np.array(
        [
            [
                [230, 130, 35],  # cup orange
                [92, 61, 36],  # dark brown table
                [255, 0, 0],  # red landing target
                [220, 220, 220],  # pale robot link
            ]
        ],
        dtype=np.uint8,
    )

    np.testing.assert_array_equal(
        orange_cup_mask(rgb),
        np.array([[True, False, False, False]]),
    )


def test_robust_center_uses_median_instead_of_outlier_sensitive_mean() -> None:
    from so101_demo.cli.rgbd_point_cloud import robust_center

    points = np.array(
        [
            [0.00, 0.00, 0.50],
            [0.02, 0.00, 0.50],
            [0.01, 0.01, 0.51],
            [100.0, 100.0, 100.0],
        ]
    )

    np.testing.assert_allclose(robust_center(points), np.array([0.015, 0.005, 0.505]))
    assert np.linalg.norm(points.mean(axis=0) - robust_center(points)) > 1.0


def test_largest_cluster_indices_rejects_noise_and_smaller_clusters() -> None:
    from so101_demo.cli.rgbd_point_cloud import largest_cluster_indices

    labels = np.array([-1, 2, 2, 7, 7, 7, -1], dtype=np.int32)

    np.testing.assert_array_equal(largest_cluster_indices(labels), np.array([3, 4, 5]))


def test_package_registers_rgbd_point_cloud_executable() -> None:
    package_root = Path(__file__).resolve().parents[1]
    setup_source = (package_root / "setup.py").read_text(encoding="utf-8")

    assert "rgbd_point_cloud = so101_demo.cli.rgbd_point_cloud:main" in setup_source
