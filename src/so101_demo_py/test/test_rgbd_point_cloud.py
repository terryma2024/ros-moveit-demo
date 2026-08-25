from pathlib import Path

import numpy as np


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
