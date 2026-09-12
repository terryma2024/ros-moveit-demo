from types import SimpleNamespace


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
