from types import SimpleNamespace

import pytest


def _message(frame_id: str = "world"):
    return SimpleNamespace(header=SimpleNamespace(frame_id=frame_id))


def test_invalid_messages_do_not_extend_absolute_acquisition_deadline() -> None:
    from so101_demo.ports.cup_pose_source import CupPoseSourceError, acquire_one

    now = [0.0]
    invalid = _message("")
    reports: list[str] = []

    with pytest.raises(CupPoseSourceError) as captured:
        acquire_one(
            receive=lambda: invalid,
            spin_once=lambda duration: now.__setitem__(0, now[0] + duration),
            convert=lambda _: (_ for _ in ()).throw(ValueError("bad frame")),
            on_invalid=lambda error: reports.append(str(error)),
            timeout_s=0.25,
            monotonic=lambda: now[0],
        )

    assert captured.value.code == "CUP_POSE_INVALID"
    assert now[0] == pytest.approx(0.25)
    assert reports


def test_no_message_before_deadline_is_timeout() -> None:
    from so101_demo.ports.cup_pose_source import CupPoseSourceError, acquire_one

    now = [0.0]
    with pytest.raises(CupPoseSourceError) as captured:
        acquire_one(
            receive=lambda: None,
            spin_once=lambda duration: now.__setitem__(0, now[0] + duration),
            convert=lambda value: value,
            on_invalid=lambda _: None,
            timeout_s=0.2,
            monotonic=lambda: now[0],
        )

    assert captured.value.code == "CUP_POSE_TIMEOUT"


def test_returns_first_valid_value_and_stops() -> None:
    from so101_demo.ports.cup_pose_source import acquire_one

    messages = iter((_message(""), _message("world")))
    reports: list[str] = []

    result = acquire_one(
        receive=lambda: next(messages, None),
        spin_once=lambda _: None,
        convert=lambda value: value.header.frame_id
        if value.header.frame_id
        else (_ for _ in ()).throw(ValueError("bad frame")),
        on_invalid=lambda error: reports.append(str(error)),
        timeout_s=1.0,
        monotonic=lambda: 0.0,
    )

    assert result == "world"
    assert reports == ["bad frame"]
