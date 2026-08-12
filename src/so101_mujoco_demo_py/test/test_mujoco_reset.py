from __future__ import annotations

import pytest

from so101_mujoco_demo_py.mujoco.client import MujocoRosClient
from so101_mujoco_demo_py.mujoco.observer import EvidenceStale
from so101_mujoco_demo_py.mujoco.reset import MujocoResetClient, ResetFailed
from so101_mujoco_demo_py.simulation.types import ObjectState, SimulationEvidence


def evidence(*, epoch=0, step=10, session="session-a", position=(0.27, 0.0, 0.08), paused=False):
    return SimulationEvidence(
        simulation_time_s=1.0,
        frame_id="world",
        publisher_sequence=step + epoch * 100,
        simulation_step=step,
        reset_epoch=epoch,
        simulation_session_id=session,
        paused=paused,
        object_state=ObjectState(
            body_id=9,
            body="cup",
            position_world=position,
            orientation_xyzw=(0.0, 0.0, 0.0, 1.0),
            linear_velocity_world=(0.0, 0.0, 0.0),
            angular_velocity_world=(0.0, 0.0, 0.0),
        ),
        has_contact=False,
        minimum_signed_distance_m=0.0,
        maximum_normal_force_n=0.0,
        truncated=False,
        left_fingertip_contacts=(),
        right_fingertip_contacts=(),
        other_object_contacts=(),
    )


class FakeObserver:
    def __init__(self, snapshots):
        self.snapshots = list(snapshots)
        self.last = self.snapshots[0]

    def snapshot(self):
        if self.snapshots:
            self.last = self.snapshots.pop(0)
        return self.last


class FakeServices:
    def __init__(self):
        self.operations = []
        self.active = True
        self.controller_ok = True
        self.joints_ok = True
        self.fail_operation = None
        self.joint_callback_count = 0
        self.fresh_joints = True

    def pause(self, paused):
        self.operations.append(("pause", paused))
        return self.fail_operation != "pause"

    def switch_controllers(self, *, activate, deactivate):
        operation = "activate" if activate else "deactivate"
        self.operations.append((operation, tuple(activate or deactivate)))
        self.active = bool(activate)
        return self.fail_operation != operation

    def reset_world(self, keyframe):
        self.operations.append(("reset", keyframe))
        return self.fail_operation != "reset"

    def step(self, steps):
        self.operations.append(("step", steps))
        return self.fail_operation != "step"

    def controllers_active(self, names):
        self.operations.append(("controllers_active", tuple(names)))
        if self.fresh_joints:
            self.joint_callback_count += 1
        return self.active and self.controller_ok

    def joints_converged(self, expected, tolerance, *, after_callback_count):
        self.operations.append(
            ("joints_converged", tuple(expected), tolerance, after_callback_count)
        )
        return self.joints_ok and self.joint_callback_count > after_callback_count


def resetter(services, observer, now, **kwargs):
    def progress():
        now[0] += 0.01
        if services.fresh_joints:
            services.joint_callback_count += 1

    return MujocoResetClient(
        services,
        observer,
        simulation_session_id="session-a",
        controller_names=("arm_controller", "gripper_controller"),
        expected_joint_positions=(0.0,) * 6,
        expected_object_position=(0.27, 0.0, 0.08),
        timeout_s=0.1,
        monotonic=lambda: now[0],
        progress=progress,
        **kwargs,
    )


