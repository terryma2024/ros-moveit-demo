import json
import signal
from pathlib import Path

import pytest


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


# --------------------------------------------------------------------------------------
# Owner records (Task 6): the boundary that calls Popen writes the STATION record
# --------------------------------------------------------------------------------------


def _owner_environment(tmp_path: Path, **overrides: str) -> dict:
    environment = {
        "SO101_OWNER_TREE_ROOT": str(tmp_path / "owner-tree"),
        "SO101_OWNER_CAMPAIGN_ID": "campaign-1",
        "SO101_OWNER_BATCH_ID": "batch-1",
        "SO101_OWNER_GENERATION": "2",
    }
    environment.update(overrides)
    return environment


def _station_config(tmp_path: Path, roles: tuple = ("task-station",)):
    from so101_demo.runtime.task_stack import PersistentStackConfig, StackProcessSpec

    return PersistentStackConfig(
        session_id="sim-a",
        headless=False,
        evidence_root=tmp_path,
        processes=tuple(StackProcessSpec(role, ("owner", role)) for role in roles),
    )


def _owner_directory(tmp_path: Path) -> Path:
    return tmp_path / "owner-tree" / "campaign-1" / "batch-1"


def test_a_station_intent_is_durable_before_popen_and_confirmed_after_it(tmp_path: Path) -> None:
    from so101_demo.runtime.task_stack import PersistentTaskStack

    directory = _owner_directory(tmp_path)
    observed = {}

    def popen(argv, **kwargs):
        observed["intents"] = sorted(path.name for path in directory.glob("*.intent.json"))
        observed["confirmed"] = sorted(path.name for path in directory.glob("*.confirmed.json"))
        observed["parts"] = sorted(path.name for path in directory.glob("*.part"))
        observed["env"] = dict(kwargs["env"])
        return _Child(4321, argv[-1], [])

    stack = PersistentTaskStack(
        popen=popen,
        killpg=lambda _pid, _signal: None,
        owner_environment=_owner_environment(tmp_path, **{"SO101_OWNER_TOKEN": "worker-abc"}),
        owner_identity_reader=lambda _pid: (4321, 987_654_321),
    )
    stack.start(_station_config(tmp_path))
    stack.shutdown()

    assert len(observed["intents"]) == 1, "the intent is written before Popen"
    assert observed["confirmed"] == [], "no confirmation exists yet when Popen is called"
    assert observed["parts"] == [], "an atomic write never leaves a .part behind"
    intent = json.loads((directory / observed["intents"][0]).read_text(encoding="utf-8"))
    assert intent["schema"] == "so101.owner-intent/1"
    assert intent["role"] == "STATION"
    assert intent["generation"] == 2
    assert intent["parent_spawn_token"] == "worker-abc"
    assert intent["expected_executable"] == "owner"
    assert observed["env"]["SO101_OWNER_TOKEN"] == intent["spawn_token"]
    assert observed["env"]["SO101_OWNER_PARENT_TOKEN"] == "worker-abc"

    confirmed = list(directory.glob("*.confirmed.json"))
    assert [path.name for path in confirmed] == [f"{intent['spawn_token']}.confirmed.json"]
    document = json.loads(confirmed[0].read_text(encoding="utf-8"))
    assert (document["pid"], document["pgid"], document["started_ticks"]) == (
        4321,
        4321,
        987_654_321,
    )
    assert document["command_sha256"] == intent["argv_sha256"]
    assert not list(directory.glob("*.abandoned.json"))


def test_a_station_spawn_without_an_owner_context_is_unchanged(tmp_path: Path) -> None:
    from so101_demo.runtime.task_stack import PersistentTaskStack

    observed = {}

    def popen(argv, **kwargs):
        observed["argv"] = list(argv)
        observed["env"] = dict(kwargs["env"])
        observed["start_new_session"] = kwargs["start_new_session"]
        return _Child(5001, argv[-1], [])

    stack = PersistentTaskStack(
        popen=popen, killpg=lambda _pid, _signal: None, owner_environment={}
    )
    stack.start(_station_config(tmp_path), environment={"ROS_DOMAIN_ID": "7"})
    stack.shutdown()

    assert observed["argv"] == ["owner", "task-station"]
    assert observed["start_new_session"] is True
    assert observed["env"]["ROS_DOMAIN_ID"] == "7"
    assert [name for name in observed["env"] if name.startswith("SO101_OWNER_")] == []
    assert list(tmp_path.rglob("*")) == [], "an inert context writes nothing"


