from types import SimpleNamespace

import pytest


def _pose_message(*, frame_id: str = "camera_color_optical_frame"):
    return SimpleNamespace(
        header=SimpleNamespace(frame_id=frame_id, stamp=object()),
        pose=SimpleNamespace(
            position=SimpleNamespace(x=-0.184, y=-0.015, z=0.805),
            orientation=SimpleNamespace(x=0.0, y=0.0, z=0.0, w=1.0),
        ),
    )


def test_transforms_pose_from_message_frame_to_requested_target_frame() -> None:
    from so101_demo.cli.cup_pose_tf_demo import transform_pose_message

    message = _pose_message()
    query_time = object()
    transform = object()
    transformed = SimpleNamespace(header=SimpleNamespace(frame_id="world"))
    lookup_calls: list[tuple[object, ...]] = []
    apply_calls: list[tuple[object, ...]] = []

    def lookup_transform(*arguments):
        lookup_calls.append(arguments)
        return transform

    def apply_transform(*arguments):
        apply_calls.append(arguments)
        return transformed

    result = transform_pose_message(
        message,
        target_frame="world",
        query_time=query_time,
        lookup_transform=lookup_transform,
        apply_transform=apply_transform,
    )

    assert result is transformed
    assert lookup_calls == [("world", "camera_color_optical_frame", query_time)]
    assert apply_calls == [(message, transform)]


@pytest.mark.parametrize(
    ("source_frame", "target_frame", "error"),
    [
        ("", "world", "frame_id must be non-empty"),
        ("camera_color_optical_frame", "", "target_frame must be non-empty"),
    ],
)
def test_rejects_missing_source_or_target_frame(
    source_frame: str,
    target_frame: str,
    error: str,
) -> None:
    from so101_demo.cli.cup_pose_tf_demo import transform_pose_message

    with pytest.raises(ValueError, match=error):
        transform_pose_message(
            _pose_message(frame_id=source_frame),
            target_frame=target_frame,
            query_time=object(),
            lookup_transform=lambda *_: object(),
            apply_transform=lambda *_: object(),
        )


def test_package_registers_tf_demo_and_geometry_transform_dependency() -> None:
    from pathlib import Path

    package_root = Path(__file__).resolve().parents[1]
    setup_source = (package_root / "setup.py").read_text(encoding="utf-8")
    package_xml = (package_root / "package.xml").read_text(encoding="utf-8")

    assert "cup_pose_tf_demo = so101_demo.cli.cup_pose_tf_demo:main" in setup_source
    assert "<depend>tf2_geometry_msgs</depend>" in package_xml
