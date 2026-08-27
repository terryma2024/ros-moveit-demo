import signal
from pathlib import Path


class _Child:
    def __init__(self, pid: int, role: str, log: list) -> None:
        self.pid = pid
        self.role = role
        self.log = log
        self.wait_calls = 0

    def poll(self):
        return None

    def wait(self, timeout: float):
        self.wait_calls += 1
        self.log.append(("wait", self.role, timeout))
        return 0


def test_stack_shutdown_is_reverse_dependency_order_and_preserves_dyld(
    tmp_path: Path,
) -> None:
    from so101_demo.runtime.task_stack import (
        PersistentStackConfig,
        PersistentTaskStack,
        StackProcessSpec,
    )

    calls = []
    children = []

    def popen(argv, **kwargs):
        role = argv[-1]
        calls.append((argv, kwargs))
        child = _Child(100 + len(children), role, calls)
        children.append(child)
        return child

    signals = []
    stack = PersistentTaskStack(popen=popen, killpg=lambda pid, sig: signals.append((pid, sig)))
    config = PersistentStackConfig(
        session_id="sim-a",
        headless=False,
        evidence_root=tmp_path,
        processes=tuple(
            StackProcessSpec(role, ("owner", role))
            for role in ("mujoco", "robot-state", "controllers", "move-group", "teleop")
        ),
    )
    stack.start(config, environment={"DYLD_LIBRARY_PATH": "/candidate/lib"})
    stack.shutdown()

    assert [call[0][-1] for call in calls if call[0] != "wait"][:5] == [
        "mujoco",
        "robot-state",
        "controllers",
        "move-group",
        "teleop",
    ]
    assert [pid for pid, sig in signals if sig == signal.SIGINT] == [104, 103, 102, 101, 100]
    assert all(call[1]["start_new_session"] for call in calls if isinstance(call[0], list))
    assert all(
        call[1]["env"]["DYLD_LIBRARY_PATH"] == "/candidate/lib"
        for call in calls
        if isinstance(call[0], list)
    )


def test_stack_escalates_only_owned_process_group_after_timeout(tmp_path: Path) -> None:
    from subprocess import TimeoutExpired

    from so101_demo.runtime.task_stack import (
        PersistentStackConfig,
        PersistentTaskStack,
        StackProcessSpec,
    )

    class SlowChild(_Child):
        def wait(self, timeout):
            self.wait_calls += 1
            if self.wait_calls == 1:
                raise TimeoutExpired("owner", timeout)
            return 0

    child = SlowChild(501, "mujoco", [])
    signals = []
    stack = PersistentTaskStack(
        popen=lambda *_args, **_kwargs: child,
        killpg=lambda pid, sig: signals.append((pid, sig)),
        interrupt_timeout_s=1.0,
        terminate_timeout_s=0.5,
    )
    stack.start(
        PersistentStackConfig(
            "sim-a", False, tmp_path, (StackProcessSpec("mujoco", ("owner",)),)
        )
    )
    stack.shutdown()
    assert signals == [(501, signal.SIGINT), (501, signal.SIGTERM)]