def test_reset_orders_pause_controller_reset_snapshot_and_independent_verification() -> None:
    services = FakeServices()
    observer = FakeObserver(
        [
            evidence(),
            evidence(epoch=1, step=0, paused=True),
            evidence(epoch=1, step=3, paused=True),
        ]
    )
    now = [0.0]
    target = resetter(services, observer, now)

    def progress():
        now[0] += 0.01
        services.joint_callback_count += 1

    target._progress = progress
    receipt = target.reset("task_start")
    assert receipt.old_epoch == 0
    assert receipt.new_epoch == 1
    assert receipt.keyframe == "task_start"
    assert receipt.simulation_step == 0
    assert services.operations == [
        ("deactivate", ("arm_controller", "gripper_controller")),
        ("pause", True),
        ("reset", "task_start"),
        ("pause", False),
        ("activate", ("arm_controller", "gripper_controller")),
        ("pause", True),
        ("controllers_active", ("arm_controller", "gripper_controller")),
        ("joints_converged", (0.0,) * 6, 0.002, 1),
    ]
    assert all(operation[0] != "step" for operation in services.operations)


def test_bounded_resume_waits_for_post_reset_joint_callback_before_repause() -> None:
    class BoundaryServices(FakeServices):
        def __init__(self):
            super().__init__()
            self.fresh_joints = False
            self.pause_true_callback_counts = []

        def pause(self, paused):
            if paused:
                self.pause_true_callback_counts.append(self.joint_callback_count)
            return super().pause(paused)

    services = BoundaryServices()
    observer = FakeObserver([evidence(), evidence(epoch=1, step=0, paused=True)])
    now = [0.0]
    progress_calls = [0]
    target = resetter(services, observer, now)

    def progress():
        progress_calls[0] += 1
        now[0] += 0.01
        if progress_calls[0] == 2:
            services.joint_callback_count = 1

    target._progress = progress
    receipt = target.reset("task_start")

    assert receipt.new_epoch == 1
    assert services.pause_true_callback_counts == [0, 1]
    assert services.operations.index(("pause", False)) < services.operations.index(
        ("activate", ("arm_controller", "gripper_controller"))
    )


def test_final_verification_drains_transient_running_frame_after_repause() -> None:
    services = FakeServices()
    observer = FakeObserver(
        [
            evidence(),
            evidence(epoch=1, step=0, paused=True),
            evidence(epoch=1, step=1, paused=False),
            evidence(epoch=1, step=1, paused=True),
        ]
    )

    receipt = resetter(services, observer, [0.0]).reset("task_start")

    assert receipt.new_epoch == 1
    assert services.operations.count(("pause", True)) == 2


@pytest.mark.parametrize("operation", ["deactivate", "reset", "activate"])
def test_failure_is_explicit_and_leaves_world_paused(operation) -> None:
    services = FakeServices()
    services.fail_operation = operation
    snapshots = [evidence()]
    if operation == "activate":
        snapshots.append(evidence(epoch=1, step=0, paused=True))
    target = resetter(services, FakeObserver(snapshots), [0.0])
    with pytest.raises(ResetFailed, match=operation):
        target.reset("task_start")
    assert services.operations[-1] == ("pause", True)


def test_epoch_mismatch_and_timeout_fail_closed() -> None:
    services = FakeServices()
    wrong_epoch = FakeObserver([evidence(), evidence(epoch=2, step=0, paused=True)])
    with pytest.raises(ResetFailed, match="epoch"):
        resetter(services, wrong_epoch, [0.0]).reset("task_start")
    services = FakeServices()
    never_changes = FakeObserver([evidence()])
    with pytest.raises(ResetFailed, match="timeout"):
        resetter(services, never_changes, [0.0]).reset("task_start")
    assert services.operations[-1] == ("pause", True)


def test_controller_or_joint_convergence_failure_is_rejected() -> None:
    services = FakeServices()
    services.joints_ok = False
    observer = FakeObserver([evidence(), evidence(epoch=1, step=0, paused=True)])
    with pytest.raises(ResetFailed, match="joint convergence"):
        resetter(services, observer, [0.0]).reset("task_start")


def test_new_epoch_must_be_authoritatively_paused() -> None:
    services = FakeServices()
    observer = FakeObserver([evidence(), evidence(epoch=1, step=0, paused=False)])
    with pytest.raises(ResetFailed, match="paused"):
        resetter(services, observer, [0.0]).reset("task_start")
    assert services.operations[-1] == ("pause", True)


