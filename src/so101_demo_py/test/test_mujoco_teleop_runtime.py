from types import SimpleNamespace
import pytest


def test_transactional_reset_returns_the_validated_joint_sample(monkeypatch) -> None:
    from so101_demo.backends.mujoco import teleop_runtime
    from so101_demo.core.simulation.types import ResetReceipt

    nodes = []

    class Node:
        def destroy_node(self):
            self.destroyed = True

    def create_node(_name):
        node = Node()
        node.destroyed = False
        nodes.append(node)
        return node

    joints = (0.001, -0.001, 0.0, 0.0, 0.0, 0.0)

    class Services:
        def __init__(self, *_args, **_kwargs):
            pass

        def latest_joint_positions(self):
            return joints

    receipt = ResetReceipt(4, 5, "task_start", 0, "session-a")

    class Resetter:
        def __init__(self, services, *_args, **_kwargs):
            self.services = services

        def reset(self, keyframe, overrides):
            assert keyframe == "task_start"
            assert overrides == ()
            return receipt

    monkeypatch.setattr(
        teleop_runtime,
        "rclpy",
        SimpleNamespace(
            init=lambda: None,
            create_node=create_node,
            shutdown=lambda: None,
            spin_once=lambda *_args, **_kwargs: None,
        ),
    )
    monkeypatch.setattr(teleop_runtime, "MujocoRosClient", Services)
    monkeypatch.setattr(
        teleop_runtime,
        "MujocoWorldObserver",
        lambda *_args, **_kwargs: object(),
    )
    monkeypatch.setattr(teleop_runtime, "MujocoResetClient", Resetter)

    result = teleop_runtime.transactional_reset("session-a")

    assert result.receipt is receipt
    assert result.new_epoch == 5
    assert result.joint_positions == joints
    assert all(node.destroyed for node in nodes)


def test_pause_snapshot_accepts_fresh_already_paused_evidence(monkeypatch) -> None:
    from so101_demo.backends.mujoco import teleop_runtime

    class Future:
        def done(self):
            return True

        def result(self):
            return SimpleNamespace(success=False)

    class Client:
        def wait_for_service(self, *, timeout_sec):
            assert timeout_sec == 1.0
            return True

        def call_async(self, request):
            assert request.paused is True
            return Future()

    node = SimpleNamespace(create_client=lambda *_args: Client())
    evidence = SimpleNamespace(paused=True)
    observer = SimpleNamespace(publisher_count=1, snapshot=lambda: evidence)
    monkeypatch.setattr(
        teleop_runtime,
        "rclpy",
        SimpleNamespace(ok=lambda: True, spin_once=lambda *_args, **_kwargs: None),
    )

    assert teleop_runtime._pause_snapshot(node, observer, 1.0) is evidence


def test_pause_snapshot_retries_idempotent_request_after_volatile_frame_loss(
    monkeypatch,
) -> None:
    from so101_demo.backends.mujoco import teleop_runtime
    from so101_demo.backends.mujoco.observer import EvidenceStale

    clock = [0.0]

    def monotonic():
        clock[0] += 0.01
        return clock[0]

    class Future:
        def done(self):
            return True

        def result(self):
            return SimpleNamespace(success=True)

    class Client:
        calls = 0

        def wait_for_service(self, *, timeout_sec):
            assert timeout_sec == 1.0
            return True

        def call_async(self, request):
            assert request.paused is True
            self.calls += 1
            return Future()

    client = Client()
    node = SimpleNamespace(create_client=lambda *_args: client)
    evidence = SimpleNamespace(paused=True)

    def snapshot():
        if client.calls < 2:
            raise EvidenceStale("first best-effort snapshot was lost")
        return evidence

    observer = SimpleNamespace(publisher_count=1, snapshot=snapshot)
    monkeypatch.setattr(teleop_runtime.time, "monotonic", monotonic)
    monkeypatch.setattr(
        teleop_runtime,
        "rclpy",
        SimpleNamespace(ok=lambda: True, spin_once=lambda *_args, **_kwargs: None),
    )

    assert teleop_runtime._pause_snapshot(node, observer, 1.0) is evidence
    assert client.calls == 2


def _failure_harness(monkeypatch, *, response, snapshot, retained=(), **observer_fields):
    """Build a fake node/observer for the PAUSE_SNAPSHOT_FAILURE diagnostic tests."""
    from so101_demo.backends.mujoco import teleop_runtime

    clock = [0.0]

    def monotonic():
        clock[0] += 0.01
        return clock[0]

    class Future:
        def done(self):
            return response is not None

        def result(self):
            return SimpleNamespace(success=response)

    class Client:
        calls = 0

        def wait_for_service(self, *, timeout_sec):
            return True

        def call_async(self, request):
            self.calls += 1
            return Future()

    client = Client()
    node = SimpleNamespace(create_client=lambda *_args: client)
    fields = dict(publisher_count=1, callback_count=7, rejected_count=2,
                  last_rejection="r" * 300)
    fields.update(observer_fields)
    observer = SimpleNamespace(snapshot=snapshot, retained_with_receipts=lambda: tuple(retained),
                               **fields)
    monkeypatch.setattr(teleop_runtime.time, "monotonic", monotonic)
    monkeypatch.setattr(teleop_runtime, "rclpy",
                        SimpleNamespace(ok=lambda: True, spin_once=lambda *_a, **_k: None))
    return teleop_runtime, node, observer, client


