"""The task gates' readiness check of the borrowed stack, without a process per call.

`RepeatableActStackReadyProbe` runs the `act_stack_ready` observer as a new process on every call (an interpreter, rclpy and the
graph discovery each time, seconds under load, several calls a task). Inside an ACT instance process the same observation runs
in a `StackReadinessSession` kept for the instance: the same code, one context and the same clients. A verdict other than a
validated "ready" is never taken from the kept session; the process decides it, exactly as before, so the kept session can only
save time and never turn a stack not ready into a fault or the other way round on its own say-so.
"""

from __future__ import annotations

import os
import threading
import time

from so101_teleop.unified.act_stack_probes import RepeatableActStackReadyProbe

#: how long the kept session looks for "ready" before the process is asked; a stack that is ready is ready within this
KEPT_ATTEMPT_TIMEOUT_S = 10.0


class KeptActStackReadyCheck(RepeatableActStackReadyProbe):
    def __init__(self, *args, kept_attempt_timeout_s: float = KEPT_ATTEMPT_TIMEOUT_S, in_instance=None,
                 make_session=None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        from so101_demo.ros.process_init import in_instance_process

        self.kept_attempt_timeout_s = min(float(kept_attempt_timeout_s), self.timeout_s)
        self._in_instance = in_instance_process if in_instance is None else in_instance
        self._make_session = make_session or self._new_session
        self._lock = threading.Lock()
        self._session = None
        self._expected_checks = self._new_probe().expected_checks

    def _new_session(self):
        from so101_demo.act.rig_profile import DEFAULT_RIG, load_rig_profile
        from so101_demo.cli.act_stack_ready import StackReadinessSession

        launch = self.launch
        rig = DEFAULT_RIG if launch.rig_profile is None else load_rig_profile(launch.rig_profile)
        return StackReadinessSession(session_id=launch.session_id, ros_domain_id=launch.ros_domain_id, rig=rig)

    def close(self) -> None:
        with self._lock:
            session, self._session = self._session, None
        if session is not None:
            session.close()

    def _kept_ready(self) -> bool:
        """True only for a ready verdict whose artifact the stack owner's own validation accepts."""
        from so101_teleop.unified.pick_place_startup_issuer import _validated_observation

        launch = self.launch
        # The observer judges the domain it runs in, and the command line refuses one that is not the launch's.
        if not self._in_instance() or os.environ.get("ROS_DOMAIN_ID") != str(launch.ros_domain_id):
            return False
        import json
        with self._lock:
            try:
                if self._session is None:
                    self._session = self._make_session()
                outcome = self._session.check(self.kept_attempt_timeout_s)
                if not outcome.ready:
                    return False
                _validated_observation(json.dumps(outcome.artifact, sort_keys=True).encode(), session_id=launch.session_id,
                                       ros_domain_id=launch.ros_domain_id, now_ns=self.clock_ns(), checks=self._expected_checks)
                return True
            except Exception:   # noqa: BLE001 - the process answers instead
                session, self._session = self._session, None
                if session is not None:
                    session.close()
                return False

    def __call__(self) -> bool:
        if self._kept_ready():
            return True
        return super().__call__()
