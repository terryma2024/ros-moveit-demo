"""Coordinator RPC and web servers of the batch composition."""

from __future__ import annotations

import threading

from so101_demo.cli.mujoco_batch.common import CliError, _jsonable, _lease_wire
from so101_demo.cli.mujoco_batch.fixed_web_control import _FixedWebStopRequested
from so101_demo.cli.mujoco_batch.rpc_proxies import _validate_rpc_payload


class ServerLifecycle:
    def _coordinator_handler(self, message):
        payload = message["payload"]
        operation = payload.get("operation")
        worker_id = message["worker_id"]
        generation = message["worker_generation"]
        _validate_rpc_payload(payload)
        if operation in {"current_broker", "startup_broker"}:
            snapshot = self.coordinator.snapshot()
            if operation == "startup_broker":
                worker = snapshot.workers.get(worker_id)
                if (
                    self.adaptive_context is None
                    or message["lease"] is not None
                    or worker is None
                    or worker.generation != generation
                    or worker.lease is not None
                    or worker.lease_count != 0
                    or worker.stop_requested
                ):
                    raise CliError("STARTUP_BROKER_WORKER")
            else:
                self._broker_discovery_lease(message)
            if not snapshot.broker_healthy:
                return {
                    "healthy": False,
                    "broker_generation": None,
                    "broker_socket_path": None,
                    "recovery_deadline_monotonic_s": (
                        snapshot.broker_recovery_deadline_monotonic_s
                    ),
                }
            return {
                "healthy": True,
                "broker_generation": self.broker_generation,
                "broker_socket_path": str(self.broker_socket_path),
                "recovery_deadline_monotonic_s": None,
            }
        if operation == "register_worker":
            requested = payload.get("generation")
            ack = self.coordinator.register_worker(
                worker_id,
                generation=requested,
                recovery_deadline_monotonic_s=payload.get("recovery_deadline_monotonic_s"),
            )
            if requested != generation:
                self.authority.advance_generation(worker_id, generation, requested)
            return _jsonable(ack)
        if operation == "grant_lease":
            outcome = self.coordinator.grant_lease_outcome(
                worker_id,
                generation=payload.get("generation"),
                request_key=message["idempotency_key"],
            )
            lease = outcome["lease"]
            if lease is not None:
                self.authority.bind_lease(worker_id, generation, _lease_wire(lease))
            return _jsonable(outcome)
        if operation == "record_recovery":
            values = {key: value for key, value in payload.items() if key != "operation"}
            return _jsonable(self.coordinator.record_recovery(worker_id, **values))
        if operation == "replace_resources":
            return self.allocator.replace(
                worker_id,
                expected_generation=payload.get("expected_generation"),
            ).to_dict()
        lease = self._active_lease(message)
        if operation == "heartbeat":
            return _jsonable(self.coordinator.heartbeat(lease))
        if operation == "heartbeat_teacher":
            return _jsonable(self.coordinator.heartbeat_projection(lease))
        if operation == "ack_lease":
            return _jsonable(self.coordinator.ack_lease(
                lease, request_key=message["idempotency_key"]
            ))
        if operation in {"ack_attempt_started", "ack_validation_started"}:
            method = getattr(self.coordinator, operation)
            return _jsonable(method(
                lease,
                request_key=message["idempotency_key"],
                gate_summary=payload.get("gate_summary"),
            ))
        if operation == "begin_finalizing":
            return _jsonable(self.coordinator.begin_finalizing(
                lease, request_key=message["idempotency_key"]
            ))
        if operation in {"commit_result", "commit_validation"}:
            return _jsonable(getattr(self.coordinator, operation)(
                lease,
                payload.get("location"),
                request_key=message["idempotency_key"],
            ))
        raise CliError("RPC_UNKNOWN_OPERATION")

    def _start_servers(self):
        if self.fixed_control_server is not None:
            self.fixed_control_server.start()
        for server in self.worker_servers:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            self._server_threads.append(thread)

    def _stop_servers(self):
        for server in self.worker_servers:
            server.close()
        for thread in self._server_threads:
            thread.join(timeout=1.0)
        if self.fixed_control_server is not None:
            self.fixed_control_server.close()

    def _fixed_web_stop_requested(self):
        server = getattr(self, "fixed_control_server", None)
        if server is None:
            return False
        server.check_health()
        return self.coordinator.snapshot().terminal_reason == "WEB_CANCEL_REQUESTED"

    def _stop_requested(self):
        """One stop predicate: the owned Web cancel state, and nothing else."""

        return self._fixed_web_stop_requested()

    def _check_fixed_web_stop(self):
        if self._stop_requested():
            raise _FixedWebStopRequested("WEB_CANCEL_REQUESTED")
