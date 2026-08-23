"""Zero-I/O, fail-closed real-arm backend placeholder."""

from __future__ import annotations

from dataclasses import dataclass

from ...core.domain import ExecutionRunStatus

ERROR_CODE = "REAL_HARDWARE_NOT_CONFIGURED"


@dataclass(frozen=True, slots=True)
class RejectedResult:
    accepted: bool = False
    error_code: str = ERROR_CODE
    run_status: ExecutionRunStatus = ExecutionRunStatus.REJECTED


def reject() -> RejectedResult:
    return RejectedResult()


class RealStubBackend:
    """Reject every runtime operation without discovering or opening hardware."""

    def readiness(self, _timeout_s=None) -> RejectedResult:
        return reject()

    def current_joint_state(self, _timeout_s=None) -> RejectedResult:
        return reject()

    def plan_joint_waypoints(self, _request=None) -> RejectedResult:
        return reject()

    def plan_tcp_motion(self, _request=None) -> RejectedResult:
        return reject()

    def execute(self, _plan=None) -> RejectedResult:
        return reject()

    def command_gripper(self, _request=None) -> RejectedResult:
        return reject()

    def reset(self, _keyframe=None) -> RejectedResult:
        return reject()

    def stop(self, _reason=None) -> RejectedResult:
        return reject()

    def recover(self, _evidence=None) -> RejectedResult:
        return reject()

    def snapshot(self) -> RejectedResult:
        return reject()

    def snapshot_with_receipt(self) -> RejectedResult:
        return reject()

    def pause(self, _paused=None) -> RejectedResult:
        return reject()

    def shutdown(self, _timeout_s=None) -> RejectedResult:
        return reject()

    def add_world_object(self, _request=None) -> RejectedResult:
        return reject()

    def attach_shadow(self, _object_id=None, _link_name=None) -> RejectedResult:
        return reject()

    def detach_shadow(self, _object_id=None) -> RejectedResult:
        return reject()

    def synchronize_object_pose(self, _object_id=None, _pose=None) -> RejectedResult:
        return reject()

    def temporary_allow_collision(self, _pair=None) -> RejectedResult:
        return reject()
