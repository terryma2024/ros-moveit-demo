"""Motion cancellation, physics pause and resume and recovery."""

from __future__ import annotations

import time

from so101_demo.runtime.parallel_ros_ports.observations import (
    ShutdownObservation,
    cancel_and_confirm_parallel_goals,
    observe_no_parallel_goals,
    observe_worker_shutdown,
)


class RecoveryPorts:
    def cancel_motion(self, lease):
        call = self.dependencies.get("cancel_motion")
        if call is not None:
            return call(lease)
        del lease
        return cancel_and_confirm_parallel_goals(timeout_s=5.0)

    def confirm_no_controller_goal(self, lease):
        call = self.dependencies.get("confirm_no_controller_goal")
        if call is not None:
            return call(lease)
        if lease.attempt_id not in self._reset_receipts:
            return False
        return observe_no_parallel_goals(timeout_s=5.0)

    def resume_physics(self, lease, reset_receipt):
        call = self.dependencies.get("resume_physics")
        if call is not None:
            return call(lease, reset_receipt)
        if (
            reset_receipt.simulation_session_id != self.resources.session_id
            or reset_receipt.reset_epoch_value is None
        ):
            return False
        return self._retained_pause_control().set_paused(False)

    def pause_physics(self, lease, reset_receipt):
        call = self.dependencies.get("pause_physics")
        if call is not None:
            return call(lease, reset_receipt)
        if (
            reset_receipt.simulation_session_id != self.resources.session_id
            or reset_receipt.reset_epoch_value is None
        ):
            return False
        return self._retained_pause_control().set_paused(True)

    def _retained_pause_control(self):
        if self._pause_control is None:
            factory = self.dependencies.get("pause_control_factory")
            if factory is None:
                from so101_demo.backends.mujoco.lifecycle import MujocoPauseControl

                factory = MujocoPauseControl
            self._pause_control = factory()
        return self._pause_control

    def _close_pause_control(self):
        if self._pause_control is None:
            return
        control, self._pause_control = self._pause_control, None
        control.close()

    def recovery(self, worker_id, generation, deadline):
        call = self.dependencies.get("recovery")
        if call is not None:
            return call(worker_id, generation, deadline)
        if time.monotonic() >= deadline:
            return False
        if worker_id != self.resources.worker_id or generation != self.resources.generation:
            return False
        if self._planner is not None:
            self._planner.close()
            self._planner = None
        observe = self.dependencies.get("observe_shutdown", observe_worker_shutdown)
        observed = observe(
            self.resources.session_id,
            timeout_s=max(0.001, min(5.0, deadline - time.monotonic())),
        )
        return (
            type(observed) is ShutdownObservation
            and time.monotonic() < deadline
            and not observed.remaining_session_pids
            and not observed.worker_node_fqns
            and observed.node_graph_stable
        )
