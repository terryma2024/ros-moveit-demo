"""The ROS runtime resources, cleanup, the command line and the package registration."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from paths import PACKAGE_ROOT
import pytest
from rgbd_cup_pose_support import _fake_ros_api, _valid_frame


def test_ros_runtime_matches_reliable_depth_one_camera_qos() -> None:
    from so101_demo.ros.rgbd_cup_pose.frames import RgbdCupPoseOptions
    from so101_demo.ros.rgbd_cup_pose.ros_runtime import _create_ros_runtime

    api, _rclpy, node, _listener = _fake_ros_api()
    runtime = _create_ros_runtime(
        RgbdCupPoseOptions(),
        startup_deadline=11.0,
        monotonic=lambda: 10.0,
        ros_api=api,
    )
    try:
        assert len(node.publisher_calls) == 1
        publisher_qos = node.publisher_calls[0][2]
        assert publisher_qos.depth == 1
        assert publisher_qos.reliability == "reliable"
        subscription_qos = [call[3] for call in node.subscription_calls]
        assert len(subscription_qos) == 3
        for qos in subscription_qos:
            assert qos.depth == 1
            assert qos.reliability == "reliable"
            assert qos.durability == "volatile"
    finally:
        runtime.close()


def test_workflow_ready_is_emitted_once_after_the_first_fresh_frame_gate() -> None:
    from so101_demo.ros.rgbd_cup_pose.frames import RgbdCupPoseOptions
    from so101_demo.ros.rgbd_cup_pose.ros_runtime import _create_ros_runtime

    timeline = []

    class Emitter:
        component = "perception"
        last_event = None

        def emit(self, event, *, payload, failure_code=None):
            timeline.append((event, payload, failure_code))
            self.last_event = SimpleNamespace(event=event)

    api, _rclpy, _node, _listener = _fake_ros_api()
    runtime = _create_ros_runtime(
        RgbdCupPoseOptions(),
        startup_deadline=11.0,
        monotonic=lambda: 10.0,
        ros_api=api,
        event_emitter=Emitter(),
    )
    runtime._processor.process = lambda _aligned: timeline.append("process")
    aligned = (
        SimpleNamespace(header=SimpleNamespace(stamp=SimpleNamespace(sec=1, nanosec=2))),
        object(),
        object(),
    )

    runtime._process_aligned(aligned)
    runtime._process_aligned(aligned)
    runtime.close()

    assert timeline == [("PERCEPTION_READY", {}, None), "process"]


def test_profiled_ros_runtime_records_matched_first_callbacks_and_common_stamp(
    tmp_path: Path,
) -> None:
    from so101_demo.profiling.model import ProfilingConfig, ProfilingMode
    from so101_demo.profiling.session import build_profiler
    from so101_demo.ros.rgbd_cup_pose.frames import RgbdCupPoseOptions
    from so101_demo.ros.rgbd_cup_pose.ros_runtime import _create_ros_runtime

    profiler = build_profiler(
        ProfilingConfig(
            mode=ProfilingMode.TRACE,
            output_root=tmp_path / "profiling",
            session_id="session-1",
            process_role="perception",
        )
    )
    assert profiler is not None
    api, _rclpy, node, _listener = _fake_ros_api()
    runtime = _create_ros_runtime(
        RgbdCupPoseOptions(),
        startup_deadline=11.0,
        monotonic=lambda: 10.0,
        ros_api=api,
        profiler=profiler,
    )
    runtime._process_aligned = lambda _aligned: None

    for call in node.subscription_calls:
        call[5]["event_callbacks"].matched(
            SimpleNamespace(current_count=1, current_count_change=1, total_count=1)
        )

    stamp = SimpleNamespace(sec=7, nanosec=123)
    for call in node.subscription_calls:
        call[2](SimpleNamespace(header=SimpleNamespace(stamp=stamp)))

    runtime.close()
    profiler.close()
    events = [
        json.loads(line)
        for line in (
            tmp_path / "profiling/processes/perception.events.jsonl"
        ).read_text().splitlines()
    ]
    instant_events = [event for event in events if event["event_type"] == "instant"]
    assert [event["name"] for event in instant_events] == [
        "perception.subscription_matched",
        "perception.subscription_matched",
        "perception.subscription_matched",
        "perception.first_callback",
        "perception.first_callback",
        "perception.first_callback",
        "perception.common_stamp",
    ]
    assert [event["attributes"]["topic"] for event in instant_events[:3]] == [
        "/task_camera/camera_info",
        "/task_camera/color",
        "/task_camera/depth",
    ]
    assert [event["attributes"]["topic"] for event in instant_events[3:6]] == [
        "/task_camera/camera_info",
        "/task_camera/color",
        "/task_camera/depth",
    ]
    assert all(
        event["attributes"]["source_stamp_ns"] == 7_000_000_123
        for event in instant_events[3:]
    )

    complete = [
        event for event in events if event["event_type"] == "span_complete"
    ]
    milestones = {
        event["name"]: event
        for event in complete
        if event["name"].startswith("perception.wait_all_")
        or event["name"] == "perception.wait_common_stamp"
    }
    assert set(milestones) == {
        "perception.wait_all_subscriptions_matched",
        "perception.wait_all_first_callbacks",
        "perception.wait_common_stamp",
    }
    assert all(event["outcome"] == "available" for event in milestones.values())


def test_unprofiled_ros_runtime_constructs_no_subscription_event_callbacks() -> None:
    from so101_demo.ros.rgbd_cup_pose.frames import RgbdCupPoseOptions
    from so101_demo.ros.rgbd_cup_pose.ros_runtime import _create_ros_runtime

    api, _rclpy, node, _listener = _fake_ros_api()

    def reject_event_callbacks(**_kwargs):
        raise AssertionError("profiling-off path constructed QoS event callbacks")

    api.SubscriptionEventCallbacks = reject_event_callbacks
    runtime = _create_ros_runtime(
        RgbdCupPoseOptions(),
        startup_deadline=11.0,
        monotonic=lambda: 10.0,
        ros_api=api,
    )
    try:
        assert [call[5] for call in node.subscription_calls] == [{}, {}, {}]
    finally:
        runtime.close()


def test_first_valid_publish_releases_exact_rgbd_inputs_once_and_cleanup_is_safe(
    monkeypatch,
) -> None:
    from so101_demo.ros.rgbd_cup_pose import ros_runtime as rgbd_cup_pose_node_ros_runtime
    from so101_demo.ros.rgbd_cup_pose.frames import RgbdCupPoseOptions
    from so101_demo.ros.rgbd_cup_pose.ros_runtime import _create_ros_runtime

    api, _rclpy, node, _listener = _fake_ros_api()
    monkeypatch.setattr(
        rgbd_cup_pose_node_ros_runtime,
        "pose_message_from_frame",
        lambda *_args, **_kwargs: object(),
    )
    runtime = _create_ros_runtime(
        RgbdCupPoseOptions(),
        startup_deadline=11.0,
        monotonic=lambda: 10.0,
        ros_api=api,
    )
    created = [call[4] for call in node.subscription_calls]

    runtime._publish_pose(_valid_frame(stamp_ns=20))

    assert node.destroyed_subscriptions == list(reversed(created))
    assert any(
        '"released_subscription_count": 3' in message
        and '"status": "INPUT_RELEASED_AFTER_FIRST_VALID"' in message
        for message in node.info_messages
    )

    runtime._publish_pose(_valid_frame(stamp_ns=21))
    runtime.close()

    assert node.destroyed_subscriptions == list(reversed(created))


def test_ros_runtime_disables_unused_default_services_without_dropping_sim_time() -> None:
    from so101_demo.ros.rgbd_cup_pose.frames import RgbdCupPoseOptions
    from so101_demo.ros.rgbd_cup_pose.ros_runtime import _create_ros_runtime

    api, fake_rclpy, node, _listener = _fake_ros_api()
    create_node_calls = []

    def record_create_node(name, **kwargs):
        create_node_calls.append((name, kwargs))
        return node

    fake_rclpy.create_node = record_create_node
    runtime = _create_ros_runtime(
        RgbdCupPoseOptions(),
        startup_deadline=11.0,
        monotonic=lambda: 10.0,
        ros_api=api,
    )
    try:
        assert len(create_node_calls) == 1
        name, kwargs = create_node_calls[0]
        assert name == "rgbd_cup_pose"
        assert kwargs["start_parameter_services"] is False
        assert kwargs["enable_rosout"] is False
        assert kwargs["automatically_declare_parameters_from_overrides"] is True
        assert kwargs["parameter_overrides"] == [
            api.Parameter("use_sim_time", value=True)
        ]
    finally:
        runtime.close()


def test_partial_ros_runtime_construction_cleans_every_created_resource() -> None:
    from so101_demo.ros.rgbd_cup_pose.frames import RgbdCupPoseOptions
    from so101_demo.ros.rgbd_cup_pose.ros_runtime import _create_ros_runtime

    api, fake_rclpy, node, listener = _fake_ros_api(fail_subscription_number=2)

    with pytest.raises(RuntimeError, match="subscription construction failed"):
        _create_ros_runtime(
            RgbdCupPoseOptions(),
            startup_deadline=11.0,
            monotonic=lambda: 10.0,
            ros_api=api,
        )

    assert node.destroyed_subscriptions == [node.subscription_calls[0][4]]
    assert node.destroyed_publishers == [node.publisher_calls[0][3]]
    assert listener.unregister_calls == 1
    assert node.destroyed
    assert fake_rclpy.shutdown_calls == 0
    assert fake_rclpy.try_shutdown_calls == 1


def test_node_construction_failure_after_init_shuts_down_owned_context() -> None:
    from so101_demo.ros.rgbd_cup_pose.frames import RgbdCupPoseOptions
    from so101_demo.ros.rgbd_cup_pose.ros_runtime import _create_ros_runtime

    api, fake_rclpy, _node, _listener = _fake_ros_api()

    def fail_node(*_args, **_kwargs):
        raise RuntimeError("node construction failed")

    fake_rclpy.create_node = fail_node

    with pytest.raises(RuntimeError, match="node construction failed"):
        _create_ros_runtime(
            RgbdCupPoseOptions(),
            startup_deadline=11.0,
            monotonic=lambda: 10.0,
            ros_api=api,
        )

    assert fake_rclpy.shutdown_calls == 0
    assert fake_rclpy.try_shutdown_calls == 1


def test_cleanup_attempts_every_resource_in_reverse_order_and_aggregates_failures() -> None:
    from so101_demo.ros.rgbd_cup_pose.ros_runtime import CleanupError, RosResourceCleanup

    calls = []

    def fail(name):
        def operation(_resource=None):
            calls.append(name)
            raise RuntimeError(f"{name} failed")

        return operation

    node = SimpleNamespace(
        destroy_subscription=lambda subscription: fail(f"subscription-{subscription}")(),
        destroy_publisher=fail("publisher"),
        destroy_node=fail("node"),
    )
    listener = SimpleNamespace(unregister=fail("listener"))
    rclpy = SimpleNamespace(ok=lambda: True, try_shutdown=fail("context"))
    cleanup = RosResourceCleanup(
        ros_api=SimpleNamespace(rclpy=rclpy),
        node=node,
        tf_listener=listener,
        publisher="pose-publisher",
        subscriptions=["first", "second"],
        initialized_here=True,
    )

    with pytest.raises(CleanupError) as captured:
        cleanup.close()

    assert calls == [
        "subscription-second",
        "subscription-first",
        "publisher",
        "listener",
        "node",
        "context",
    ]
    assert len(captured.value.failures) == 6


def test_cleanup_is_idempotent_and_preserves_external_context() -> None:
    from so101_demo.ros.rgbd_cup_pose.ros_runtime import RosResourceCleanup

    calls = []
    node = SimpleNamespace(
        destroy_subscription=lambda subscription: calls.append(f"subscription-{subscription}"),
        destroy_publisher=lambda _publisher: calls.append("publisher"),
        destroy_node=lambda: calls.append("node"),
    )
    listener = SimpleNamespace(unregister=lambda: calls.append("listener"))
    rclpy = SimpleNamespace(
        ok=lambda: True,
        shutdown=lambda: calls.append("context"),
    )
    cleanup = RosResourceCleanup(
        ros_api=SimpleNamespace(rclpy=rclpy),
        node=node,
        tf_listener=listener,
        publisher="pose-publisher",
        subscriptions=["only"],
        initialized_here=False,
    )

    cleanup.close()
    cleanup.close()

    assert calls == ["subscription-only", "publisher", "listener", "node"]


def test_failed_cleanup_is_idempotent_and_rethrows_without_repeating_actions() -> None:
    from so101_demo.ros.rgbd_cup_pose.ros_runtime import CleanupError, RosResourceCleanup

    calls = []

    def fail_node() -> None:
        calls.append("node")
        raise RuntimeError("node cleanup failed")

    cleanup = RosResourceCleanup(
        ros_api=SimpleNamespace(rclpy=SimpleNamespace(shutdown=lambda: None)),
        node=SimpleNamespace(destroy_node=fail_node),
        initialized_here=False,
    )

    with pytest.raises(CleanupError) as first:
        cleanup.close()
    with pytest.raises(CleanupError) as second:
        cleanup.close()

    assert first.value is second.value
    assert calls == ["node"]


def test_partial_construction_cleanup_failure_is_actionable_and_continues(capsys) -> None:
    from so101_demo.ros.rgbd_cup_pose.frames import RgbdCupPoseOptions
    from so101_demo.ros.rgbd_cup_pose.ros_runtime import _create_ros_runtime
    from so101_demo.ros.rgbd_cup_pose_node import run_rgbd_cup_pose

    api, fake_rclpy, node, listener = _fake_ros_api(fail_subscription_number=2)

    def fail_subscription_cleanup(subscription) -> None:
        node.destroyed_subscriptions.append(subscription)
        raise RuntimeError("subscription cleanup failed")

    node.destroy_subscription = fail_subscription_cleanup
    result = run_rgbd_cup_pose(
        RgbdCupPoseOptions(startup_timeout_s=1.0),
        runtime_factory=lambda options, deadline, clock: _create_ros_runtime(
            options,
            deadline,
            clock,
            ros_api=api,
        ),
        monotonic=lambda: 10.0,
        open3d_preflight=lambda _remaining_s: None,
    )

    assert result != 0
    assert "RGBD_CUP_POSE_CLEANUP_FAILED" in capsys.readouterr().out
    assert node.destroyed_publishers == [node.publisher_calls[0][3]]
    assert listener.unregister_calls == 1
    assert node.destroyed
    assert fake_rclpy.shutdown_calls == 0
    assert fake_rclpy.try_shutdown_calls == 1


def test_post_success_cleanup_failure_forces_actionable_nonzero(capsys) -> None:
    from so101_demo.ros.rgbd_cup_pose.frames import RgbdCupPoseOptions
    from so101_demo.ros.rgbd_cup_pose_node import run_rgbd_cup_pose

    class FakeRuntime:
        first_valid_published = True

        def spin_once(self, _timeout_s: float) -> None:
            pytest.fail("stopped runtime reached spin")

        def ok(self) -> bool:
            return False

        def close(self) -> None:
            raise RuntimeError("publisher cleanup failed")

    result = run_rgbd_cup_pose(
        RgbdCupPoseOptions(startup_timeout_s=1.0),
        runtime_factory=lambda _options, _deadline, _monotonic: FakeRuntime(),
        monotonic=lambda: 10.0,
        open3d_preflight=lambda _remaining_s: None,
    )

    assert result != 0
    output = capsys.readouterr().out
    assert "RGBD_CUP_POSE_CLEANUP_FAILED" in output
    assert "publisher cleanup failed" in output


def test_post_success_close_accepts_owned_context_already_shut_down(capsys) -> None:
    from so101_demo.ros.rgbd_cup_pose.frames import RgbdCupPoseOptions
    from so101_demo.ros.rgbd_cup_pose.ros_runtime import RosResourceCleanup
    from so101_demo.ros.rgbd_cup_pose_node import run_rgbd_cup_pose

    api, fake_rclpy, node, listener = _fake_ros_api()
    subscription = object()
    publisher = object()
    cleanup = RosResourceCleanup(
        ros_api=api,
        initialized_here=True,
        node=node,
        tf_listener=listener,
        publisher=publisher,
        subscriptions=[subscription],
    )
    fake_rclpy.initialized = False

    runtime = SimpleNamespace(
        first_valid_published=True,
        ok=lambda: False,
        close=cleanup.close,
    )
    result = run_rgbd_cup_pose(
        RgbdCupPoseOptions(startup_timeout_s=1.0),
        runtime_factory=lambda _options, _deadline, _monotonic: runtime,
        monotonic=lambda: 10.0,
        open3d_preflight=lambda _remaining_s: None,
    )

    assert result == 0
    assert "RGBD_CUP_POSE_CLEANUP_FAILED" not in capsys.readouterr().out
    assert node.destroyed_subscriptions == [subscription]
    assert node.destroyed_publishers == [publisher]
    assert listener.unregister_calls == 1
    assert node.destroyed
    assert fake_rclpy.shutdown_calls == 0
    assert fake_rclpy.try_shutdown_calls == 1


def test_run_continues_after_first_valid_frame_until_orderly_shutdown() -> None:
    from so101_demo.ros.rgbd_cup_pose.frames import RgbdCupPoseOptions
    from so101_demo.ros.rgbd_cup_pose_node import run_rgbd_cup_pose

    class FakeRuntime:
        def __init__(self) -> None:
            self.spins = 0
            self.closed = False

        @property
        def first_valid_published(self) -> bool:
            return self.spins >= 1

        def spin_once(self, _timeout_s: float) -> None:
            self.spins += 1

        def ok(self) -> bool:
            return self.spins < 3

        def close(self) -> None:
            self.closed = True

    runtime = FakeRuntime()
    result = run_rgbd_cup_pose(
        RgbdCupPoseOptions(startup_timeout_s=1.0),
        runtime_factory=lambda _options, _deadline, _monotonic: runtime,
        monotonic=lambda: 10.0,
        open3d_preflight=lambda _remaining_s: None,
    )

    assert result == 0
    assert runtime.spins == 3
    assert runtime.closed


def test_runtime_evidence_io_failure_returns_explicit_nonzero(capsys) -> None:
    from so101_demo.ros.rgbd_cup_pose.frames import RgbdCupPoseOptions
    from so101_demo.ros.rgbd_cup_pose_node import run_rgbd_cup_pose

    class FakeRuntime:
        first_valid_published = False
        closed = False

        def spin_once(self, _timeout_s: float) -> None:
            raise OSError("evidence disk is full")

        def ok(self) -> bool:
            return True

        def close(self) -> None:
            self.closed = True

    runtime = FakeRuntime()
    result = run_rgbd_cup_pose(
        RgbdCupPoseOptions(startup_timeout_s=1.0),
        runtime_factory=lambda _options, _deadline, _monotonic: runtime,
        monotonic=lambda: 10.0,
        open3d_preflight=lambda _remaining_s: None,
    )

    assert result != 0
    assert runtime.closed
    output = capsys.readouterr().out
    assert "RGBD_CUP_POSE_FATAL" in output
    assert "evidence disk is full" in output


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (["--startup-timeout-s", "nan"], "finite and positive"),
        (["--output-topic", "cup_pose"], "absolute ROS topic"),
        (["--output-ply", ""], "non-empty path"),
        (["--evidence-json", "relative.json"], "absolute output file path"),
    ],
)
def test_cli_rejects_invalid_options(arguments, message, capsys) -> None:
    from so101_demo.cli.rgbd_cup_pose import main

    with pytest.raises(SystemExit) as error:
        main(arguments)
    assert error.value.code == 2
    assert message in capsys.readouterr().err


def test_cli_removes_launch_injected_ros_parameter_arguments(monkeypatch, tmp_path) -> None:
    from so101_demo.cli import rgbd_cup_pose
    from so101_demo.ros import rgbd_cup_pose_node

    params = tmp_path / "params.yaml"
    params.write_text(
        "/**:\n  ros__parameters:\n    use_sim_time: true\n",
        encoding="utf-8",
    )
    calls = []
    monkeypatch.setattr(
        rgbd_cup_pose_node,
        "run_rgbd_cup_pose",
        lambda options: calls.append(options) or 23,
    )

    assert (
        rgbd_cup_pose.main(
            [
                "--startup-timeout-s",
                "30",
                "--output-topic",
                "/cup_pose",
                "--ros-args",
                "--params-file",
                str(params),
            ]
        )
        == 23
    )
    assert len(calls) == 1
    assert calls[0].startup_timeout_s == 30.0
    assert calls[0].output_topic == "/cup_pose"


def test_cli_still_rejects_unknown_application_argument(capsys) -> None:
    from so101_demo.cli.rgbd_cup_pose import main

    with pytest.raises(SystemExit) as error:
        main(["--unknown-application-option"])
    assert error.value.code == 2
    assert "unrecognized arguments" in capsys.readouterr().err


def test_cli_enabled_profiling_passes_and_closes_perception_profiler(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from so101_demo.cli import rgbd_cup_pose
    from so101_demo.ros import rgbd_cup_pose_node

    calls = []

    def run(options, *, profiler) -> int:
        calls.append((options, profiler))
        return 0

    monkeypatch.setattr(rgbd_cup_pose_node, "run_rgbd_cup_pose", run)
    profiling_root = tmp_path / "profiling"

    assert rgbd_cup_pose.main(
        [
            "--profiling",
            "trace",
            "--profiling-output-root",
            str(profiling_root),
            "--profiling-session-id",
            "session-1",
        ]
    ) == 0

    assert len(calls) == 1
    assert calls[0][1].config.process_role == "perception"
    events = [
        json.loads(line)
        for line in (
            profiling_root / "processes/perception.events.jsonl"
        ).read_text().splitlines()
    ]
    assert events[-1]["event_type"] == "process_close"


def test_cli_profiling_sink_initialization_error_runs_perception_unprofiled(
    monkeypatch,
) -> None:
    from so101_demo.cli import rgbd_cup_pose
    from so101_demo.profiling import session as profiling_session
    from so101_demo.ros import rgbd_cup_pose_node

    calls = []

    def run(options, **kwargs) -> int:
        calls.append((options, kwargs))
        return 23

    monkeypatch.setattr(rgbd_cup_pose_node, "run_rgbd_cup_pose", run)
    monkeypatch.setattr(
        profiling_session,
        "build_profiler",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("disk full")),
    )

    assert rgbd_cup_pose.main(
        [
            "--profiling",
            "summary",
            "--profiling-output-root",
            "/tmp/profiling",
            "--profiling-session-id",
            "session-1",
        ]
    ) == 23

    assert len(calls) == 1
    assert calls[0][1] == {}


def test_cli_invalid_profiling_configuration_still_exits_before_perception(
    monkeypatch,
) -> None:
    from so101_demo.cli import rgbd_cup_pose
    from so101_demo.ros import rgbd_cup_pose_node

    calls = []
    monkeypatch.setattr(
        rgbd_cup_pose_node,
        "run_rgbd_cup_pose",
        lambda options, **kwargs: calls.append((options, kwargs)) or 0,
    )

    with pytest.raises(SystemExit) as error:
        rgbd_cup_pose.main(["--profiling", "summary"])

    assert error.value.code == 2
    assert calls == []


def test_package_registers_rgbd_cup_pose_executable() -> None:
    package_root = PACKAGE_ROOT
    setup_source = (package_root / "setup.py").read_text(encoding="utf-8")

    assert "rgbd_cup_pose = so101_demo.cli.rgbd_cup_pose:main" in setup_source
