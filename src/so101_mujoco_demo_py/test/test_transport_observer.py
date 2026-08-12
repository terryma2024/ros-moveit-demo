from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from so101_mujoco_demo_py.dynamic_transport_evidence import (
    AtomicTransportEvidenceStore,
    PhysicsContactSample,
    PhysicsStepChunk,
    PhysicsStepSample,
    TransportBoundaryKind,
)
from so101_mujoco_demo_py.mujoco.transport_observer import (
    BoundaryActionClient,
    CancellationAck,
    DynamicTransportEvidenceObserver,
    EvidenceInvalid,
    HazardLatch,
    ReactionLatencyInvalid,
    publisher_provenance,
)


def contact(side: str, force_n: float) -> PhysicsContactSample:
    return PhysicsContactSample(
        side=side,
        object_body="plastic_cup",
        object_geom="cup_collision",
        other_body=f"{side}_jaw",
        other_geom=f"{side}_fingertip",
        signed_distance_m=-0.001,
        normal_force_n=force_n,
        normal_world=(1.0, 0.0, 0.0),
    )


def sample(step: int, force_n: float = 1.0) -> PhysicsStepSample:
    left = contact("left", force_n)
    right = contact("right", force_n / 2.0)
    return PhysicsStepSample(
        simulation_session_id="EXP-110-session",
        reset_epoch=4,
        physics_step=step,
        simulation_time_s=step * 0.002,
        object_pose_world_xyz_xyzw=(0.0, 0.0, 0.2, 0.0, 0.0, 0.0, 1.0),
        object_twist_world_linear_angular=(0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        maximum_normal_force_n=force_n,
        left_fingertip_total_normal_force_n=force_n,
        right_fingertip_total_normal_force_n=force_n / 2.0,
        fingertip_max_single_contact_force_n=force_n,
        global_max_single_contact_force_n=force_n,
        left_fingertip_compression_m=0.001,
        right_fingertip_compression_m=0.001,
        net_contact_force_world_n=(force_n * 1.5, 0.0, 0.0),
        truncated=False,
        left_fingertip_contacts=(left,),
        right_fingertip_contacts=(right,),
        other_object_contacts=(),
    )


def chunk(first: int, last: int, sequence: int = 0) -> PhysicsStepChunk:
    samples = tuple(sample(step) for step in range(first, last + 1))
    return PhysicsStepChunk(
        chunk_sequence=sequence,
        simulation_session_id="EXP-110-session",
        reset_epoch=4,
        first_physics_step=first,
        last_physics_step=last,
        first_simulation_time_s=first * 0.002,
        last_simulation_time_s=last * 0.002,
        failed_publish_attempts=0,
        evidence_loss=False,
        samples=samples,
    )


def observer(tmp_path: Path) -> DynamicTransportEvidenceObserver:
    return DynamicTransportEvidenceObserver(
        simulation_session_id="EXP-110-session",
        reset_epoch=4,
        store=AtomicTransportEvidenceStore(tmp_path, run_id="EXP-110"),
        maximum_reaction_steps=25,
    )


def test_goal_dispatch_is_the_first_dynamic_boundary(tmp_path: Path) -> None:
    value = observer(tmp_path)
    value.accept_chunk(chunk(100, 104))

    boundary = value.mark_goal_dispatched(waypoint=1)

    assert boundary.kind is TransportBoundaryKind.PHASE_START
    assert boundary.physics_step == 104
    assert value.boundaries[1].kind is TransportBoundaryKind.WAYPOINT_START
    assert value.boundaries[1].physics_step == 104


def test_session_mismatch_is_rejected_with_structured_durable_identity(tmp_path: Path) -> None:
    value = observer(tmp_path)
    wrong_session = replace(chunk(100, 104), simulation_session_id="producer-fallback")

    with pytest.raises(EvidenceInvalid, match="chunk simulation session mismatch") as caught:
        value.accept_chunk(wrong_session)
    index_path = value.close_invalid(caught.value)

    document = json.loads(index_path.read_text(encoding="utf-8"))
    assert document["outcome_class"] == "INVALID_EVIDENCE"
    assert document["identity_mismatch"] == {
        "actual_session_id": "producer-fallback",
        "expected_session_id": "EXP-110-session",
        "message_kind": "PhysicsStepEvidenceChunk",
        "topic": "/so101/simulation/physics_step_chunks",
    }
    assert document["first_chunk_header"] == {
        "chunk_sequence": 0,
        "evidence_loss": False,
        "failed_publish_attempts": 0,
        "first_physics_step": 100,
        "first_simulation_time_s": 0.2,
        "last_physics_step": 104,
        "last_simulation_time_s": 104 * 0.002,
        "reset_epoch": 4,
        "sample_count": 5,
        "simulation_session_id": "producer-fallback",
    }
    assert document["chunks"] == []
    assert document["boundaries"] == []


def test_empty_loss_sentinel_keeps_identity_and_is_rejected_as_evidence_loss(
    tmp_path: Path,
) -> None:
    value = observer(tmp_path)
    sentinel = replace(
        chunk(100, 104),
        evidence_loss=True,
        failed_publish_attempts=1,
        samples=(),
    )

    with pytest.raises(EvidenceInvalid, match="chunk evidence loss latched") as caught:
        value.accept_chunk(sentinel)
    index_path = value.close_invalid(caught.value)

    document = json.loads(index_path.read_text(encoding="utf-8"))
    assert document["first_chunk_session_id"] == "EXP-110-session"
    assert document["first_chunk_header"] == {
        "chunk_sequence": 0,
        "evidence_loss": True,
        "failed_publish_attempts": 1,
        "first_physics_step": 100,
        "first_simulation_time_s": 0.2,
        "last_physics_step": 104,
        "last_simulation_time_s": 104 * 0.002,
        "reset_epoch": 4,
        "sample_count": 0,
        "simulation_session_id": "EXP-110-session",
    }
    assert "identity_mismatch" not in document


def test_first_identity_mismatch_is_not_overwritten(tmp_path: Path) -> None:
    value = observer(tmp_path)
    errors = []
    for actual in ("producer-first", "producer-later"):
        with pytest.raises(EvidenceInvalid) as caught:
            value.accept_chunk(replace(chunk(100, 104), simulation_session_id=actual))
        errors.append(caught.value)
        value.record_invalid(caught.value)

    index_path = value.close_invalid(errors[-1])
    document = json.loads(index_path.read_text(encoding="utf-8"))
    assert document["first_chunk_session_id"] == "producer-first"
    assert document["identity_mismatch"]["actual_session_id"] == "producer-first"


def test_snapshot_identity_mismatch_uses_snapshot_topic_and_kind(tmp_path: Path) -> None:
    value = observer(tmp_path)

    with pytest.raises(EvidenceInvalid) as caught:
        value.checkpoint_snapshot_session("snapshot-producer")
    index_path = value.close_invalid(caught.value)

    document = json.loads(index_path.read_text(encoding="utf-8"))
    assert document["identity_mismatch"] == {
        "actual_session_id": "snapshot-producer",
        "expected_session_id": "EXP-110-session",
        "message_kind": "SimulationEvidence",
        "topic": "/so101/simulation/evidence",
    }


def test_publisher_provenance_records_count_node_and_gid() -> None:
    class Endpoint:
        node_name = "mujoco_ros2_control_node"
        node_namespace = "/"
        endpoint_gid = bytes.fromhex("001122aabb")

    class Node:
        def get_publishers_info_by_topic(self, topic: str):
            assert topic == "/so101/simulation/physics_step_chunks"
            return [Endpoint()]

    assert publisher_provenance(
        Node(),
        topic="/so101/simulation/physics_step_chunks",
        message_kind="PhysicsStepEvidenceChunk",
    ) == {
        "message_kind": "PhysicsStepEvidenceChunk",
        "publisher_count": 1,
        "publishers": [
            {
                "endpoint_gid": "001122aabb",
                "node_name": "mujoco_ros2_control_node",
                "node_namespace": "/",
            }
        ],
        "topic": "/so101/simulation/physics_step_chunks",
    }


def test_observer_checkpoints_both_topic_publishers_before_first_chunk(tmp_path: Path) -> None:
    value = observer(tmp_path)
    provenance = {
        "snapshot": {"topic": "/so101/simulation/evidence", "publisher_count": 1},
        "physics_step_chunk": {
            "topic": "/so101/simulation/physics_step_chunks",
            "publisher_count": 1,
        },
    }

    value.checkpoint_producer_provenance(provenance)
    value.checkpoint_snapshot_session("EXP-110-session")
    value.accept_chunk(chunk(100, 104))

    document = json.loads((tmp_path / "run-index.json").read_text(encoding="utf-8"))
    assert document["expected_session_id"] == "EXP-110-session"
    assert document["first_chunk_session_id"] == "EXP-110-session"
    assert document["first_snapshot_session_id"] == "EXP-110-session"
    assert document["publisher_provenance"] == provenance


def test_action_proxy_observes_exact_dispatch_and_cancel_call_boundaries() -> None:
    events: list[str] = []

    class GoalHandle:
        accepted = True

        def cancel_goal_async(self):
            events.append("cancel_sent")
            return object()

    class Future:
        def done(self):
            return True

        def result(self):
            return GoalHandle()

    class Client:
        def wait_for_server(self, *, timeout_sec: float):
            return timeout_sec > 0.0

        def send_goal_async(self, goal):
            events.append("goal_sent")
            return Future()

    proxy = BoundaryActionClient(
        Client(),
        on_goal_dispatched=lambda: events.append("goal_dispatched"),
        on_cancellation_requested=lambda: events.append("cancellation_requested"),
    )

    handle = proxy.send_goal_async(object()).result()
    handle.cancel_goal_async()

    assert events == [
        "goal_sent",
        "goal_dispatched",
        "cancellation_requested",
        "cancel_sent",
    ]


def test_action_proxy_measurement_error_cannot_suppress_cancel() -> None:
    cancel_count = [0]

    class GoalHandle:
        def cancel_goal_async(self):
            cancel_count[0] += 1
            return object()

    class Future:
        def result(self):
            return GoalHandle()

    class Client:
        def send_goal_async(self, goal):
            return Future()

    proxy = BoundaryActionClient(
        Client(),
        on_goal_dispatched=lambda: None,
        on_cancellation_requested=lambda: (_ for _ in ()).throw(RuntimeError("measurement failed")),
    )

    proxy.send_goal_async(object()).result().cancel_goal_async()
    assert cancel_count == [1]


def test_first_hazard_latch_is_immutable(tmp_path: Path) -> None:
    value = observer(tmp_path)
    first = HazardLatch("EXP-110-session", 4, 107, 0.214, 11.60, 11.60, False)
    later = HazardLatch("EXP-110-session", 4, 112, 0.224, 12.50, 11.60, False)

    value.accept_hazard(first)
    value.accept_hazard(later)

    assert value.hazard == first


def test_cancellation_request_latency_is_bounded_in_physics_steps(tmp_path: Path) -> None:
    value = observer(tmp_path)
    value.accept_hazard(HazardLatch("EXP-110-session", 4, 100, 0.2, 11.60, 11.60, False))

    assert value.mark_cancellation_requested(125) == 25

    with pytest.raises(ReactionLatencyInvalid, match="25 physics steps"):
        value.mark_cancellation_requested(126)


def test_plugin_ack_is_a_conservative_physics_step_bound_for_cancel_request(
    tmp_path: Path,
) -> None:
    value = observer(tmp_path)
    value.accept_hazard(HazardLatch("EXP-110-session", 4, 100, 0.2, 11.60, 11.60, False))

    value.accept_cancellation_ack(CancellationAck("EXP-110-session", 4, 100, 0, 123, 0.246))

    assert value.cancellation_request_upper_bound_step == 123
    assert value.reaction_upper_bound_steps == 23


def test_safety_abort_keeps_hashed_partial_evidence_readable(tmp_path: Path) -> None:
    value = observer(tmp_path)
    value.accept_chunk(chunk(100, 104))
    value.mark_goal_dispatched(waypoint=1)
    value.accept_hazard(HazardLatch("EXP-110-session", 4, 103, 0.206, 11.60, 11.60, False))
    value.mark_cancellation_requested(104)

    index_path = value.close_safety_abort()

    document = json.loads(index_path.read_text(encoding="utf-8"))
    assert document["outcome_class"] == "VALID_SAFETY_ABORT"
    assert document["trigger_physics_step"] == 103
    assert document["cancellation_request_physics_step"] == 104
    assert document["reaction_steps"] == 1
    assert document["boundaries"][0]["kind"] == "PHASE_START"
    for item in document["chunks"]:
        path = tmp_path / item["path"]
        assert path.is_file()
