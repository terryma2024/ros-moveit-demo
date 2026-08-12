"""Bounded joint-state and TCP observation for planning evidence."""

import time
from typing import Any, Callable

from ...core.domain import Failure, FailureCategory
from ..trajectory.evidence import RobotStateEvidence


class RobotStateObserver:
    def __init__(
        self,
        joint_source: Callable[[], Any],
        tcp_source: Callable[[], Any],
        expected_joints: tuple[str, ...],
        progress: Callable[[], None] = lambda: None,
    ) -> None:
        self._joint_source = joint_source
        self._tcp_source = tcp_source
        self._expected_joints = expected_joints
        self._progress = progress

    def sample(self, timeout_s: float) -> RobotStateEvidence | Failure:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            joint_state = self._joint_source()
            tcp = self._tcp_source()
            if joint_state is not None and tcp is not None:
                index = {name: offset for offset, name in enumerate(joint_state.name)}
                if all(name in index for name in self._expected_joints):
                    positions = tuple(
                        float(joint_state.position[index[name]]) for name in self._expected_joints
                    )
                    velocities = tuple(
                        float(joint_state.velocity[index[name]])
                        if len(joint_state.velocity) > index[name]
                        else 0.0
                        for name in self._expected_joints
                    )
                    return RobotStateEvidence(
                        self._expected_joints,
                        positions,
                        velocities,
                        tuple(tcp),
                    )
            self._progress()
            time.sleep(0.001)
        return Failure(
            FailureCategory.OBSERVATION,
            "ROBOT_STATE_TIMEOUT",
            "joint state or TCP unavailable",
        )
