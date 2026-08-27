from pathlib import Path
from types import SimpleNamespace


class _Processes:
    def __init__(self) -> None:
        self.roles = []
        self.commands = []
        self.children = {}
        self.codes = {"dynamic-consumer": None, "rgbd-perception": None}
        self.stdout_paths = {}

    def start(self, role, argv, *, environment=None, stdout_path=None):
        from so101_demo.application.task_batch import ManagedChild

        self.roles.append(role)
        self.commands.append(list(argv))
        if stdout_path is not None:
            self.stdout_paths[role] = stdout_path
        child = ManagedChild(role, 100 + len(self.roles), 100 + len(self.roles))
        self.children[role] = child
        return child

    def stop_all(self):
        self.roles.append("stopped")

    def poll(self, role):
        return self.codes[role]


class _Graph:
    def __init__(self) -> None:
        self.calls = []

    def subscription_count(self, node_name, topic):
        self.calls.append((node_name, topic))
        return 1


def test_graph_probe_discovers_subscription_without_ros_daemon() -> None:
    from so101_demo.runtime.task_batch_runtime import RosGraphProbe

    calls = []

    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        return SimpleNamespace(
            returncode=0,
            stdout="Subscribers:\n  /cup_pose: geometry_msgs/msg/PoseStamped\nPublishers:\n",
        )

    probe = RosGraphProbe(runner=run)

    assert probe.subscription_count(
        "/so101_dynamic_cup_pick_place", "/cup_pose"
    ) == 1
    assert "--no-daemon" in calls[0][0]
    assert calls[0][0][-1] == "/so101_dynamic_cup_pick_place"
    assert calls[0][1]["timeout"] == 3.0


def _runtime(tmp_path: Path):
    from so101_demo.runtime.task_batch_runtime import RosTaskBatchRuntime

    processes = _Processes()
    graph = _Graph()
    runtime = RosTaskBatchRuntime(
        processes,
        graph,
        session_id="sim-a",
        points_file=tmp_path / "points.yaml",
        policy_file=tmp_path / "policy.yaml",
        evidence_root=tmp_path,
        viewer_capture=SimpleNamespace(capture=lambda path, **_kwargs: path),
        command_runner=lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0, stdout="{}"
        ),
        resume=lambda: True,
        monotonic=lambda: 1.0,
        sleep=lambda _value: None,
    )
    return runtime, processes, graph


def test_runtime_waits_for_consumer_before_starting_perception(tmp_path: Path) -> None:
    runtime, processes, graph = _runtime(tmp_path)
    point_root = tmp_path / "point"
    consumer = runtime.start_consumer(point_root, epoch=3)
    (point_root / "dynamic-consumer.log").write_text(
        "status=READY subscription=/cup_pose\n"
    )
    runtime.wait_consumer_subscription(consumer, 5.0)
    runtime.start_perception(point_root)

    assert processes.roles == ["dynamic-consumer", "rgbd-perception"]
    assert graph.calls == []
    consumer_argv, perception_argv = processes.commands
    assert ["--session-id", "sim-a"] == consumer_argv[
        consumer_argv.index("--session-id") : consumer_argv.index("--session-id") + 2
    ]
    epoch_index = consumer_argv.index("--expected-reset-epoch")
    assert ["--expected-reset-epoch", "3"] == consumer_argv[
        epoch_index : epoch_index + 2
    ]
    timeout_index = consumer_argv.index("--cup-pose-timeout-s")
    assert consumer_argv[timeout_index : timeout_index + 2] == [
        "--cup-pose-timeout-s",
        "75.0",
    ]
    perception_timeout_index = perception_argv.index("--timeout-s")
    assert perception_argv[
        perception_timeout_index : perception_timeout_index + 2
    ] == ["--timeout-s", "30.0"]
    assert str(point_root / "dynamic") in consumer_argv
    assert str(point_root / "rgb.png") in perception_argv
    assert str(point_root / "full-cloud.ply") in perception_argv
    assert str(point_root / "point-cloud-preview.png") in perception_argv
    assert processes.stdout_paths == {
        "dynamic-consumer": point_root / "dynamic-consumer.log",
        "rgbd-perception": point_root / "rgbd-perception.log",
    }


def test_owned_process_stdout_is_retained_and_closed(tmp_path: Path) -> None:
    from so101_demo.runtime.task_batch_runtime import OwnedPointProcesses

    captured = {}

    class Child:
        pid = 123

        def poll(self):
            return 0

    def popen(argv, **kwargs):
        captured.update(kwargs)
        return Child()

    processes = OwnedPointProcesses(popen=popen)
    log_path = tmp_path / "consumer.log"
    processes.start("consumer", ["example"], stdout_path=log_path)

    assert captured["stdout"].name == str(log_path)
    assert captured["stderr"] is __import__("subprocess").STDOUT
    processes.stop_all()
    assert captured["stdout"].closed is True


