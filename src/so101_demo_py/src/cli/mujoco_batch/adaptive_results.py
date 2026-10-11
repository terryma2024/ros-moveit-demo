"""Capture and release of the adaptive pool results of the batch composition."""

from __future__ import annotations

import json
import os
import shutil
import stat

from so101_demo.cli.mujoco_batch.common import CliError
from so101_demo.parallel_batch.adaptive_pool import (
    adaptive_socket_paths,
)
from so101_demo.parallel_batch.contracts import (
    AttemptStatus,
)
from so101_demo.parallel_batch.resources import (
    configured_runtime_ipc_root,
)


class AdaptiveResultCapture:
    def _capture_adaptive_results(self):
        if self.adaptive_context is None:
            return
        statuses = {}
        for resources in self.resource_manifest.workers:
            path = resources.worker_root / "worker-run-results.json"
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
            except (FileNotFoundError, OSError, ValueError, TypeError):
                continue
            for result in document.get("results", ()):
                point_id = result.get("point_id")
                status = result.get("terminal_status")
                if isinstance(point_id, str) and isinstance(status, str):
                    try:
                        statuses[point_id] = AttemptStatus(status)
                    except ValueError:
                        continue
        locations = {}
        for event in self.journal.replay().events:
            if event.type != "RESULT_COMMITTED":
                continue
            response = event.payload.get("response", {})
            identity = event.payload.get("identity", {})
            point_id = identity.get("point_id")
            location = response.get("location", identity.get("location"))
            if isinstance(point_id, str) and isinstance(location, str):
                locations[point_id] = location
        self.adaptive_attempt_statuses = statuses
        self.adaptive_result_locations = locations

    def _record_adaptive_infrastructure_failure(self, process, code):
        if self.adaptive_context is None:
            raise CliError("ADAPTIVE_POOL_CONTEXT")
        role = getattr(process, "role", "unknown")
        self.adaptive_diagnostics.append(f"FIRST_INFRA:{role}:{code}")
        if role == "broker":
            try:
                self._capture_broker_exit_evidence(process, code)
            except Exception as error:
                self.adaptive_diagnostics.append(
                    f"BROKER_EXIT_EVIDENCE:{type(error).__name__}:{error}"
                )
        self.coordinator.request_stop(reason="ADAPTIVE_INFRASTRUCTURE_FAILURE")

    def _release_adaptive_resources(self, cleanup_verified):
        if self.adaptive_context is None:
            return True
        if cleanup_verified is not True:
            return False
        try:
            for path in adaptive_socket_paths(
                self.spec.request.evidence_root,
                self.spec.request.worker_count,
                ipc_root=self.authority.ipc_root,
            ):
                try:
                    identity = path.lstat()
                except FileNotFoundError:
                    continue
                if not stat.S_ISSOCK(identity.st_mode) or identity.st_uid != os.getuid():
                    raise CliError("ADAPTIVE_SOCKET_CLEANUP_IDENTITY")
                path.unlink()
            return self.allocator.release_persistent_claims(
                cleanup_verified=True
            )
        except Exception as error:
            self.adaptive_diagnostics.append(
                f"CLEANUP:{type(error).__name__}:{error}"
            )
            return False

    def _release_runtime_ipc_root(self):
        if self.runtime_ipc_root is None:
            return True
        expected = configured_runtime_ipc_root(self.spec.request.batch_id)
        if expected != self.runtime_ipc_root or self.runtime_ipc_root.is_symlink():
            raise CliError("RUNTIME_IPC_CLEANUP_IDENTITY")
        try:
            info = self.runtime_ipc_root.lstat()
        except FileNotFoundError:
            return True
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
            raise CliError("RUNTIME_IPC_CLEANUP_IDENTITY")
        shutil.rmtree(self.runtime_ipc_root)
        return not self.runtime_ipc_root.exists()
