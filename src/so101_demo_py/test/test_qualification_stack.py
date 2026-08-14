from __future__ import annotations

import signal

from so101_demo.application import qualification_stack


def test_launch_children_own_process_groups_for_signal_forwarding(monkeypatch) -> None:
    calls = []

    class Child:
        pid = 4321

    monkeypatch.setattr(
        qualification_stack.subprocess,
        "Popen",
        lambda command, **kwargs: calls.append((command, kwargs)) or Child(),
    )

    children = qualification_stack.start_children([["ros2", "launch", "pkg", "file"]])

    assert len(children) == 1
    assert calls == [
        (["ros2", "launch", "pkg", "file"], {"start_new_session": True})
    ]


def test_signal_child_targets_its_whole_process_group(monkeypatch) -> None:
    signals = []
    child = type("Child", (), {"pid": 4321})()
    monkeypatch.setattr(
        qualification_stack.os,
        "killpg",
        lambda process_group_id, value: signals.append((process_group_id, value)),
    )

    qualification_stack.signal_child_group(child, signal.SIGINT)

    assert signals == [(4321, signal.SIGINT)]
