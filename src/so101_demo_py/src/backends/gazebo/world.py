"""Gazebo implementation of the neutral physical-world port."""

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
        collision1=str(value.collision1),
        collision2=str(value.collision2),
        position_m=tuple(value.position_world),
        normal=tuple(value.normal_world),
        normal_force_n=float(value.normal_force_n),
        backend_metadata={"contact_depth_m": float(value.contact_depth_m)},
    )


def convert_evidence(value: Any) -> WorldEvidence:
    pose = tuple(value.object_pose_world)
    twist = tuple(value.object_twist_world)
    return WorldEvidence(
        backend="gazebo",
        session_id=str(value.simulation_session_id),
        reset_epoch=int(value.reset_epoch),
        simulation_step=int(value.simulation_step),
        simulation_time_s=float(value.simulation_time_s),
        object_pose=PoseEvidence(pose[:3], pose[3:]),
        object_twist=TwistEvidence(twist[:3], twist[3:]),
        contacts=tuple(_contact(contact) for contact in value.contacts),
        evidence_loss=bool(value.evidence_loss),
        truncated=bool(value.truncated),
        backend_metadata={
            "bridge_identity": str(value.bridge_identity),
            "contact_receipt_sequence": int(value.contact_receipt_sequence),
            "partition": str(value.partition),
            "pose_receipt_sequence": int(value.pose_receipt_sequence),
            "world_stats": dict(value.world_stats),
        },
    )


class GazeboWorldAdapter:
    def __init__(self, observer: Any, resetter: Any) -> None:
        self._observer = observer
        self._resetter = resetter
        self._last_identity: tuple[str, int] | None = None
        self._last_step = -1

    def _convert_fresh(self, raw: Any) -> WorldEvidence:
        identity = (str(raw.simulation_session_id), int(raw.reset_epoch))
        step = int(raw.simulation_step)
        if identity == self._last_identity and step < self._last_step:
            raise ValueError("Gazebo simulation step regressed")
        self._last_identity = identity
        self._last_step = step
        return convert_evidence(raw)

    def snapshot(self) -> WorldEvidence:
        return self._convert_fresh(self._observer.snapshot())

    def snapshot_with_receipt(self) -> ReceivedWorldEvidence:
        received = self._observer.snapshot_with_receipt()
        return ReceivedWorldEvidence(
            self._convert_fresh(received.observation),
            received.received_monotonic_s,
        )

    def reset(self, keyframe: str) -> ResetReceipt:
        if self._resetter is None:
            raise RuntimeError("Gazebo reset adapter is not configured")
        return self._resetter.reset(keyframe)