def test_perception_cannot_start_before_subscription_handshake(tmp_path: Path) -> None:
    runtime, processes, _graph = _runtime(tmp_path)
    runtime.start_consumer(tmp_path / "point", epoch=1)
    try:
        runtime.start_perception(tmp_path / "point")
    except RuntimeError as error:
        assert "subscription" in str(error)
    else:
        raise AssertionError("perception started before subscription handshake")
    assert processes.roles == ["dynamic-consumer"]


def test_subscription_timeout_has_a_stable_shared_failure_code(tmp_path: Path) -> None:
    from so101_demo.application.task_batch import SharedStackFailure
    from so101_demo.runtime.task_batch_runtime import RosTaskBatchRuntime

    runtime = RosTaskBatchRuntime(
        _Processes(),
        SimpleNamespace(subscription_count=lambda *_args: 0),
        session_id="sim-a",
        points_file=tmp_path / "points.yaml",
        policy_file=tmp_path / "policy.yaml",
        evidence_root=tmp_path,
        viewer_capture=SimpleNamespace(capture=lambda *_args, **_kwargs: None),
        command_runner=lambda *_args, **_kwargs: None,
        resume=lambda: True,
        monotonic=iter((0.0, 0.0, 31.0)).__next__,
        sleep=lambda _value: None,
    )

    consumer = runtime.start_consumer(tmp_path / "point", epoch=1)
    try:
        runtime.wait_consumer_subscription(consumer, 30.0)
    except SharedStackFailure as error:
        assert error.code == "DYNAMIC_CONSUMER_SUBSCRIPTION_TIMEOUT"
    else:
        raise AssertionError("subscription timeout must be a shared stack failure")


def test_subscription_handshake_fails_immediately_when_consumer_exits(tmp_path: Path) -> None:
    from so101_demo.application.task_batch import SharedStackFailure

    runtime, processes, _graph = _runtime(tmp_path)
    consumer = runtime.start_consumer(tmp_path / "point", epoch=1)
    processes.codes["dynamic-consumer"] = 1

    try:
        runtime.wait_consumer_subscription(consumer, 30.0)
    except SharedStackFailure as error:
        assert error.code == "DYNAMIC_CONSUMER_EXITED_BEFORE_SUBSCRIPTION"
    else:
        raise AssertionError("an exited consumer cannot satisfy the handshake")


def test_stop_point_children_targets_only_runtime_owned_groups(tmp_path: Path) -> None:
    runtime, processes, _graph = _runtime(tmp_path)
    point_root = tmp_path / "point"
    runtime.start_consumer(point_root, epoch=1)
    (point_root / "dynamic-consumer.log").write_text(
        "status=READY subscription=/cup_pose\n"
    )
    runtime.wait_consumer_subscription(processes.children["dynamic-consumer"], 5.0)
    runtime.start_perception(point_root)
    runtime.stop_point_children()
    assert processes.roles[-1] == "stopped"


def test_declared_reachability_and_reset_preserve_point_session_epoch(tmp_path: Path) -> None:
    from so101_demo.application.task_reachability import ReachabilityStatus
    from so101_demo.core.task_points import TaskPoint
    from so101_demo.runtime.task_batch_runtime import RosTaskBatchRuntime

    commands = []
    resumed = []

    def run(argv, **_kwargs):
        commands.append(argv)
        if "task_reachability" in argv:
            document = {
                "reports": [
                    {
                        "point_id": "left",
                        "status": "REACHABLE",
                        "first_failure_code": None,
                        "scene_revision": 4,
                    }
                ]
            }
        else:
            document = {
                "success": True,
                "old_epoch": 4,
                "new_epoch": 5,
                "simulation_session_id": "sim-a",
            }
        return SimpleNamespace(returncode=0, stdout=__import__("json").dumps(document))

    runtime = RosTaskBatchRuntime(
        _Processes(),
        _Graph(),
        session_id="sim-a",
        points_file=tmp_path / "points.yaml",
        policy_file=tmp_path / "policy.yaml",
        evidence_root=tmp_path,
        viewer_capture=SimpleNamespace(capture=lambda *_args, **_kwargs: None),
        command_runner=run,
        resume=lambda: resumed.append(True) or True,
    )
    point = TaskPoint("left", "Left", (-0.03, -0.28, 0.165))

    report = runtime.check_declared(point)
    reset = runtime.reset_point(point)

    assert report.status is ReachabilityStatus.REACHABLE
    assert report.scene_revision == 4
    assert (reset.old_epoch, reset.new_epoch, reset.simulation_session_id) == (
        4,
        5,
        "sim-a",
    )
    assert resumed == [True, True]
    reachability_argv = commands[0]
    joint_timeout = reachability_argv.index("--joint-state-timeout-s")
    assert reachability_argv[joint_timeout : joint_timeout + 2] == [
        "--joint-state-timeout-s",
        "20.0",
    ]
    reset_argv = commands[1]
    coordinates = reset_argv.index("--cup-position-world-m")
    assert reset_argv[coordinates + 1 : coordinates + 4] == ["-0.03", "-0.28", "0.165"]


