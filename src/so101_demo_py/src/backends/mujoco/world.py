"""MuJoCo implementation of the neutral physical-world port."""

from __future__ import annotations

from typing import Any

from ...ports.evidence import (
    ContactEvidence,
    PoseEvidence,
    ReceivedWorldEvidence,
    TwistEvidence,
    WorldEvidence,
)
from ...ports.world import ResetReceipt


def _contact(value: Any) -> ContactEvidence:
    return ContactEvidence(
        collision1=value.geom1,
        collision2=value.geom2,
        position_m=value.position_world,
        normal=value.normal_world,
        normal_force_n=value.normal_force_n,
        backend_metadata={
            "body1_id": value.body1_id,
            "geom1_id": value.geom1_id,
            "body1": value.body1,
            "body2_id": value.body2_id,
            "geom2_id": value.geom2_id,
            "body2": value.body2,
            "signed_distance_m": value.signed_distance_m,
        },
    )


def convert_evidence(value: Any) -> WorldEvidence:
    contacts = (
        *value.left_fingertip_contacts,
        *value.right_fingertip_contacts,
        *value.other_object_contacts,
    )
    return WorldEvidence(
        backend="mujoco",
        session_id=value.simulation_session_id,
        reset_epoch=value.reset_epoch,
        simulation_step=value.simulation_step,
        simulation_time_s=value.simulation_time_s,
        object_pose=PoseEvidence(
            value.object_state.position_world,
            value.object_state.orientation_xyzw,
        ),
        object_twist=TwistEvidence(
            value.object_state.linear_velocity_world,
            value.object_state.angular_velocity_world,
        ),
        contacts=tuple(_contact(contact) for contact in contacts),
        evidence_loss=False,
        truncated=value.truncated,
        backend_metadata={
            "frame_id": value.frame_id,
            "publisher_sequence": value.publisher_sequence,
            "paused": value.paused,
            "object_body_id": value.object_state.body_id,
            "object_body": value.object_state.body,
            "minimum_signed_distance_m": value.minimum_signed_distance_m,
            "maximum_normal_force_n": value.maximum_normal_force_n,
        },
    )


class MujocoWorldAdapter:
    def __init__(self, observer: Any, resetter: Any) -> None:
        self._observer = observer
        self._resetter = resetter
        self._last_identity: tuple[str, int] | None = None
        self._last_publisher_sequence = -1
        self._last_simulation_step = -1

    def _convert_fresh(self, raw: Any) -> WorldEvidence:
        identity = (raw.simulation_session_id, raw.reset_epoch)
        if identity == self._last_identity and (
            raw.publisher_sequence < self._last_publisher_sequence
            or raw.simulation_step < self._last_simulation_step
        ):
            raise ValueError("MuJoCo evidence sequence or simulation step regressed")
        self._last_identity = identity
        self._last_publisher_sequence = raw.publisher_sequence
        self._last_simulation_step = raw.simulation_step
        return convert_evidence(raw)

    def snapshot(self) -> WorldEvidence:
        return self._convert_fresh(self._observer.snapshot())

    def snapshot_with_receipt(self) -> ReceivedWorldEvidence:
        received = self._observer.snapshot_with_receipt()
        return ReceivedWorldEvidence(
            self._convert_fresh(received.evidence), received.received_monotonic_s
        )

    def reset(self, keyframe: str) -> ResetReceipt:
        receipt = self._resetter.reset(keyframe)
        return ResetReceipt(
            old_epoch=receipt.old_epoch,
            new_epoch=receipt.new_epoch,
            keyframe=receipt.keyframe,
            simulation_step=receipt.simulation_step,
            session_id=receipt.simulation_session_id,
            observed_after_request=(
                receipt.new_epoch == receipt.old_epoch + 1 and receipt.simulation_step == 0
            ),
        )