def test_two_identical_resets_produce_sequential_receipts() -> None:
    services = FakeServices()
    observer = FakeObserver(
        [
            evidence(epoch=0, step=9),
            evidence(epoch=1, step=0, paused=True),
            evidence(epoch=1, step=8, paused=True),
            evidence(epoch=1, step=8, paused=True),
            evidence(epoch=2, step=0, paused=True),
            evidence(epoch=2, step=6, paused=True),
        ]
    )
    target = resetter(services, observer, [0.0])
    first = target.reset("task_start")
    second = target.reset("task_start")
    assert (first.old_epoch, first.new_epoch) == (0, 1)
    assert (second.old_epoch, second.new_epoch) == (1, 2)
    assert first.keyframe == second.keyframe == "task_start"
    assert first.simulation_step == second.simulation_step == 0
    assert services.operations[8] == ("pause", False)
    assert services.operations[9] == ("deactivate", ("arm_controller", "gripper_controller"))
    assert services.operations[10] == ("pause", True)
    assert services.operations[11] == ("reset", "task_start")
    assert services.operations[12] == ("pause", False)
    assert services.operations[13] == (
        "activate",
        ("arm_controller", "gripper_controller"),
    )
    assert services.operations[14] == ("pause", True)
    assert (
        services.operations.count(
            (
                "deactivate",
                ("arm_controller", "gripper_controller"),
            )
        )
        == 2
    )


def test_paused_start_is_resumed_before_strict_deactivate() -> None:
    services = FakeServices()
    observer = FakeObserver([evidence(paused=True), evidence(epoch=1, step=0, paused=True)])
    resetter(services, observer, [0.0]).reset("task_start")
    assert services.operations[:2] == [
        ("pause", False),
        ("deactivate", ("arm_controller", "gripper_controller")),
    ]


def test_fresh_client_requests_snapshot_when_world_is_already_paused() -> None:
    class PausedSnapshotObserver:
        def __init__(self):
            self.snapshot_requested = False
            self.accepted_reads = 0

        def snapshot(self):
            if not self.snapshot_requested:
                raise EvidenceStale("paused publisher has not emitted to this subscriber")
            self.accepted_reads += 1
            if self.accepted_reads == 1:
                return evidence(epoch=0, step=12, paused=False)
            if self.accepted_reads == 2:
                return evidence(epoch=0, step=0, paused=True)
            return evidence(epoch=1, step=0, paused=True)

    observer = PausedSnapshotObserver()

    class SnapshotServices(FakeServices):
        def pause(self, paused):
            if paused:
                observer.snapshot_requested = True
            return super().pause(paused)

    services = SnapshotServices()
    receipt = resetter(services, observer, [0.0]).reset("task_start")

    assert receipt.old_epoch == 0
    assert receipt.new_epoch == 1
    assert services.operations[:3] == [
        ("pause", True),
        ("pause", False),
        ("deactivate", ("arm_controller", "gripper_controller")),
    ]


def test_progresses_subscriptions_before_first_post_service_snapshot() -> None:
    class ProgressRequiredObserver:
        def __init__(self):
            self.initial_read = False
            self.progressed = False

        def snapshot(self):
            if not self.initial_read:
                self.initial_read = True
                return evidence()
            if not self.progressed:
                raise RuntimeError("snapshot read before subscription progress")
            return evidence(epoch=1, step=0, paused=True)

    observer = ProgressRequiredObserver()
    services = FakeServices()
    now = [0.0]

    def progress():
        observer.progressed = True
        now[0] += 0.01
        services.joint_callback_count += 1

    target = MujocoResetClient(
        services,
        observer,
        simulation_session_id="session-a",
        controller_names=("arm_controller", "gripper_controller"),
        expected_joint_positions=(0.0,) * 6,
        expected_object_position=(0.27, 0.0, 0.08),
        timeout_s=0.1,
        monotonic=lambda: now[0],
        progress=progress,
    )

    receipt = target.reset("task_start")
    assert receipt.new_epoch == 1