def test_declared_reachability_fails_closed_when_world_cannot_resume(tmp_path: Path) -> None:
    from so101_demo.application.task_batch import SharedStackFailure
    from so101_demo.core.task_points import TaskPoint
    from so101_demo.runtime.task_batch_runtime import RosTaskBatchRuntime

    commands = []
    runtime = RosTaskBatchRuntime(
        _Processes(),
        _Graph(),
        session_id="sim-a",
        points_file=tmp_path / "points.yaml",
        policy_file=tmp_path / "policy.yaml",
        evidence_root=tmp_path,
        viewer_capture=SimpleNamespace(capture=lambda *_args, **_kwargs: None),
        command_runner=lambda *args, **kwargs: commands.append((args, kwargs)),
        resume=lambda: False,
    )

    try:
        runtime.check_declared(TaskPoint("next", "Next", (0.02, -0.28, 0.165)))
    except SharedStackFailure as error:
        assert error.code == "MUJOCO_RESUME_FAILED"
    else:
        raise AssertionError("reachability must not run against a paused world")
    assert commands == []


def test_runtime_canonicalizes_symlinked_evidence_root(tmp_path: Path) -> None:
    from so101_demo.core.task_points import TaskPoint
    from so101_demo.runtime.task_batch_runtime import RosTaskBatchRuntime

    real_root = tmp_path / "private-tmp"
    real_root.mkdir()
    alias_root = tmp_path / "tmp"
    alias_root.symlink_to(real_root, target_is_directory=True)
    commands = []

    def run(argv, **_kwargs):
        commands.append(argv)
        document = {
            "reports": [
                {
                    "point_id": "task_start",
                    "status": "REACHABLE",
                    "first_failure_code": None,
                    "scene_revision": 1,
                }
            ]
        }
        return SimpleNamespace(
            returncode=0,
            stdout=__import__("json").dumps(document),
        )

    runtime = RosTaskBatchRuntime(
        _Processes(),
        _Graph(),
        session_id="sim-a",
        points_file=tmp_path / "points.yaml",
        policy_file=tmp_path / "policy.yaml",
        evidence_root=alias_root,
        viewer_capture=SimpleNamespace(capture=lambda *_args, **_kwargs: None),
        command_runner=run,
        resume=lambda: True,
    )

    runtime.check_declared(
        TaskPoint("task_start", "Task start", (0.02, -0.28, 0.165))
    )

    evidence_argument = commands[0][commands[0].index("--evidence-file") + 1]
    assert Path(evidence_argument).is_relative_to(real_root.resolve())
    assert not Path(evidence_argument).is_relative_to(alias_root.absolute())


def test_first_terminal_child_status_controls_point_result(tmp_path: Path) -> None:
    from so101_demo.core.task_points import TaskPoint

    runtime, processes, _graph = _runtime(tmp_path)
    processes.codes["dynamic-consumer"] = 0
    processes.codes["rgbd-perception"] = None
    point_root = tmp_path / "point"
    point_root.mkdir()

    receipt = runtime.wait_point_result(
        TaskPoint("first", "First", (0.02, -0.28, 0.165)),
        3,
        point_root,
    )

    assert receipt.succeeded is True
    assert receipt.workflow_manifest == (
        point_root / "dynamic/dynamic-execute-manifest.json"
    )


def test_final_pause_reuses_safe_to_continue_paused_snapshot(
    tmp_path: Path, monkeypatch
) -> None:
    from so101_demo.backends.mujoco import teleop_runtime

    evidence = SimpleNamespace(
        simulation_session_id="sim-a",
        reset_epoch=3,
        object_state=SimpleNamespace(position_world=(0.02, -0.28, 0.165)),
        left_fingertip_contacts=(),
        right_fingertip_contacts=(),
    )
    calls = []

    def current_evidence(_session_id):
        calls.append("pause")
        return evidence

    monkeypatch.setattr(teleop_runtime, "current_evidence", current_evidence)
    runtime, _processes, _graph = _runtime(tmp_path)

    safety = runtime.safe_to_continue(3)
    runtime.pause_world()

    assert safety.safe_to_reset is True
    assert calls == ["pause"]
