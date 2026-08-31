from __future__ import annotations

import builtins
from types import SimpleNamespace

import numpy as np
import pytest

from so101_demo.application.object_pose import (
    LocalizationError,
    RgbdLocalizer,
    _default_outlier_cleaner,
)
from so101_demo.cli.rgbd_point_cloud import build_mask_point_cloud
from so101_demo.core.detection import DetectionCandidate


def _header(*, stamp_ns: int = 7, frame_id: str = "task_camera_frame"):
    return SimpleNamespace(
        stamp=SimpleNamespace(sec=stamp_ns // 1_000_000_000, nanosec=stamp_ns % 1_000_000_000),
        frame_id=frame_id,
    )


def _camera_info(
    *,
    width: int = 3,
    height: int = 2,
    stamp_ns: int = 7,
    frame_id: str = "task_camera_frame",
    fx: float = 1.0,
    fy: float = 1.0,
    cx: float = 0.0,
    cy: float = 0.0,
):
    return SimpleNamespace(
        header=_header(stamp_ns=stamp_ns, frame_id=frame_id),
        width=width,
        height=height,
        k=[fx, 0.0, cx, 0.0, fy, cy, 0.0, 0.0, 1.0],
    )


def _depth_message(
    values: np.ndarray,
    *,
    stamp_ns: int = 7,
    frame_id: str = "task_camera_frame",
):
    depth = np.asarray(values, dtype="<f4")
    height, width = depth.shape
    return SimpleNamespace(
        header=_header(stamp_ns=stamp_ns, frame_id=frame_id),
        width=width,
        height=height,
        encoding="32FC1",
        step=width * 4,
        is_bigendian=False,
        data=depth.tobytes(),
    )


def _candidate(
    mask: np.ndarray,
    *,
    stamp_ns: int = 7,
    frame_id: str = "task_camera_frame",
) -> DetectionCandidate:
    height, width = mask.shape
    return DetectionCandidate(
        instance_id="cup-0",
        class_id="plastic_cup",
        confidence=0.9,
        bbox_xyxy=(0.0, 0.0, float(width), float(height)),
        mask=mask,
        source_stamp_ns=stamp_ns,
        source_frame_id=frame_id,
        image_width=width,
        image_height=height,
    )


def _identity_transform():
    return SimpleNamespace(
        transform=SimpleNamespace(
            translation=SimpleNamespace(x=0.0, y=0.0, z=0.0),
            rotation=SimpleNamespace(x=0.0, y=0.0, z=0.0, w=1.0),
        )
    )


def _partial_cylinder() -> np.ndarray:
    angles = np.linspace(-1.1, 1.2, 80)
    center_xy = np.array([0.02, -0.28])
    radius = 0.04
    xy = center_xy + radius * np.column_stack((np.cos(angles), np.sin(angles)))
    return np.column_stack((xy, np.linspace(0.13, 0.21, len(xy))))


def test_build_mask_point_cloud_back_projects_only_valid_selected_depth() -> None:
    mask = np.array([[True, True, False], [True, True, True]], dtype=bool)
    depth = np.array([[0.5, np.nan, 0.0], [2.0, 4.0, 1.0]], dtype=np.float32)

    cloud = build_mask_point_cloud(
        _candidate(mask),
        _camera_info(),
        _depth_message(depth),
        depth_trunc_m=3.0,
    )

    np.testing.assert_allclose(
        cloud,
        np.array(
            [
                [0.0, 0.0, 0.5],
                [0.0, 2.0, 2.0],
                [2.0, 1.0, 1.0],
            ]
        ),
    )


@pytest.mark.parametrize(
    ("camera_overrides", "depth_overrides"),
    [
        ({"stamp_ns": 8}, {}),
        ({"frame_id": "other"}, {}),
        ({"width": 4}, {}),
        ({}, {"stamp_ns": 8}),
        ({}, {"frame_id": "other"}),
    ],
)
def test_build_mask_point_cloud_rejects_misaligned_rgbd_contract(
    camera_overrides: dict[str, object], depth_overrides: dict[str, object]
) -> None:
    mask = np.ones((2, 3), dtype=bool)
    with pytest.raises(ValueError, match="candidate, CameraInfo, and depth"):
        build_mask_point_cloud(
            _candidate(mask),
            _camera_info(**camera_overrides),
            _depth_message(np.ones((2, 3)), **depth_overrides),
            depth_trunc_m=3.0,
        )


def test_localizer_uses_exact_stamp_transform_and_fits_cup_geometry() -> None:
    lookup_calls: list[tuple[str, str, int]] = []

    def lookup(target: str, source: str, stamp_ns: int):
        lookup_calls.append((target, source, stamp_ns))
        return _identity_transform()

    localizer = RgbdLocalizer(
        depth_trunc_m=3.0,
        minimum_cup_points=50,
        cluster_eps_m=0.02,
        cluster_min_points=5,
        table_top_z=0.12,
        cup_height=0.09,
        expected_radius_m=0.04,
        radius_tolerance_m=0.01,
        workspace_min_xyz=(-0.2, -0.5, 0.1),
        workspace_max_xyz=(0.2, -0.1, 0.3),
        point_cloud_builder=lambda *_args, **_kwargs: _partial_cylinder(),
        outlier_cleaner=lambda points, *_args, **_kwargs: points,
    )

    result = localizer.localize(
        _candidate(np.ones((2, 3), dtype=bool)),
        _camera_info(),
        _depth_message(np.ones((2, 3))),
        lookup,
    )

    assert lookup_calls == [("world", "task_camera_frame", 7)]
    np.testing.assert_allclose(result.center_world_xyz, (0.02, -0.28, 0.165), atol=1e-6)
    assert result.fitted_radius_m == pytest.approx(0.04, abs=1e-6)
    assert result.valid_depth_point_count == 80
    assert not result.points_world.flags.writeable


def test_localizer_warm_up_primes_outlier_cleanup_once() -> None:
    calls: list[np.ndarray] = []

    def cleaner(points: np.ndarray, eps_m: float, min_points: int) -> np.ndarray:
        calls.append(np.array(points, copy=True))
        assert eps_m == 0.02
        assert min_points == 5
        return points

    clock = iter([1_000_000_000, 1_007_000_000])
    localizer = RgbdLocalizer(outlier_cleaner=cleaner)

    assert localizer.warm_up(monotonic_ns=clock.__next__) == pytest.approx(7.0)
    assert localizer.warm_up(monotonic_ns=lambda: pytest.fail("warm-up repeated")) == (
        pytest.approx(7.0)
    )
    assert len(calls) == 1
    assert calls[0].shape == (8, 3)
    assert np.isfinite(calls[0]).all()


def test_default_outlier_cleanup_has_no_open3d_runtime_dependency(monkeypatch) -> None:
    main_cluster = np.column_stack(
        (
            np.linspace(-0.008, 0.008, 25),
            np.zeros(25),
            np.full(25, 0.5),
        )
    )
    secondary_cluster = np.column_stack(
        (
            np.linspace(0.192, 0.208, 8),
            np.full(8, 0.2),
            np.full(8, 0.7),
        )
    )
    points = np.vstack((main_cluster, secondary_cluster))
    original_import = builtins.__import__

    def reject_open3d(name, *args, **kwargs):
        if name == "open3d" or name.startswith("open3d."):
            raise ImportError("Open3D intentionally unavailable")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", reject_open3d)

    cleaned = _default_outlier_cleaner(points, 0.02, 5)

    np.testing.assert_allclose(cleaned, main_cluster)


def test_default_outlier_cleanup_rejects_only_isolated_voxels() -> None:
    isolated = np.column_stack(
        (
            np.arange(8, dtype=np.float64) * 0.1,
            np.zeros(8),
            np.full(8, 0.5),
        )
    )

    cleaned = _default_outlier_cleaner(isolated, 0.02, 5)

    assert cleaned.shape == (0, 3)


def test_localizer_rejects_insufficient_depth_before_tf_lookup() -> None:
    calls: list[object] = []
    localizer = RgbdLocalizer(
        minimum_cup_points=50,
        point_cloud_builder=lambda *_args, **_kwargs: np.zeros((3, 3)),
    )

    with pytest.raises(LocalizationError, match="DEPTH_INVALID") as caught:
        localizer.localize(
            _candidate(np.ones((2, 3), dtype=bool)),
            _camera_info(),
            _depth_message(np.ones((2, 3))),
            lambda *_args: calls.append(object()),
        )

    assert caught.value.code == "DEPTH_INVALID"
    assert calls == []


def test_localizer_maps_tf_failure_and_does_not_return_pose() -> None:
    localizer = RgbdLocalizer(
        minimum_cup_points=50,
        point_cloud_builder=lambda *_args, **_kwargs: _partial_cylinder(),
        outlier_cleaner=lambda points, *_args, **_kwargs: points,
    )

    def failed_lookup(*_args):
        raise RuntimeError("missing transform")

    with pytest.raises(LocalizationError, match="TF_UNAVAILABLE"):
        localizer.localize(
            _candidate(np.ones((2, 3), dtype=bool)),
            _camera_info(),
            _depth_message(np.ones((2, 3))),
            failed_lookup,
        )


def test_localizer_rejects_wrong_radius_or_out_of_workspace_geometry() -> None:
    angles = np.linspace(-1.0, 1.0, 80)
    wrong_radius = np.column_stack(
        (0.10 * np.cos(angles), -0.28 + 0.10 * np.sin(angles), np.full(80, 0.18))
    )
    for points, expected in [
        (wrong_radius, "fitted radius"),
        (_partial_cylinder() + np.array([1.0, 0.0, 0.0]), "workspace"),
    ]:
        localizer = RgbdLocalizer(
            minimum_cup_points=50,
            point_cloud_builder=lambda *_args, value=points, **_kwargs: value,
            outlier_cleaner=lambda values, *_args, **_kwargs: values,
        )
        with pytest.raises(LocalizationError, match="GEOMETRY_REJECTED") as caught:
            localizer.localize(
                _candidate(np.ones((2, 3), dtype=bool)),
                _camera_info(),
                _depth_message(np.ones((2, 3))),
                lambda *_args: _identity_transform(),
            )
        assert expected in caught.value.detail
