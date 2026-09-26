"""Own one admitted pick-place validation child and simulator through durable retirement.

This source-only composition does not claim FULL_RESTART. The production case
runner must supply bounded physical and graph probes and an owner-created proof
handoff before the pick-place validation campaign fence can be removed.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import os
from pathlib import Path
import re
import stat
import time

from .act_artifacts import ActArtifactBinding
from .bridge import ActChildLaunch
from .child_runtime import NORMAL_SOCKET_NAME, READY_FILE_NAME, SAFETY_SOCKET_NAME
from .contracts import MutationError, OwnerKey
from .pick_place_startup_issuer import InstalledActStackReadinessProbe, PickPlaceStartupProofIssuer


def _retirement_receipt(root: Path, owner: OwnerKey, *, stack: bool,
                        session_id: str | None = None,
                        ros_domain_id: int | None = None) -> dict:
    path = root / "cleanup-receipt.json"
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        with os.fdopen(fd, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError("receipt is not regular")
            raw = stream.read((1 << 20) + 1)
        if len(raw) > (1 << 20):
            raise ValueError("receipt too large")
        value = json.loads(raw)
        expected = {
            "leader_pid": owner.pid, "pgid": owner.pgid,
            "started_ticks": owner.started_ticks,
            "argv_sha256": owner.argv_sha256, "group_clear": True,
        }
        if stack:
            expected.update(session_id=session_id, ros_domain_id=ros_domain_id)
        if (type(value) is not dict
                or any(value.get(key) != item or type(value.get(key)) is not type(item)
                       for key, item in expected.items())
                or stack and any(value.get(key) is not True for key in (
                    "physical_stop_confirmed", "graph_clear",
                ))
                or not stack and any((root / name).exists() or (root / name).is_symlink()
                                     for name in (
                                         NORMAL_SOCKET_NAME, SAFETY_SOCKET_NAME,
                                         READY_FILE_NAME,
                                     ))):
            raise ValueError("receipt identity or proof mismatch")
        return value
    except (OSError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise MutationError("TASK8_RETIREMENT_RECEIPT_INVALID") from error


class PickPlaceCaseOwner:
    """One admission, one child, one stack and a resumable retirement sequence."""

    def __init__(self, workload_service, child_owner, *, stack_factory,
                 final_clear_probe, artifact_binding=ActArtifactBinding.from_admission,
                 startup_proof_issuer=PickPlaceStartupProofIssuer,
                 require_startup_proof: bool = True,
                 final_clear_timeout_s: float = 5.0) -> None:
        if (not callable(stack_factory) or not inspect.iscoroutinefunction(final_clear_probe)
                or not callable(artifact_binding) or not callable(startup_proof_issuer)
                or type(require_startup_proof) is not bool
                or not 0 < final_clear_timeout_s <= 30):
            raise ValueError("TASK8_CASE_OWNER_CONFIG_INVALID")
        self.workload_service = workload_service
        self.child_owner = child_owner
        self.stack_factory = stack_factory
        self.final_clear_probe = final_clear_probe
        self.artifact_binding = artifact_binding
        self.startup_proof_issuer = startup_proof_issuer
        self.require_startup_proof = require_startup_proof
        self.final_clear_timeout_s = final_clear_timeout_s
        self.context = None
        self.worker = None
        self.stack = None
        self.child_launch = None
        self.stack_owner_key = None
        self.child_owner_key = None
        self._ready = False
        self._stop_confirmed = False
        self._stack_retired = False
        self._child_retired = False
        self._final_clear = False
        self._ever_started = False

    async def start(self, spec):
        if self._ever_started:
            raise MutationError("TASK8_CASE_OWNER_REUSED")
        if self.context is not None:
            raise MutationError("TASK8_CASE_ALREADY_ADMITTED")
        self._ever_started = True
        context = self.workload_service.start(spec, allow_existing=False)
        self.context = context
        try:
            if (getattr(spec, "kind", None) != "task8_full"
                    or context.workload_kind != "task8_full" or context.worker_count != 1
                    or spec.payload.get("evidence_root") != context.evidence_root):
                raise MutationError("TASK8_CASE_CONTEXT_INVALID")
            artifacts = self.artifact_binding(spec.payload, context)
            launches = tuple(ActChildLaunch(**item) for item in spec.payload["children"])
            if len(launches) != 1:
                raise MutationError("TASK8_CASE_CHILD_MAP_INVALID")
            child = launches[0]
            if (child.campaign_id != context.campaign_id
                    or child.execution_generation != context.execution_generation):
                raise MutationError("TASK8_CASE_CHILD_MAP_INVALID")
            self.child_launch = child
            ports = await self.child_owner.start(context, launches, artifacts=artifacts)
            if len(ports) != 1 or ports[0].launch != child:
                raise MutationError("TASK8_CASE_CHILD_MAP_INVALID")
            self.worker = ports[0]
            self.child_owner_key = ports[0].client.owner
            if not isinstance(self.child_owner_key, OwnerKey):
                raise MutationError("TASK8_CASE_CHILD_OWNER_INVALID")
            stack = self.stack_factory(context, child)
            self.stack = stack
            stack_launch = stack.launch
            stack_root = Path(stack_launch.evidence_root)
            campaign_root = Path(context.evidence_root)
            child_root = Path(child.socket_root)
            campaign_id = context.campaign_id
            if (not isinstance(campaign_id, str)
                    or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", campaign_id) is None):
                raise MutationError("TASK8_CASE_STACK_SCOPE_INVALID")
            expected_stack_root = campaign_root / "task8-live" / campaign_id / "stack"
            if (stack_launch.session_id != child.mujoco_session_id
                    or stack_launch.ros_domain_id != child.ros_domain_id
                    or stack_root != expected_stack_root
                    or any(path.is_symlink() for path in (
                        campaign_root, expected_stack_root.parent.parent,
                        expected_stack_root.parent, expected_stack_root,
                    ))
                    or not stack_root.is_dir()
                    or stack_root.resolve() == child_root.resolve()
                    or (stack_root / "cleanup-receipt.json").exists()
                    or (child_root / "cleanup-receipt.json").exists()):
                raise MutationError("TASK8_CASE_STACK_SCOPE_INVALID")
            owner_key = await stack.start()
            if not isinstance(owner_key, OwnerKey) or stack.owner != owner_key:
                raise MutationError("TASK8_CASE_STACK_OWNER_INVALID")
            self.stack_owner_key = owner_key
            if self.require_startup_proof:
                probe = getattr(stack, "ready_probe", None)
                if (not isinstance(probe, InstalledActStackReadinessProbe)
                        or probe.readiness_bytes is None):
                    raise MutationError("TASK8_STARTUP_PROOF_UNAVAILABLE")
                self.startup_proof_issuer(
                    context, child, owner_key, self.child_owner_key,
                ).issue(probe.readiness_bytes)
                self.worker.bind_startup_owner(owner_key)
            self._ready = True
            return context, self.worker
        except BaseException:
            # A spawned stack may still own controllers despite a failed start.
            # Keep the admission, child and stack fenced for explicit recovery.
            if self.stack is not None and self.stack.process is not None:
                raise
            await self.child_owner.stop_owned()
            self.workload_service.finish(context, cleanup_confirmed=True)
            self.context = None
            self.worker = self.stack = self.child_launch = None
            raise

    async def finish(self, *, attempt_id: str) -> None:
        if not self._ready or self.context is None:
            raise MutationError("TASK8_CASE_NOT_READY")
        if not isinstance(attempt_id, str) or not attempt_id:
            raise MutationError("TASK8_CASE_ATTEMPT_INVALID")
        if not self._stop_confirmed:
            response = await self.worker.cancel({
                "session_id": self.child_launch.mujoco_session_id,
                "attempt_id": attempt_id,
                "reason": "TASK8_CASE_RETIRE",
                "deadline_ns": time.monotonic_ns() + 5_000_000_000,
            })
            if not isinstance(response, dict) or response.get("stopped_confirmed") is not True:
                raise MutationError("TASK8_CASE_STOP_NOT_CONFIRMED")
            self._stop_confirmed = True
        if not self._stack_retired:
            await self.stack.stop()
            _retirement_receipt(Path(self.stack.launch.evidence_root),
                                self.stack_owner_key, stack=True,
                                session_id=self.child_launch.mujoco_session_id,
                                ros_domain_id=self.child_launch.ros_domain_id)
            self._stack_retired = True
        if not self._child_retired:
            await self.child_owner.stop_owned()
            _retirement_receipt(Path(self.child_launch.socket_root),
                                self.child_owner_key, stack=False)
            self._child_retired = True
        if not self._final_clear:
            proof = self.final_clear_probe(self.child_launch.ros_domain_id)
            try:
                clear = await asyncio.wait_for(proof, timeout=self.final_clear_timeout_s)
            except (asyncio.TimeoutError, OSError, ValueError) as error:
                raise MutationError("TASK8_FINAL_GRAPH_NOT_CLEARED") from error
            if clear is not True:
                raise MutationError("TASK8_FINAL_GRAPH_NOT_CLEARED")
            self._final_clear = True
        self.workload_service.finish(self.context, cleanup_confirmed=True)
        self.context = None
        self._ready = False


# Legacy Python API for version-one pick-place callers.
Task8CaseOwner = PickPlaceCaseOwner
