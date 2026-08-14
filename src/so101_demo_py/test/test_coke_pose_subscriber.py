from types import SimpleNamespace

import pytest


def _pose_message(
    *,
    frame_id: str = "camera_link",
    position: tuple[float, float, float] = (0.12, -0.34, 0.56),
    orientation: tuple[float, float, float, float] = (0.0, 0.0, 0.5, 0.5),
):
    return SimpleNamespace(
        header=SimpleNamespace(frame_id=frame_id),
        pose=SimpleNamespace(
            position=SimpleNamespace(x=position[0], y=position[1], z=position[2]),
            orientation=SimpleNamespace(
                x=orientation[0],
                y=orientation[1],
                z=orientation[2],
                w=orientation[3],
            ),
        ),
    )


def test_validates_complete_pose_stamped_message_without_replacing_its_values() -> None:
    from so101_demo.cli.coke_pose_subscriber import validate_pose_message

    message = _pose_message()

    assert validate_pose_message(message) == (
        "camera_link",
        (0.12, -0.34, 0.56),
        (0.0, 0.0, 0.5, 0.5),
    )


@pytest.mark.parametrize(
    ("message", "error"),
    [
        (_pose_message(frame_id=""), "frame_id must be non-empty"),
        (_pose_message(position=(float("nan"), 0.0, 0.0)), "position.x must be finite"),
        (_pose_message(orientation=(0.0, float("inf"), 0.0, 0.0)), "orientation.y must be finite"),
        (_pose_message(orientation=(0.0, 0.0, 0.0, 0.0)), "quaternion must be non-zero"),
    ],
)
def test_rejects_invalid_pose_stamped_message(message, error: str) -> None:
    from so101_demo.cli.coke_pose_subscriber import CokePoseValidationError, validate_pose_message

    with pytest.raises(CokePoseValidationError, match=error):
        validate_pose_message(message)


def test_wait_returns_the_received_pose_and_never_falls_back_to_an_internal_pose() -> None:
    from so101_demo.cli.coke_pose_subscriber import wait_for_pose_message

    message = _pose_message(position=(9.0, 8.0, 7.0))
    received = [None, message]
    spin_calls: list[float] = []

    result = wait_for_pose_message(
        receive=lambda: received.pop(0) if received else message,
        spin_once=spin_calls.append,
        timeout_s=1.0,
        monotonic=iter((0.0, 0.0, 0.1, 0.1)).__next__,
    )

    assert result == ("camera_link", (9.0, 8.0, 7.0), (0.0, 0.0, 0.5, 0.5))
    assert spin_calls == [0.1]


def test_wait_reports_timeout_when_no_message_arrives() -> None:
    from so101_demo.cli.coke_pose_subscriber import CokePoseTimeoutError, wait_for_pose_message

    clock = iter((0.0, 0.0, 0.1, 1.0))

    with pytest.raises(
        CokePoseTimeoutError,
        match="no /coke_pose message received within 1.0 seconds",
    ):
        wait_for_pose_message(
            receive=lambda: None,
            spin_once=lambda _: None,
            timeout_s=1.0,
            monotonic=clock.__next__,
        )


def test_setup_registers_the_coke_pose_subscriber_executable() -> None:
    from pathlib import Path

    source = Path("src/so101_demo_py/setup.py").read_text(encoding="utf-8")

    assert "coke_pose_subscriber = so101_demo.cli.coke_pose_subscriber:main" in source
