from dataclasses import dataclass
import threading

import pytest

from so101_gazebo_demo.domain import ActionStatus, FailureCategory
from so101_gazebo_demo.gazebo.attachment import (
    AttachmentStateReducer, GazeboAttachmentClient,
)
from so101_gazebo_demo.gazebo.observer import (
    ContactPair, MOVING_PAD_MESH_PENETRATION_CEILING_M, evaluate_bilateral_contact,
)
from so101_gazebo_demo.test_support.live_attachment import (
    LiveAttachmentGate, PoseSample,
)
from so101_gazebo_demo.gazebo.transport import wait_for_connections


@dataclass
class FakeTransport:
    reducer: AttachmentStateReducer
    published: list[str]
    converge: bool = True

    def publish_empty(self, topic: str) -> bool:
        self.published.append(topic)
        if self.converge:
            self.reducer.accept("attached" if "attach_object" in topic else "detached")
        return True


def test_event_reducer_ignores_invalid_events_and_keeps_durable_state() -> None:
    reducer = AttachmentStateReducer()
    assert reducer.state is None
    assert not reducer.accept("garbage")
    assert reducer.accept("attached")
    assert reducer.state == "attached"
    assert reducer.accept("detached")
    assert reducer.state == "detached"


def test_attach_and_detach_use_distinct_topics_and_wait_for_convergence() -> None:
    reducer = AttachmentStateReducer()
    transport = FakeTransport(reducer, [])
    client = GazeboAttachmentClient(transport, reducer, "/attach_object", "/detach_object")
    assert client.set_attached(True, 0.1).status is ActionStatus.SUCCEEDED
    assert client.set_attached(False, 0.1).status is ActionStatus.SUCCEEDED
    assert transport.published == ["/attach_object", "/detach_object"]


def test_attachment_timeout_has_stable_failure_category_and_code() -> None:
    reducer = AttachmentStateReducer()
    client = GazeboAttachmentClient(FakeTransport(reducer, [], False), reducer, "/attach", "/detach")
    result = client.set_attached(True, 0.001)
    assert result.status is ActionStatus.TIMED_OUT
    assert result.failure.category is FailureCategory.GAZEBO_ATTACHMENT
    assert result.failure.code == "GAZEBO_ATTACHMENT_CONVERGENCE_TIMEOUT"


def test_transport_waits_for_discovery_before_one_shot_command_publish() -> None:
    class DelayedPublisher:
        calls = 0

        def has_connections(self) -> bool:
            self.calls += 1
            return self.calls >= 3

    publisher = DelayedPublisher()
    assert wait_for_connections(publisher, 0.1)
    assert publisher.calls == 3


def test_bilateral_contact_requires_independent_calibrated_pad_witnesses() -> None:
    evidence = evaluate_bilateral_contact([
        ContactPair(
            "plastic_cup::body::wall_near",
            "so101::gripper::fixed_fingertip_pad_collision_003",
            (0.00031, -0.00002),
        ),
        ContactPair(
            "plastic_cup::body::wall_near",
            "so101::jaw::moving_fingertip_pad_collision_002",
            (0.0013,),
        ),
    ])
    assert evidence.fixed_finger
    assert evidence.moving_jaw
    assert evidence.bilateral
    assert MOVING_PAD_MESH_PENETRATION_CEILING_M == 0.0013
    assert evidence.max_moving_pad_penetration_m == 0.0013


def test_bilateral_contact_rejects_legacy_collision_and_solver_depth_excess() -> None:
    evidence = evaluate_bilateral_contact([
        ContactPair(
            "plastic_cup::body::wall_near", "so101::gripper::gripper_collision", (0.0001,),
        ),
        ContactPair(
            "plastic_cup::body::wall_near",
            "so101::jaw::moving_fingertip_pad_collision_000",
            (0.001300001,),
        ),
    ])
    assert not evidence.fixed_finger
    assert evidence.moving_jaw
    assert not evidence.bilateral
    assert not evidence.within_solver_depth_limit


class FakeLiveBackend:
    def __init__(self) -> None:
        self.arm_paths: list[tuple[tuple[float, ...], ...]] = []
        self.gripper_targets: list[float] = []
        self.attachment_requests: list[bool] = []
        self.sample_index = 0

    def move_arm(self, points: tuple[tuple[float, ...], ...]) -> None:
        self.arm_paths.append(points)

    def move_gripper(self, target_q6: float) -> None:
        self.gripper_targets.append(target_q6)

    def contacts(self) -> tuple[ContactPair, ...]:
        return (
            ContactPair("plastic_cup::body::wall_near", "so101::gripper::fixed_fingertip_pad_collision_003", (0.0004,)),
            ContactPair("plastic_cup::body::wall_near", "so101::jaw::moving_fingertip_pad_collision_002", (0.0007,)),
        )

    def set_attached(self, attached: bool) -> None:
        self.attachment_requests.append(attached)

    def sample(self) -> PoseSample:
        samples = (
            PoseSample((0.020, -0.280, 0.165), (0.020, -0.263, 0.200)),
            PoseSample((0.020, -0.280, 0.165), (0.020, -0.263, 0.200)),
            PoseSample((0.020, -0.280, 0.167), (0.020, -0.263, 0.202)),
            PoseSample((0.020, -0.280, 0.167), (0.020, -0.263, 0.202)),
            PoseSample((0.020, -0.280, 0.165), (0.020, -0.263, 0.202)),
        )
        value = samples[min(self.sample_index, len(samples) - 1)]
        self.sample_index += 1
        return value

    def attachment_state(self) -> str:
        return "attached" if self.attachment_requests[-1] else "detached"

    def solver_stable(self) -> bool:
        return True

    def original_collision_plugin_loaded(self) -> bool:
        return False


def test_live_gate_executes_ladders_exact_micro_lift_and_detach_contract() -> None:
    backend = FakeLiveBackend()
    evidence = LiveAttachmentGate(backend).run()
    assert [len(path) for path in backend.arm_paths] == [10, 5, 1, 1]
    assert backend.arm_paths[-1][-1] == pytest.approx((
        -0.0002062266287315138, 0.46262046903357984, 0.21277364017949124,
        0.8648894480356747, 0.0005764164414532356,
    ))
    assert backend.gripper_targets == pytest.approx([
        0.465038, -0.047608632840292, 0.465038,
    ])
    assert backend.attachment_requests == [False, True, False]
    assert evidence.bilateral_contact_before_attach
    assert evidence.micro_lift_world_z == pytest.approx(0.002)
    assert evidence.attached and evidence.detached
    assert evidence.object_settled_independently


def test_live_gate_retries_missing_moving_contact_in_one_milliradian_steps() -> None:
    class RetryBackend(FakeLiveBackend):
        def contacts(self) -> tuple[ContactPair, ...]:
            fixed = ContactPair(
                "plastic_cup::body::wall_near",
                "so101::gripper::fixed_fingertip_pad_collision_003", (0.0004,),
            )
            if self.gripper_targets[-1] == pytest.approx(-0.048608632840292):
                return (fixed, ContactPair(
                    "plastic_cup::body::wall_near",
                    "so101::jaw::moving_fingertip_pad_collision_002", (0.00035,),
                ))
            return (fixed,)

    backend = RetryBackend()
    evidence = LiveAttachmentGate(backend).run()
    assert evidence.bilateral_contact_before_attach
    assert backend.gripper_targets[:4] == pytest.approx([
        0.465038, -0.047608632840292, 0.465038, -0.048608632840292,
    ])
