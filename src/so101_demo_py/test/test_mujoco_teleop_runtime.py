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
