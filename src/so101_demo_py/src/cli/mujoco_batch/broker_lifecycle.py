"""Broker generation, container and readiness handling of the batch composition."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time

from so101_demo.cli.mujoco_batch.common import (
    CliError,
    _read_existing_json,
    _write_bytes,
    _write_json,
)
from so101_demo.cli.mujoco_batch.fixed_web_control import _FixedWebStopRequested
from so101_demo.cli.mujoco_batch.outcome import _validate_broker_ready
from so101_demo.parallel_batch.contracts.common import RunMode, WorkerState


class BrokerLifecycle:
    def _broker_runtime_for_generation(self, generation):
        if generation == 1:
            return self.authority.ipc_root / "broker"
        return self.authority.ipc_root / f"broker-g{generation}"

    def _prior_broker_generation(self):
        if self.spec.request.run_mode is RunMode.DRY_RUN:
            return 0
        generations = []
        ipc_root = self.authority.ipc_root
        for path in ipc_root.glob("broker*/broker-spec.json"):
            document = _read_existing_json(path, label="BROKER_SPEC")
            generation = document.get("broker_generation")
            if (
                document.get("batch_id") != self.spec.request.batch_id
                or type(generation) is not int
                or generation <= 0
            ):
                raise CliError("RECOVERY_BROKER_SPEC_IDENTITY")
            expected_root = (
                ipc_root / "broker" if generation == 1
                else ipc_root / f"broker-g{generation}"
            )
            if path.parent != expected_root:
                raise CliError("RECOVERY_BROKER_SPEC_IDENTITY")
            generations.append(generation)
        if not generations or len(generations) != len(set(generations)):
            raise CliError("RECOVERY_BROKER_SPEC_MISSING")
        return max(generations)

    def _prepare_broker_generation(self, generation):
        if type(generation) is not int or generation != self.broker_generation + 1:
            raise CliError("BROKER_GENERATION_SEQUENCE")
        runtime_root = (
            self.authority.ipc_root / "broker"
            if generation == 1
            else self.authority.ipc_root / f"broker-g{generation}"
        )
        runtime_root.mkdir(mode=0o700)
        config_copy = runtime_root / "runtime-config.yaml"
        _write_bytes(config_copy, self.spec.config_path.read_bytes())
        spec_path = runtime_root / "broker-spec.json"
        broker_document = {
            "schema_version": 1,
            "kind": "so101_parallel_broker_runtime",
            "batch_id": self.spec.request.batch_id,
            "coordinator_epoch": self.journal.coordinator_epoch,
            "broker_generation": generation,
            "run_mode": self.spec.request.run_mode.value,
            "image_id": self.spec.provenance.get("image_id"),
            "yolo_weights_sha256": self.spec.yolo_weights_sha256,
            "grounded_manifest_sha256": self.spec.grounded_manifest_sha256,
            # the container route mounts runtime_root at /runtime; a host run names the copy itself, which sits
            # beside the spec
            "config_path": ("/runtime/runtime-config.yaml" if self._uses_production_broker_container
                            else str(config_copy)),
            "request_deadline_s": self.spec.config.heartbeat_timeout_s,
            "max_frame_bytes": self.spec.config.broker_max_frame_bytes,
        }
        if self.adaptive_context is not None:
            worker_count = self.adaptive_context.request.worker_count
            broker_document.update(
                {
                    "queue_capacity_per_model": worker_count,
                    "connection_handler_count": worker_count,
                    "yolo_executor_count": min(
                        self.adaptive_context.options.yolo_executor_count,
                        worker_count,
                    ),
                    "grounded_sam_executor_count": 1,
                    "request_deadline_s": max(
                        self.spec.config.yolo_queue_timeout_s
                        + self.spec.config.yolo_inference_timeout_s,
                        self.spec.config.grounded_sam_queue_timeout_s
                        + self.spec.config.grounded_sam_inference_timeout_s,
                    )
                    + self.spec.config.heartbeat_timeout_s,
                }
            )
        _write_json(spec_path, broker_document)
        self.broker_generation = generation
        self.broker_runtime_root = runtime_root
        self.broker_socket_path = runtime_root / "perception.sock"
        self.broker_container_id_path = runtime_root / "container.cid"
        self.broker_spec_path = spec_path

    def _release_partial(self):
        outcomes = {"worker_servers": []}
        if getattr(self, "fixed_control_server", None) is not None:
            try:
                self.fixed_control_server.close()
                outcomes["fixed_control_server"] = {"succeeded": True}
            except Exception as error:
                outcomes["fixed_control_server"] = {
                    "succeeded": False, "error_type": type(error).__name__,
                }
        for server in getattr(self, "worker_servers", ()):
            try:
                server.close()
            except Exception as error:
                outcomes["worker_servers"].append({
                    "succeeded": False,
                    "error_type": type(error).__name__,
                    "error_message": str(error),
                })
            else:
                outcomes["worker_servers"].append({
                    "succeeded": True,
                    "error_type": None,
                    "error_message": None,
                })
        journal = getattr(self, "journal", None)
        if journal is not None:
            try:
                journal.close()
            except Exception as error:
                outcomes["journal"] = {
                    "succeeded": False,
                    "error_type": type(error).__name__,
                    "error_message": str(error),
                }
            else:
                outcomes["journal"] = {
                    "succeeded": True,
                    "error_type": None,
                    "error_message": None,
                }
        else:
            outcomes["journal"] = None
        allocator = getattr(self, "allocator", None)
        if allocator is not None:
            try:
                allocator.close()
            except Exception as error:
                outcomes["allocator"] = {
                    "succeeded": False,
                    "error_type": type(error).__name__,
                    "error_message": str(error),
                }
            else:
                outcomes["allocator"] = {
                    "succeeded": True,
                    "error_type": None,
                    "error_message": None,
                }
        else:
            outcomes["allocator"] = None
        return outcomes

    def _start_broker(self):
        self._check_fixed_web_stop()
        if self.broker_spec_path is None:
            return None
        try:
            current_provenance = self._provenance_revalidator(
                self.spec.provenance_inputs
            )
        except Exception as error:
            raise CliError("PROVENANCE_REVALIDATION_FAILED") from error
        if dict(current_provenance) != dict(self.spec.provenance):
            raise CliError("PROVENANCE_DRIFT")
        if self._broker_command_builder is not None:
            command = self._broker_command_builder(self)
        else:
            from so101_demo.cli.parallel_perception_broker import (
                container_run_argv,
                gpu_groups,
                image_record,
                qualified_package_root,
            )

            image_id = self.spec.provenance.get("image_id")
            if not isinstance(image_id, str):
                raise CliError("BROKER_IMAGE_ID_REQUIRED")
            package = qualified_package_root()
            try:
                current_image = image_record(self.spec.broker_image)
            except Exception as error:
                raise CliError("BROKER_IMAGE_READBACK_FAILED") from error
            if any(
                self.spec.provenance.get(name) != value
                for name, value in current_image.items()
            ):
                raise CliError("BROKER_IMAGE_TAG_DRIFT")
            command = container_run_argv(
                self.spec.request.evidence_root,
                runtime_root=self.broker_runtime_root,
                runtime_ipc_root=self.runtime_ipc_root,
                input_root=self.broker_input_root,
                image_id=image_id,
                yolo_weights=self.spec.yolo_weights.resolve(),
                grounded_root=self.spec.grounded_root.resolve(),
                gpu_groups=gpu_groups(),
                uid=os.getuid(),
                gid=os.getgid(),
                batch_id=self.spec.request.batch_id,
                broker_generation=self.broker_generation,
                # The baked package of the image is replaced by the running, qualified one; its detector is what the broker runs, and the run records its hash
                source_package=package,
            )
            if os.environ.get("SO101_QUALIFIED_FREEZE"):
                self._record_broker_source_pin(package)
        return self.supervisor.start("broker", command)

    def _record_broker_source_pin(self, package):
        """Write what the broker's code is: the install's package and its detector with their hashes (once per run)."""
        from so101_demo.cli.parallel_perception_broker import broker_source_record

        document = broker_source_record(package)
        path = self.spec.request.evidence_root / "broker-source-pin.json"
        payload = (json.dumps(document, sort_keys=True, indent=1) + "\n").encode()
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        except FileExistsError:
            if path.read_bytes() != payload:
                raise CliError("BROKER_SOURCE_PIN_RECORD_CHANGED") from None
            return
        try:
            os.write(descriptor, payload)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def _container_inspect(self, container_id):
        return self._container_runner(
            ["docker", "inspect", "--type", "container", container_id],
            check=False,
            capture_output=True,
            text=True,
            timeout=self.spec.config.heartbeat_timeout_s,
        )

    def _harden_broker_container_id(self):
        """Make Docker's daemon-created cidfile private before trusting it."""

        path = self.broker_container_id_path
        try:
            before = path.lstat()
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        except OSError as error:
            raise CliError("BROKER_CONTAINER_ID_MISSING") from error
        try:
            current = os.fstat(descriptor)
            if (
                not stat.S_ISREG(before.st_mode)
                or not stat.S_ISREG(current.st_mode)
                or before.st_uid != os.getuid()
                or current.st_uid != os.getuid()
                or (before.st_dev, before.st_ino) != (current.st_dev, current.st_ino)
            ):
                raise CliError("BROKER_CONTAINER_ID_INVALID")
            value = os.read(descriptor, 66).decode("ascii").strip()
            if re.fullmatch(r"[0-9a-f]{64}", value) is None:
                raise CliError("BROKER_CONTAINER_ID_INVALID")
            os.fchmod(descriptor, 0o600)
            os.fsync(descriptor)
        except (OSError, UnicodeError) as error:
            raise CliError("BROKER_CONTAINER_ID_INVALID") from error
        finally:
            os.close(descriptor)
        return True

    def _retire_broker_container(self, *, runtime_root=None, generation=None):
        """Stop only the exact Docker container created for this Broker generation."""

        if not self._uses_production_broker_container or self.broker_spec_path is None:
            return True
        runtime_root = self.broker_runtime_root if runtime_root is None else Path(runtime_root)
        generation = self.broker_generation if generation is None else generation
        container_id_path = runtime_root / "container.cid"
        try:
            identity = container_id_path.lstat()
            container_id = container_id_path.read_text(encoding="ascii").strip()
        except (OSError, UnicodeError) as error:
            raise CliError("BROKER_CONTAINER_ID_MISSING") from error
        if (
            not stat.S_ISREG(identity.st_mode)
            or identity.st_uid != os.getuid()
            or stat.S_IMODE(identity.st_mode) != 0o600
            or re.fullmatch(r"[0-9a-f]{64}", container_id) is None
        ):
            raise CliError("BROKER_CONTAINER_ID_INVALID")
        inspected = self._container_inspect(container_id)
        if inspected.returncode != 0:
            return True
        try:
            documents = json.loads(inspected.stdout)
        except (TypeError, json.JSONDecodeError) as error:
            raise CliError("BROKER_CONTAINER_INSPECT_INVALID") from error
        if type(documents) is not list or len(documents) != 1 or type(documents[0]) is not dict:
            raise CliError("BROKER_CONTAINER_INSPECT_INVALID")
        document = documents[0]
        labels = document.get("Config", {}).get("Labels", {})
        mounts = {
            (item.get("Source"), item.get("Destination"))
            for item in document.get("Mounts", ())
            if type(item) is dict
        }
        if (
            document.get("Id") != container_id
            or document.get("Image") != self.spec.provenance.get("image_id")
            or labels.get("com.so101.batch-id") != self.spec.request.batch_id
            or labels.get("com.so101.broker-generation") != str(generation)
            or (str(runtime_root), "/runtime") not in mounts
            or (str(self.broker_input_root), "/inputs") not in mounts
        ):
            raise CliError("BROKER_CONTAINER_IDENTITY")
        stopped = self._container_runner(
            [
                "docker", "stop", "--timeout",
                str(max(1, int(self.spec.config.heartbeat_timeout_s))),
                container_id,
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=self.spec.config.heartbeat_timeout_s + 2.0,
        )
        removal_deadline = self._clock() + self.spec.config.heartbeat_timeout_s
        after = self._container_inspect(container_id)
        while after.returncode == 0 and self._clock() < removal_deadline:
            remaining = removal_deadline - self._clock()
            self._sleep(min(0.05, remaining))
            after = self._container_inspect(container_id)
        if stopped.returncode != 0 and after.returncode == 0:
            raise CliError("BROKER_CONTAINER_STOP_FAILED")
        if after.returncode == 0:
            raise CliError("BROKER_CONTAINER_SURVIVED")
        return True

    def _wait_broker_ready(self, *, deadline_monotonic_s=None):
        self._check_fixed_web_stop()
        if self.broker_spec_path is None:
            return True
        deadline = (
            self._clock() + self.spec.config.broker_recovery_timeout_s
            if deadline_monotonic_s is None
            else deadline_monotonic_s
        )
        ready = self.broker_runtime_root / "ready.json"
        while self._clock() < deadline:
            self._check_fixed_web_stop()
            self.supervisor.assert_healthy()
            try:
                socket_info = self.broker_socket_path.lstat()
            except FileNotFoundError:
                socket_info = None
            try:
                ready_info = ready.lstat()
            except FileNotFoundError:
                ready_info = None
            if socket_info is not None:
                if not stat.S_ISSOCK(socket_info.st_mode):
                    raise CliError("BROKER_READY_ENDPOINT_NOT_SOCKET")
            if ready_info is not None and stat.S_ISLNK(ready_info.st_mode):
                raise CliError("BROKER_READY_RECEIPT_INVALID")
            if (
                socket_info is not None
                and ready_info is not None
                and stat.S_ISSOCK(socket_info.st_mode)
                and stat.S_ISREG(ready_info.st_mode)
                and socket_info.st_uid == os.getuid()
                and ready_info.st_uid == os.getuid()
                and stat.S_IMODE(socket_info.st_mode) == 0o600
                and stat.S_IMODE(ready_info.st_mode) == 0o600
            ):
                if self._uses_production_broker_container:
                    self._harden_broker_container_id()
                try:
                    document = json.loads(ready.read_text(encoding="utf-8"))
                except (OSError, UnicodeError, json.JSONDecodeError) as error:
                    raise CliError("BROKER_READY_RECEIPT_INVALID") from error
                expected = {
                    "batch_id": self.spec.request.batch_id,
                    "run_mode": self.spec.request.run_mode.value,
                    "coordinator_epoch": self.journal.coordinator_epoch,
                    "broker_generation": self.broker_generation,
                    "image_id": self.spec.provenance.get("image_id"),
                    "yolo_weights_sha256": self.spec.yolo_weights_sha256,
                    "grounded_manifest_sha256": self.spec.grounded_manifest_sha256,
                }
                _validate_broker_ready(document, expected)
                ready_bytes = json.dumps(
                    document, sort_keys=True, separators=(",", ":"), allow_nan=False
                ).encode("utf-8")
                ready_sha256 = hashlib.sha256(ready_bytes).hexdigest()
                client = self._broker_health_client_factory(
                    self.broker_socket_path,
                    deadline_s=self.spec.config.heartbeat_timeout_s,
                    max_frame_bytes=self.spec.config.broker_max_frame_bytes,
                )
                message = {
                    "schema_version": 1,
                    "kind": "broker_call",
                    "coordinator_epoch": self.journal.coordinator_epoch,
                    "worker_id": "broker",
                    "worker_generation": self.broker_generation,
                    "lease": None,
                    "request_id": f"broker-health-{self.broker_generation}",
                    "idempotency_key": f"broker-health-{self.broker_generation}",
                    "token": "0" * 64,
                    "payload": {"operation": "health", "ready_sha256": ready_sha256},
                }
                response = client.call(message)
                payload = response.get("payload")
                if (
                    type(payload) is not dict
                    or set(payload) != {"ready", "ready_sha256"}
                    or payload["ready"] != document
                    or payload["ready_sha256"] != ready_sha256
                ):
                    raise CliError("BROKER_READY_HEALTH_IDENTITY")
                try:
                    socket_after = self.broker_socket_path.lstat()
                except FileNotFoundError as error:
                    raise CliError("BROKER_READY_ENDPOINT_CHANGED") from error
                if (
                    (socket_after.st_dev, socket_after.st_ino)
                    != (socket_info.st_dev, socket_info.st_ino)
                    or not stat.S_ISSOCK(socket_after.st_mode)
                ):
                    raise CliError("BROKER_READY_ENDPOINT_CHANGED")
                return True
            self._sleep(0.01)
        raise CliError("BROKER_READY_TIMEOUT")

    def _recover_broker(self, expected, _exit_code):
        self._check_fixed_web_stop()
        snapshot = self.coordinator.mark_broker_health(False)
        deadline = snapshot.broker_recovery_deadline_monotonic_s
        if deadline is None:
            raise CliError("BROKER_RECOVERY_DEADLINE_MISSING")
        replacement = None
        previous_runtime_root = self.broker_runtime_root
        previous_generation = self.broker_generation
        try:
            if self.supervisor.retire_owned(expected) is not True:
                raise CliError("BROKER_RETIRE_FAILED")
            if self._retire_broker_container(
                runtime_root=previous_runtime_root,
                generation=previous_generation,
            ) is not True:
                raise CliError("BROKER_CONTAINER_RETIRE_FAILED")
            self._prepare_broker_generation(self.broker_generation + 1)
            replacement = self._start_broker()
            self._wait_broker_ready(deadline_monotonic_s=deadline)
            self.coordinator.mark_broker_health(True)
            return True
        except _FixedWebStopRequested:
            raise
        except Exception:
            if replacement is not None:
                try:
                    self.supervisor.retire_owned(replacement)
                except Exception:
                    pass
            while self._clock() < deadline:
                self._check_fixed_web_stop()
                self._sleep(min(0.01, max(0.0, deadline - self._clock())))
            self.coordinator.tick()
            return False

    def _broker_discovery_lease(self, message):
        """Authorize discovery from an active or exact just-terminal lease."""
        try:
            return self._active_lease(message)
        except CliError:
            pass
        snapshot = self.coordinator.snapshot()
        worker = snapshot.workers.get(message["worker_id"])
        lease = message.get("lease")
        if (
            worker is None
            or worker.generation != message["worker_generation"]
            or worker.state is not WorkerState.RECOVERING
            or worker.lease is not None
            or type(lease) is not dict
        ):
            raise CliError("BROKER_DISCOVERY_LEASE")
        terminal_identity = None
        for event in reversed(self.journal.replay().events):
            if event.type not in {
                "RESULT_COMMITTED", "VALIDATION_COMMITTED", "LEASE_EXPIRED",
            }:
                continue
            identity = event.payload.get("identity")
            if (
                type(identity) is dict
                and identity.get("worker_id") == message["worker_id"]
                and identity.get("worker_generation")
                == message["worker_generation"]
            ):
                terminal_identity = identity
                break
        if terminal_identity is None or any(
            terminal_identity.get(name) != value for name, value in lease.items()
        ):
            raise CliError("BROKER_DISCOVERY_LEASE")
        return True

    def _capture_broker_exit_evidence(self, process, code):
        """Persist bounded Docker evidence before cleanup can erase it."""

        try:
            identity = self.broker_container_id_path.lstat()
            container_id = self.broker_container_id_path.read_text(
                encoding="ascii"
            ).strip()
        except (OSError, UnicodeError) as error:
            raise CliError("BROKER_CONTAINER_ID_MISSING") from error
        if (
            not stat.S_ISREG(identity.st_mode)
            or identity.st_uid != os.getuid()
            or stat.S_IMODE(identity.st_mode) != 0o600
            or re.fullmatch(r"[0-9a-f]{64}", container_id) is None
        ):
            raise CliError("BROKER_CONTAINER_ID_INVALID")

        def run(command):
            try:
                result = self._container_runner(
                    command,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=5.0,
                )
            except Exception as error:
                return {
                    "returncode": None,
                    "stdout": "",
                    "stderr": f"{type(error).__name__}: {error}"[:65536],
                }
            return {
                "returncode": result.returncode,
                "stdout": (result.stdout or "")[-65536:],
                "stderr": (result.stderr or "")[-65536:],
            }

        inspected = run(
            ["docker", "inspect", "--type", "container", container_id]
        )
        state = None
        if inspected["returncode"] == 0:
            try:
                documents = json.loads(inspected["stdout"])
                if (
                    type(documents) is list
                    and len(documents) == 1
                    and type(documents[0]) is dict
                    and documents[0].get("Id") == container_id
                    and type(documents[0].get("State")) is dict
                ):
                    state = documents[0]["State"]
            except (TypeError, json.JSONDecodeError):
                pass
        logs = run(["docker", "logs", "--tail", "200", container_id])
        events = run([
            "docker", "events", "--since", "10m", "--until", "0s",
            "--filter", f"container={container_id}", "--format", "{{json .}}",
        ])
        _write_json(
            self.broker_runtime_root / "broker-exit.json",
            {
                "schema_version": 1,
                "kind": "so101_broker_exit",
                "recorded_unix_ns": time.time_ns(),
                "process": {
                    "role": getattr(process, "role", "unknown"),
                    "pid": getattr(process, "pid", None),
                    "pgid": getattr(process, "pgid", None),
                    "start_time": getattr(process, "start_time", None),
                    "exit_code": code,
                },
                "container": {
                    "id": container_id,
                    "state": state,
                    "inspect": inspected,
                },
                "logs": logs,
                "events": events,
            },
        )
        return True
