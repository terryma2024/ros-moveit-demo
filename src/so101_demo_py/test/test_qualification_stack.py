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


def test_graceful_shutdown_signals_only_launch_owners() -> None:
    signals = []

    class Child:
        def poll(self):
            return None

        def send_signal(self, value):
            signals.append(value)

    qualification_stack.request_graceful_shutdown([Child(), Child()])

    assert signals == [signal.SIGINT, signal.SIGINT]


def test_macos_ros2_launch_uses_current_python_to_preserve_dyld(monkeypatch) -> None:
    monkeypatch.setattr(qualification_stack.sys, "platform", "darwin")
    monkeypatch.setattr(
        qualification_stack.shutil,
        "which",
        lambda executable: "/ros/install/ros2" if executable == "ros2" else None,
    )

    assert qualification_stack.ros2_command("launch", "pkg", "file") == [
        qualification_stack.sys.executable,
        "/ros/install/ros2",
        "launch",
        "pkg",
        "file",
    ]