def _failure_lines(captured):
    import json
    prefix = "PAUSE_SNAPSHOT_FAILURE "
    return [json.loads(line[len(prefix):]) for line in captured.err.splitlines()
            if line.startswith(prefix)]


def test_pause_snapshot_failure_logs_one_line_with_counters_when_never_paused(
        monkeypatch, capsys) -> None:
    from so101_demo.backends.mujoco.observer import EvidenceStale

    evidence = SimpleNamespace(paused=False, simulation_step=11, simulation_time_s=1.5,
                               simulation_session_id="sess", reset_epoch=3, publisher_sequence=9)
    received = SimpleNamespace(evidence=evidence, received_monotonic_s=0.0)
    reads = []

    def snapshot():
        reads.append(1)
        if len(reads) % 2:
            raise EvidenceStale("stale")
        return evidence

    runtime, node, observer, client = _failure_harness(
        monkeypatch, response=True, snapshot=snapshot, retained=(received,))
    with pytest.raises(RuntimeError, match="^fresh paused atomic MuJoCo evidence unavailable$"):
        runtime._pause_snapshot(node, observer, 1.0)
    lines = _failure_lines(capsys.readouterr())
    assert len(lines) == 1
    line = lines[0]
    assert line["reason"] == "fresh paused atomic MuJoCo evidence unavailable"
    assert line["timeout_s"] == 1.0
    assert line["requests_sent"] == client.calls >= 1
    assert line["response_received"] is True and line["pause_accepted"] is True
    assert line["publisher_count"] == 1 and line["callback_count"] == 7
    assert line["rejected_count"] == 2 and line["last_rejection"] == "r" * 200
    assert line["stale_reads"] == (len(reads) + 1) // 2
    assert line["non_paused_reads"] == len(reads) // 2
    assert line["elapsed_s"] > 0.0
    latest = line["latest"]
    assert latest["paused"] is False and latest["simulation_step"] == 11
    assert latest["simulation_time_s"] == 1.5 and latest["session_id"] == "sess"
    assert latest["reset_epoch"] == 3 and latest["publisher_sequence"] == 9
    assert latest["receipt_age_s"] > 0.0


def test_pause_snapshot_failure_latest_is_null_without_retained_evidence(
        monkeypatch, capsys) -> None:
    from so101_demo.backends.mujoco.observer import EvidenceStale

    def snapshot():
        raise EvidenceStale("none")

    runtime, node, observer, _client = _failure_harness(
        monkeypatch, response=True, snapshot=snapshot)
    with pytest.raises(RuntimeError, match="fresh paused atomic MuJoCo evidence unavailable"):
        runtime._pause_snapshot(node, observer, 1.0)
    (line,) = _failure_lines(capsys.readouterr())
    assert line["latest"] is None and line["non_paused_reads"] == 0 and line["stale_reads"] > 0


def test_pause_snapshot_timeout_without_response_logs_one_line(monkeypatch, capsys) -> None:
    from so101_demo.backends.mujoco.observer import EvidenceStale

    def snapshot():
        raise EvidenceStale("none")

    runtime, node, observer, client = _failure_harness(
        monkeypatch, response=None, snapshot=snapshot)
    with pytest.raises(RuntimeError, match="^pause snapshot request timed out$"):
        runtime._pause_snapshot(node, observer, 1.0)
    (line,) = _failure_lines(capsys.readouterr())
    assert line["reason"] == "pause snapshot request timed out"
    assert line["response_received"] is False and line["requests_sent"] == client.calls == 1


def test_pause_snapshot_rejected_pause_logs_one_line(monkeypatch, capsys) -> None:
    from so101_demo.backends.mujoco.observer import EvidenceStale

    def snapshot():
        raise EvidenceStale("none")

    runtime, node, observer, _client = _failure_harness(
        monkeypatch, response=False, snapshot=snapshot)
    with pytest.raises(RuntimeError, match="^pause snapshot request failed$"):
        runtime._pause_snapshot(node, observer, 1.0)
    (line,) = _failure_lines(capsys.readouterr())
    assert line["reason"] == "pause snapshot request failed"
    assert line["response_received"] is True and line["pause_accepted"] is False


def test_pause_snapshot_failure_log_never_raises_or_masks_the_error(monkeypatch, capsys) -> None:
    from so101_demo.backends.mujoco.observer import EvidenceStale

    def snapshot():
        raise EvidenceStale("none")

    runtime, node, observer, _client = _failure_harness(
        monkeypatch, response=True, snapshot=snapshot)

    def broken():
        raise OSError("observer broke")

    observer.retained_with_receipts = broken
    with pytest.raises(RuntimeError, match="^fresh paused atomic MuJoCo evidence unavailable$"):
        runtime._pause_snapshot(node, observer, 1.0)
    capsys.readouterr()


def test_pause_snapshot_success_emits_no_failure_line(monkeypatch, capsys) -> None:
    evidence = SimpleNamespace(paused=True)
    runtime, node, observer, _client = _failure_harness(
        monkeypatch, response=True, snapshot=lambda: evidence)
    assert runtime._pause_snapshot(node, observer, 1.0) is evidence
    assert _failure_lines(capsys.readouterr()) == []
