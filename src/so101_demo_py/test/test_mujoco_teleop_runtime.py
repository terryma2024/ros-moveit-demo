from types import SimpleNamespace


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