def test_drains_typed_stale_evidence_before_service_retry_deadline() -> None:
    class StaleThenFreshObserver:
        def __init__(self):
            self.reads = 0

        def snapshot(self):
            self.reads += 1
            if self.reads == 1:
                return evidence()
            if self.reads < 4:
                raise EvidenceStale("queued frame is stale")
            return evidence(epoch=1, step=0, paused=True)

    observer = StaleThenFreshObserver()
    now = [0.0]
    services = FakeServices()
    target = resetter(services, observer, now)

    receipt = target.reset("task_start")
    assert receipt.new_epoch == 1
    assert observer.reads == 5
    assert services.operations.count(("pause", True)) == 2


def test_waits_for_subscription_drain_before_retrying_idempotent_pause() -> None:
    """A service retry must not starve delivery of its own reset snapshot."""

    progress_streak = [0]

    class DrainRequiredObserver:
        def __init__(self):
            self.initial_read = False

        def snapshot(self):
            if not self.initial_read:
                self.initial_read = True
                return evidence()
            if progress_streak[0] < 3:
                return evidence()
            return evidence(epoch=1, step=0, paused=True)

    class RetryInterruptsDrainServices(FakeServices):
        def pause(self, paused):
            if paused:
                progress_streak[0] = 0
            return super().pause(paused)

    observer = DrainRequiredObserver()
    services = RetryInterruptsDrainServices()
    now = [0.0]

    def progress():
        progress_streak[0] += 1
        now[0] += 0.01
        services.joint_callback_count += 1

    target = MujocoResetClient(
        services,
        observer,
        simulation_session_id="session-a",
        controller_names=("arm_controller", "gripper_controller"),
        expected_joint_positions=(0.0,) * 6,
        expected_object_position=(0.27, 0.0, 0.08),
        timeout_s=0.1,
        monotonic=lambda: now[0],
        progress=progress,
    )

    receipt = target.reset("task_start")

    assert receipt.new_epoch == 1
    assert services.operations.count(("pause", True)) == 2


def test_ros_client_separates_service_clients_from_joint_subscription() -> None:
    class ServiceNode:
        def __init__(self):
            self.clients = []

        def create_client(self, service_type, name):
            self.clients.append((service_type, name))
            return object()

    class JointNode:
        def __init__(self):
            self.subscriptions = []

        def create_subscription(self, message_type, topic, callback, qos):
            self.subscriptions.append((message_type, topic, callback, qos))
            return object()

    service_node = ServiceNode()
    joint_node = JointNode()
    target = MujocoRosClient(service_node, joint_node)
    assert len(service_node.clients) == 4
    assert [name for _type, name in service_node.clients] == [
        "/mujoco_ros2_control_node/set_pause",
        "/mujoco_ros2_control_node/reset_world",
        "/controller_manager/switch_controller",
        "/controller_manager/list_controllers",
    ]
    assert len(joint_node.subscriptions) == 1
    assert joint_node.subscriptions[0][1] == "/joint_states"
    assert target.joint_callback_count == 0


def test_joint_freshness_advances_only_for_complete_finite_six_joint_feedback() -> None:
    class ServiceNode:
        def create_client(self, _service_type, _name):
            return object()

    class JointNode:
        def create_subscription(self, _message_type, _topic, callback, _qos):
            self.callback = callback
            return object()

    class Message:
        def __init__(self, names, positions):
            self.name = names
            self.position = positions

    joint_node = JointNode()
    target = MujocoRosClient(ServiceNode(), joint_node)

    joint_node.callback(Message(["1"], [0.0]))
    assert target.joint_callback_count == 0
    joint_node.callback(
        Message([str(index) for index in range(1, 7)], [0.0, 0.0, float("nan"), 0.0, 0.0, 0.0])
    )
    assert target.joint_callback_count == 0

    joint_node.callback(Message([str(index) for index in range(1, 7)], [0.0] * 6))
    assert target.joint_callback_count == 1
    assert target.latest_joint_positions() == (0.0,) * 6


