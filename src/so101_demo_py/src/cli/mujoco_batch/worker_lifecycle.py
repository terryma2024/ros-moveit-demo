"""Worker slots, goals, leases and recovery of the batch composition."""

from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import sys
import time

from so101_demo.cli.mujoco_batch.common import CliError, _lease_wire
from so101_demo.cli.mujoco_batch.rpc_proxies import _resource_from_dict
from so101_demo.cli.mujoco_batch.worker_process import (
    _build_worker_from_spec,
    _worker_results_failed,
)
from so101_demo.parallel_batch.contracts import (
    WorkerState,
)
from so101_demo.runtime.parallel_ipc import (
    IpcError,
)


class WorkerLifecycle:
    def _remove_stale_worker_sockets(self):
        """Remove only prior generation sockets after exact process fencing."""
        ipc_root = self.allocator.ipc_root
        for worker in self.resource_manifest.workers:
            for name in (f"{worker.worker_id}.sock", f"{worker.worker_id}-control.sock"):
                path = ipc_root / name
                try:
                    info = path.lstat()
                except FileNotFoundError:
                    continue
                if (
                    not stat.S_ISSOCK(info.st_mode)
                    or info.st_uid != os.getuid()
                ):
                    raise CliError("RECOVERY_STALE_SOCKET_INVALID")
                path.unlink()

    def _readmit_recovered_slots(self):
        """Rotate every reusable slot after replay has adjudicated old leases."""
        snapshot = self.coordinator.tick()
        admitted = set()
        for base in self.resource_manifest.workers:
            prior = snapshot.workers.get(base.worker_id)
            prior_generation = base.generation if prior is None else prior.generation
            if prior_generation < base.generation:
                raise CliError("RECOVERY_WORKER_GENERATION_ROLLBACK")
            current = base
            while current.generation < prior_generation + 1:
                current = self.allocator.replace(
                    current.worker_id, expected_generation=current.generation
                )
            if prior is None:
                self.coordinator.register_worker(
                    current.worker_id, generation=current.generation
                )
                admitted.add(current.worker_id)
                continue
            if prior.lease is not None:
                raise CliError("RECOVERY_ACTIVE_LEASE_NOT_ADJUDICATED")
            if prior.state is WorkerState.RECOVERING:
                deadline = prior.recovery_deadline_monotonic_s
                if deadline is None or self._clock() >= deadline:
                    self.coordinator.tick()
                    continue
                self.coordinator.register_worker(
                    current.worker_id,
                    generation=current.generation,
                    recovery_deadline_monotonic_s=deadline,
                )
                final = self.coordinator.record_recovery(
                    current.worker_id,
                    generation=current.generation,
                    succeeded=True,
                    fenced=True,
                    owned_processes_stopped=True,
                    controllers_stopped=True,
                    readmitted=True,
                    recovery_deadline_monotonic_s=deadline,
                )
                if final.state is not WorkerState.AVAILABLE:
                    raise CliError("RECOVERY_WORKER_READMISSION_FAILED")
                admitted.add(current.worker_id)
            elif prior.state is WorkerState.AVAILABLE:
                final = self.coordinator.register_worker(
                    current.worker_id, generation=current.generation
                )
                if final.state is not WorkerState.AVAILABLE:
                    raise CliError("RECOVERY_WORKER_READMISSION_FAILED")
                admitted.add(current.worker_id)
            elif prior.state not in {WorkerState.QUARANTINED, WorkerState.STOPPED}:
                raise CliError("RECOVERY_WORKER_STATE")
        return frozenset(admitted)

    def _stop_new_leases(self):
        self.coordinator.request_stop(reason="SUPERVISOR_SHUTDOWN")
        return self._worker_control("stop")

    def _settle_shared_dependency_failure(self):
        """Let active leases reach terminal or immutable stage deadlines."""
        snapshot = self.coordinator.snapshot()
        while snapshot.broker_recovery_failed and snapshot.terminal_reason is None:
            active = [
                worker for worker in snapshot.workers.values()
                if worker.lease is not None
            ]
            if not active:
                snapshot = self.coordinator.tick()
                break
            deadlines = [snapshot.batch_deadline_monotonic_s]
            for worker in active:
                deadlines.extend(value for value in (
                    worker.lease.lease_deadline_monotonic_s,
                    worker.stage_deadline_monotonic_s,
                    worker.heartbeat_deadline_monotonic_s,
                ) if value is not None)
            deadline = min(deadlines)
            now = self._clock()
            if now < deadline:
                self._sleep(min(0.01, deadline - now))
            snapshot = self.coordinator.tick()
        return snapshot

    def _worker_control(self, operation):
        if getattr(self, "_worker_children_reaped", False):
            return True
        okay = True
        for control in self.worker_controls:
            try:
                okay = control.call(operation) is True and okay
            except Exception:
                okay = False
        return okay

    def _cancel_worker_goals(self):
        return self._worker_control("cancel_motion")

    def _confirm_worker_goals_cancelled(self):
        return self._worker_control("confirm_no_controller_goal")

    def _request_worker_recovery(self):
        return self._worker_control("recover")

    @staticmethod
    def worker_command(path):
        """The Worker child: the running interpreter and module, an absolute command that no PATH can change."""
        return (sys.executable, "-m", "so101_demo.cli.mujoco_parallel_batch", "--internal-worker", str(path))

    def _start_workers(self):
        self._check_fixed_web_stop()
        adaptive_processes = {}
        for path, resources in zip(
            self.worker_specs, self.resource_manifest.workers, strict=True
        ):
            self._check_fixed_web_stop()
            command = self.worker_command(path)
            process = self.supervisor.start(
                "worker", command, environment=dict(resources.environment)
            )
            if self.adaptive_context is not None:
                adaptive_processes[resources.worker_id] = process
        if self.adaptive_context is not None:
            self._adaptive_worker_processes = adaptive_processes
            self._release_adaptive_workers()
            return
        if not callable(getattr(self.supervisor, "assert_healthy", None)):
            return
        deadline = time.monotonic() + self.spec.config.heartbeat_timeout_s
        while time.monotonic() < deadline:
            self._check_fixed_web_stop()
            self.supervisor.assert_healthy()
            if all(
                control.socket_path.is_socket()
                and not control.socket_path.is_symlink()
                and stat.S_IMODE(control.socket_path.stat().st_mode) == 0o600
                for control in self.worker_controls
            ):
                return
            time.sleep(0.01)
        raise CliError("WORKER_CONTROL_READY_TIMEOUT")

    def _release_adaptive_workers(self):
        """Collect fresh readiness, durably linearize, then release every Worker."""

        if not callable(getattr(self.supervisor, "assert_healthy", None)):
            raise CliError("WORKER_HEALTH_PROBE_REQUIRED")
        deadline = self._clock() + (
            self.adaptive_context.options.worker_start_timeout_s
        )
        receipts = {}

        def readiness_or_none(control):
            try:
                return control.readiness()
            except (IpcError, OSError):
                # A live readiness probe may outlast the request-local IPC
                # deadline under multi-stack startup load.  No receipt means
                # no release authority; retry only within the shared startup
                # deadline and keep every schema/identity check below.
                return None

        while self._clock() < deadline:
            self.supervisor.assert_healthy()
            for control in self.worker_controls:
                if control.worker_id not in receipts:
                    receipt = readiness_or_none(control)
                    if receipt is not None:
                        receipts[control.worker_id] = receipt
            if len(receipts) == len(self.worker_controls):
                break
            self._sleep(min(0.01, max(0.0, deadline - self._clock())))
        if len(receipts) != len(self.worker_controls):
            raise CliError("WORKER_READY_TIMEOUT")
        final_receipts = []
        for control in self.worker_controls:
            receipt = None
            while receipt is None and self._clock() < deadline:
                self.supervisor.assert_healthy()
                receipt = readiness_or_none(control)
                if receipt is None:
                    self._sleep(min(0.01, max(0.0, deadline - self._clock())))
            now = self._clock()
            process = self._adaptive_worker_processes.get(control.worker_id)
            if receipt is None or (
                receipt.worker_id != control.worker_id
                or receipt.generation != control.generation
                or not receipt.coordinator_registered
                or not receipt.runtime_ready
                or not receipt.broker_ready
                or receipt.broker_generation != (self.broker_generation or 1)
                or process is None
                or receipt.process_start_ticks
                != getattr(process, "start_time", None)
                or receipt.observed_monotonic_s > now
                or now - receipt.observed_monotonic_s > 1.0
                or now >= deadline
            ):
                raise CliError("WORKER_READINESS_INVALID")
            final_receipts.append(receipt)
        self._pool_running_recorder(tuple(final_receipts))
        for control in self.worker_controls:
            if self._clock() >= deadline:
                raise CliError("POOL_RUNTIME_RELEASE_FAILED")
            if control.release_start() is not True:
                raise CliError("POOL_RUNTIME_RELEASE_FAILED")

    def _active_lease(self, message):
        worker = self.coordinator.snapshot().workers.get(message["worker_id"])
        if worker is None or worker.lease is None:
            raise CliError("RPC_ACTIVE_LEASE_REQUIRED")
        if _lease_wire(worker.lease) != message["lease"]:
            raise CliError("RPC_STALE_LEASE")
        return worker.lease

    def _run_worker_local(self, path):
        resources = _resource_from_dict(json.loads(Path(path).read_text())["resources"])
        side_effects = (
            None if self._runtime_side_effects_factory is None
            else self._runtime_side_effects_factory(resources)
        )
        worker, runtime = _build_worker_from_spec(
            path, runtime_side_effects=side_effects
        )
        self.last_local_components = (worker, runtime)
        try:
            results = worker.run()
            return int(
                _worker_results_failed(
                    results,
                    adaptive_workers=getattr(self, "adaptive_context", None)
                    is not None,
                )
            )
        finally:
            runtime.shutdown_owned()