def test_the_owner_context_is_read_from_the_process_environment(
    tmp_path: Path, monkeypatch
) -> None:
    from so101_demo.runtime.task_stack import PersistentTaskStack

    for name, value in _owner_environment(
        tmp_path, **{"SO101_OWNER_TOKEN": "campaign-abc"}
    ).items():
        monkeypatch.setenv(name, value)

    stack = PersistentTaskStack(
        popen=lambda argv, **_kwargs: _Child(6001, argv[-1], []),
        killpg=lambda _pid, _signal: None,
        owner_identity_reader=lambda _pid: (6001, 111),
    )
    stack.start(_station_config(tmp_path))
    stack.shutdown()

    intents = list(_owner_directory(tmp_path).glob("*.intent.json"))
    assert len(intents) == 1
    intent = json.loads(intents[0].read_text(encoding="utf-8"))
    assert intent["parent_spawn_token"] == "campaign-abc"


def test_an_unreadable_station_identity_abandons_the_record_and_keeps_the_cleanup(
    tmp_path: Path,
) -> None:
    from so101_demo.runtime.owner_records import OwnerRecordError
    from so101_demo.runtime.task_stack import PersistentTaskStack

    signals = []
    stack = PersistentTaskStack(
        popen=lambda argv, **_kwargs: _Child(7001, argv[-1], []),
        killpg=lambda pid, number: signals.append((pid, number)),
        owner_environment=_owner_environment(tmp_path),
        owner_identity_reader=lambda _pid: None,
        owner_confirm_deadline_s=0.0,
    )
    with pytest.raises(OwnerRecordError) as refused:
        stack.start(_station_config(tmp_path))

    assert refused.value.code == "OWNER_CONFIRMATION_UNREADABLE"
    markers = list(_owner_directory(tmp_path).glob("*.abandoned.json"))
    assert len(markers) == 1
    assert json.loads(markers[0].read_text(encoding="utf-8"))["reason"] == (
        "OWNER_CONFIRMATION_UNREADABLE"
    )
    assert signals == [(7001, signal.SIGTERM)], "the existing failure cleanup is untouched"
    assert list(_owner_directory(tmp_path).glob("*.confirmed.json")) == []


def test_a_failing_station_spawn_abandons_its_intent(tmp_path: Path) -> None:
    from so101_demo.runtime.task_stack import PersistentTaskStack

    def popen(_argv, **_kwargs):
        raise OSError("station could not be spawned")

    stack = PersistentTaskStack(
        popen=popen,
        killpg=lambda _pid, _signal: None,
        owner_environment=_owner_environment(tmp_path),
    )
    with pytest.raises(OSError, match="could not be spawned"):
        stack.start(_station_config(tmp_path))

    assert len(list(_owner_directory(tmp_path).glob("*.intent.json"))) == 1
    markers = list(_owner_directory(tmp_path).glob("*.abandoned.json"))
    assert len(markers) == 1
    assert json.loads(markers[0].read_text(encoding="utf-8"))["reason"] == "SPAWN_FAILED"
    assert list(_owner_directory(tmp_path).glob("*.confirmed.json")) == []


def test_exactly_one_station_intent_is_written_per_station_spawn(tmp_path: Path) -> None:
    """Two intents for one station spawn would make the owner tree ambiguous."""

    from so101_demo.runtime.task_stack import PersistentTaskStack

    directory = _owner_directory(tmp_path)
    children = []

    def popen(argv, **_kwargs):
        child = _Child(8001 + len(children), argv[-1], [])
        children.append(child)
        return child

    stack = PersistentTaskStack(
        popen=popen,
        killpg=lambda _pid, _signal: None,
        owner_environment=_owner_environment(tmp_path, **{"SO101_OWNER_TOKEN": "worker-abc"}),
        owner_identity_reader=lambda pid: (pid, 5000 + pid),
    )
    stack.start(_station_config(tmp_path, roles=("task-station", "station")))
    stack.shutdown()

    intents = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in directory.glob("*.intent.json")
    ]
    assert len(intents) == 2, "one intent per station spawn, never two"
    assert {intent["role"] for intent in intents} == {"STATION"}
    assert len({intent["spawn_token"] for intent in intents}) == 2
    assert len(list(directory.glob("*.confirmed.json"))) == 2
    assert not list(directory.glob("*.abandoned.json"))

    # The Worker that owns the station cooperates instead of recording: it contributes the
    # parent-token context and nothing else, so this source check is the other half of the proof.
    worker = (
        Path(__file__).resolve().parents[1] / "src" / "cli" / "macos_w2_worker.py"
    ).read_text(encoding="utf-8")
    assert "OwnerSpawnRecorder" not in worker
    assert "SO101_OWNER_PARENT_TOKEN" in worker


def test_a_stack_role_outside_the_owner_vocabulary_is_not_recorded(tmp_path: Path) -> None:
    from so101_demo.runtime.task_stack import PersistentTaskStack

    stack = PersistentTaskStack(
        popen=lambda argv, **_kwargs: _Child(9001, argv[-1], []),
        killpg=lambda _pid, _signal: None,
        owner_environment=_owner_environment(tmp_path),
    )
    stack.start(_station_config(tmp_path, roles=("mujoco",)))
    stack.shutdown()

    assert not (tmp_path / "owner-tree").exists()