def test_step_zero_is_required_and_publisher_sequence_must_advance() -> None:
    services = FakeServices()
    with pytest.raises(ResetFailed, match="step zero"):
        resetter(
            services,
            FakeObserver([evidence(step=9), evidence(epoch=1, step=1, paused=True)]),
            [0.0],
        ).reset("task_start")
    services = FakeServices()
    current = evidence(epoch=1, step=0, paused=True)
    object.__setattr__(current, "publisher_sequence", 1)
    with pytest.raises(ResetFailed, match="publisher sequence"):
        resetter(services, FakeObserver([evidence(step=9), current]), [0.0]).reset("task_start")


def test_receipt_preserves_authoritative_step_zero_after_bounded_resume() -> None:
    services = FakeServices()
    observer = FakeObserver(
        [
            evidence(step=9),
            evidence(epoch=1, step=0, paused=True),
            evidence(epoch=1, step=4, paused=True),
        ]
    )

    receipt = resetter(services, observer, [0.0]).reset("task_start")

    assert receipt.simulation_step == 0
    assert observer.snapshot().simulation_step == 4


def test_non_stale_observer_error_is_terminal_without_retry() -> None:
    class BrokenObserver:
        def __init__(self):
            self.reads = 0

        def snapshot(self):
            self.reads += 1
            if self.reads == 1:
                return evidence()
            raise RuntimeError("observer broken")

    observer = BrokenObserver()
    services = FakeServices()
    with pytest.raises(ResetFailed, match="observer broken"):
        resetter(services, observer, [0.0]).reset("task_start")
    assert observer.reads == 2
    assert services.operations[-1] == ("pause", True)


def test_invalid_keyframe_failure_is_paused_and_epoch_unchanged() -> None:
    services = FakeServices()
    services.fail_operation = "reset"
    observer = FakeObserver([evidence(epoch=4), evidence(epoch=4)])
    with pytest.raises(ResetFailed, match="reset"):
        resetter(services, observer, [0.0]).reset("missing-keyframe")
    assert observer.snapshot().reset_epoch == 4
    assert services.operations[-1] == ("pause", True)


def test_session_controller_joint_and_object_failures_are_terminal() -> None:
    services = FakeServices()
    with pytest.raises(ResetFailed, match="session"):
        resetter(
            services,
            FakeObserver([evidence(), evidence(epoch=1, step=0, session="other", paused=True)]),
            [0.0],
        ).reset("task_start")

    services = FakeServices()
    services.controller_ok = False
    with pytest.raises(ResetFailed, match="controller"):
        resetter(
            services,
            FakeObserver([evidence(), evidence(epoch=1, step=0, paused=True)]),
            [0.0],
        ).reset("task_start")

    services = FakeServices()
    services.fresh_joints = False
    with pytest.raises(ResetFailed, match="joint"):
        resetter(
            services,
            FakeObserver([evidence(), evidence(epoch=1, step=0, paused=True)]),
            [0.0],
        ).reset("task_start")

    services = FakeServices()
    with pytest.raises(ResetFailed, match="object pose"):
        resetter(
            services,
            FakeObserver(
                [evidence(), evidence(epoch=1, step=0, position=(0.274, 0.0, 0.08), paused=True)]
            ),
            [0.0],
        ).reset("task_start")


def test_nonfinite_atomic_object_state_is_rejected() -> None:
    current = evidence(epoch=1, step=0, paused=True)
    object.__setattr__(current.object_state, "position_world", (float("nan"), 0.0, 0.08))
    with pytest.raises(ResetFailed, match="finite"):
        resetter(FakeServices(), FakeObserver([evidence(), current]), [0.0]).reset("task_start")
