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
    from so101_demo.cli.cup_pose_subscriber import validate_pose_message

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
    from so101_demo.cli.cup_pose_subscriber import CupPoseValidationError, validate_pose_message

    with pytest.raises(CupPoseValidationError, match=error):
        validate_pose_message(message)


def test_formats_status_reports_as_one_terminal_line() -> None:
    from so101_demo.cli.cup_pose_subscriber import status_line

    report = status_line(
        "ERROR",
        failure="CUP_POSE_INVALID",
        message="frame_id must be\nnon-empty",
    )

    assert report == "status=ERROR failure=CUP_POSE_INVALID message=frame_id must be non-empty"
    assert "\n" not in report


def test_listens_to_multiple_messages_until_the_inter_message_timeout() -> None:
    from so101_demo.cli.cup_pose_subscriber import (
        CupPoseTimeoutError,
        listen_for_pose_messages,
    )

    messages = iter(
        [
            _pose_message(position=(9.0, 8.0, 7.0)),
            _pose_message(position=(6.0, 5.0, 4.0)),
        ]
    )
    accepted: list[object] = []
    now = [0.0]

    with pytest.raises(
        CupPoseTimeoutError,
        match="no /cup_pose message received within 1.0 seconds",
    ):
        listen_for_pose_messages(
            receive=lambda: next(messages, None),
            spin_once=lambda timeout: now.__setitem__(0, now[0] + timeout),
            on_pose=accepted.append,
            timeout_s=1.0,
            monotonic=lambda: now[0],
        )

    assert accepted == [
        ("camera_link", (9.0, 8.0, 7.0), (0.0, 0.0, 0.5, 0.5)),
        ("camera_link", (6.0, 5.0, 4.0), (0.0, 0.0, 0.5, 0.5)),
    ]


def test_listener_reports_an_invalid_pose_and_continues_to_the_next_message() -> None:
    from so101_demo.cli.cup_pose_subscriber import (
        CupPoseTimeoutError,
        listen_for_pose_messages,
    )

    messages = iter([_pose_message(frame_id=""), _pose_message(position=(6.0, 5.0, 4.0))])
    accepted: list[object] = []
    invalid_messages: list[str] = []
    now = [0.0]

    with pytest.raises(CupPoseTimeoutError):
        listen_for_pose_messages(
            receive=lambda: next(messages, None),
            spin_once=lambda timeout: now.__setitem__(0, now[0] + timeout),
            on_pose=accepted.append,
            on_invalid=lambda error: invalid_messages.append(str(error)),
            timeout_s=1.0,
            monotonic=lambda: now[0],
        )

    assert invalid_messages == ["frame_id must be non-empty"]
    assert accepted == [("camera_link", (6.0, 5.0, 4.0), (0.0, 0.0, 0.5, 0.5))]


def test_listener_reports_timeout_when_no_message_arrives() -> None:
    from so101_demo.cli.cup_pose_subscriber import CupPoseTimeoutError, listen_for_pose_messages

    clock = iter((0.0, 0.0, 0.1, 1.0))

    with pytest.raises(
        CupPoseTimeoutError,
        match="no /cup_pose message received within 1.0 seconds",
    ):
        listen_for_pose_messages(
            receive=lambda: None,
            spin_once=lambda _: None,
            on_pose=lambda _: None,
            timeout_s=1.0,
            monotonic=clock.__next__,
        )


@pytest.mark.parametrize(
    ("context_ok", "expected_shutdown_calls"),
    [(True, 1), (False, 0)],
)
def test_main_exits_cleanly_on_sigint_without_double_shutting_down_rclpy(
    monkeypatch,
    capsys,
    context_ok: bool,
    expected_shutdown_calls: int,
) -> None:
    import sys
    from types import ModuleType, SimpleNamespace

    from so101_demo.cli import cup_pose_subscriber

    node = SimpleNamespace(
        create_subscription=lambda *_: object(),
        destroy_node=lambda: None,
    )
    shutdown_calls: list[None] = []
    rclpy = SimpleNamespace(
        init=lambda: None,
        create_node=lambda _: node,
        spin_once=lambda *_args, **_kwargs: (_ for _ in ()).throw(KeyboardInterrupt()),
        ok=lambda: context_ok,
        shutdown=lambda: shutdown_calls.append(None),
    )
    geometry_msgs = ModuleType("geometry_msgs")
    geometry_msgs_msg = ModuleType("geometry_msgs.msg")
    geometry_msgs_msg.PoseStamped = object
    geometry_msgs.msg = geometry_msgs_msg
    monkeypatch.setitem(sys.modules, "rclpy", rclpy)
    monkeypatch.setitem(sys.modules, "geometry_msgs", geometry_msgs)
    monkeypatch.setitem(sys.modules, "geometry_msgs.msg", geometry_msgs_msg)

    assert cup_pose_subscriber.main(["--timeout-s", "1"]) == 0
    assert capsys.readouterr().out == "status=STOPPED reason=SIGINT\n"
    assert len(shutdown_calls) == expected_shutdown_calls


def test_setup_registers_the_cup_pose_subscriber_executable() -> None:
    from pathlib import Path

    source = Path("src/so101_demo_py/setup.py").read_text(encoding="utf-8")

    assert "cup_pose_subscriber = so101_demo.cli.cup_pose_subscriber:main" in source
