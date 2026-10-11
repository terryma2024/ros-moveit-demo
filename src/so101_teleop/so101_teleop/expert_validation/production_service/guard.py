"""The start guard admission, the host resource probe and the verified cleanup receipt."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping


class _GuardAdmission:
    """The guard wiring one execution document needs. Cacheable; it holds no verdict.

    ``(profile, config_sha256, accelerator, selector)`` is the composition key. The
    ``EpochStartGuard`` itself is built on first use, so reading the policy or the selector of a
    document performs no I/O beyond loading that document and starts no probe process.
    """

    def __init__(self, *, document, accelerator) -> None:
        self.document = document
        self.profile = None if document.profile is None else document.profile.profile
        self.config_sha256 = document.config_sha256
        self.accelerator_kind = document.accelerator
        self.selector = document.selector
        self.policy = document.config.start_guard
        self.accelerator = accelerator
        self._guard = None

    @property
    def composition_key(self) -> tuple:
        return (self.profile, self.config_sha256, self.accelerator_kind, self.selector)

    @property
    def guard(self):
        if self._guard is None:
            from so101_demo.parallel_batch.start_guard_probe import compose_default_start_guard

            self._guard = compose_default_start_guard(
                self.policy, accelerator=self.accelerator)
        return self._guard

    def begin_epoch(self, scope):
        """One fresh observation for this request/spawn epoch; never a stored verdict."""

        return self.guard.begin_epoch(scope)

    def require_before_spawn(self, scope):
        return self.guard.require_before_spawn(scope)


class _LazyStartGuard:
    """Compose the shared guard per execution document; the composition is cached, verdicts are not."""

    def __init__(self, environment: Mapping[str, str], config_path=None) -> None:
        self._environment = dict(environment)
        self._config_path = config_path
        self._admissions: dict[tuple, _GuardAdmission] = {}

    def admission(self, config_path=None) -> _GuardAdmission:
        """The cached composition for one document, keyed by its profile and real bytes."""

        from so101_teleop.expert_validation.preflight import describe_execution_document

        discovered = (config_path or self._config_path
                      or self._environment.get("SO101_VALIDATION_PARALLEL_CONFIG"))
        if not discovered:
            raise ValueError("START_GUARD_CONFIG_REQUIRED")
        # The document decides which guard this host can run. Loading everything as v3 both
        # rejected the schema-4 macOS document and built an NVML probe, which refuses every
        # preflight with GPU_TARGET_UNAVAILABLE on a host with no CUDA device.
        document = describe_execution_document(Path(discovered))
        key = self._composition_key(document)
        admission = self._admissions.get(key)
        if admission is None:
            admission = _GuardAdmission(
                document=document, accelerator=_accelerator_for_document(document))
            self._admissions[key] = admission
        return admission

    @staticmethod
    def _composition_key(document) -> tuple:
        profile = None if document.profile is None else document.profile.profile
        return (profile, document.config_sha256, document.accelerator, document.selector)

    @property
    def policy(self):
        return self.admission().policy

    @property
    def gpu_selector(self):
        return self.admission().selector

    def begin_epoch(self, scope, config_path=None):
        """A fresh probe for the document this request names; the composition may be reused."""

        return self.admission(config_path).begin_epoch(scope)

    def require_before_spawn(self, scope, config_path=None):
        return self.admission(config_path).require_before_spawn(scope)


def _accelerator_for_document(document):
    """The accelerator probe the document's combination asks for; ``None`` keeps the v3 path."""

    if document.accelerator == "mps":
        from so101_demo.parallel_batch.accelerator_probe import select_accelerator_probe

        selection = select_accelerator_probe("mps")
        if selection is None:  # pragma: no cover - the table above only asks for MPS
            raise RuntimeError("MPS_ACCELERATOR_PROBE_MISSING")
        return selection.probe.probe
    return None


#: The terminal reason of a batch whose owned coordinator or runner exited before any terminal event.
COORDINATOR_EXITED_NON_TERMINAL = "COORDINATOR_EXITED_NON_TERMINAL"


def _verified_cleanup_receipt_sha256(batch) -> str | None:
    """The frame hash of a batch's own verified ``CLEANUP_COMMITTED`` event, or ``None``.

    The frame hash is computed by the journal reader over the committed bytes of that event, so a
    receipt taken from it is a fact this service verified - never a claim the batch merely wrote
    somewhere else. ``None`` means the verified events carry no committed cleanup at all, and no
    receipt may be invented for them.
    """

    for event in reversed(batch.events):
        if event.type == "CLEANUP_COMMITTED":
            return event.frame_sha256
    return None


class _HostResourceProbe:
    """Fixed mode admits through the shared start guard; no budget authority is consulted."""

    def __init__(self, start_guard=None, gpu_selector=None) -> None:
        self._start_guard = start_guard
        self._gpu_selector = gpu_selector
        self._epochs = 0

    def _admission(self, request):
        """The composition for this request's document, when the guard is the lazy composer."""

        resolve = getattr(self._start_guard, "admission", None)
        if resolve is None:
            return None
        config_path = getattr(request, "parallel_config_path", None)
        return resolve(config_path)

    def probe(self, _request, config):
        observations: dict[str, object] = {"logical_cpu_count": os.cpu_count() or 0}
        reasons: list[str] = []
        workers = max(1, int(getattr(config, "worker_count", 1)))
        observations["requested_worker_count"] = workers
        if self._start_guard is None:
            reasons.append("START_GUARD_UNAVAILABLE")
            return not reasons, tuple(reasons), observations
        try:
            admission = self._admission(_request)
        except Exception as error:
            observations["probe_error"] = type(error).__name__
            reasons.append("RESOURCE_PROBE_FAILED")
            return not reasons, tuple(reasons), observations
        selector = getattr(config, "gpu_device", None)
        if selector is not None:
            gpu_selector = f"{selector.selector_kind}:{selector.selector}"
        elif admission is not None:
            gpu_selector = self._gpu_selector or admission.selector
        else:
            gpu_selector = self._gpu_selector or getattr(
                self._start_guard, "gpu_selector", None)
        if not gpu_selector:
            reasons.append("CONFIG_VERSION_UNSUPPORTED_FOR_EXECUTION")
            return not reasons, tuple(reasons), observations
        try:
            from so101_demo.parallel_batch.start_guard import GuardScope

            # Every request is its own epoch: a previous verdict is never reused.
            self._epochs += 1
            scope = GuardScope(
                batch_id="web-preflight",
                epoch=self._epochs,
                owner_pid=os.getpid(),
                owner_starttime_ticks=1,
                gpu_selector=gpu_selector,
                worker_count=workers,
            )
            result = (admission.begin_epoch(scope) if admission is not None
                      else self._start_guard.begin_epoch(scope))
        except Exception as error:
            observations["probe_error"] = type(error).__name__
            reasons.append("RESOURCE_PROBE_FAILED")
            return not reasons, tuple(reasons), observations
        observations["start_guard_status"] = result.status
        # The label is derived from the checks that actually ran, so a client can tell a
        # unified-memory proxy apart from a device-level VRAM reading without guessing.
        admission_kind = (
            "unified-memory-proxy" if "mps_headroom" in result.checks
            else ("nvml-device" if "gpu" in result.checks else None)
        )
        observations["start_guard"] = {
            "status": result.status,
            "cleanup_state": result.cleanup_state,
            "gpu_uuid": None if result.snapshot is None else result.snapshot.gpu_uuid,
            "observed_monotonic_s": result.completed_monotonic_s,
            "admission_kind": admission_kind,
            "checks": {
                name: {"status": check.status, "reason": check.reason,
                       "observed": check.observed, "cutoff": check.cutoff,
                       "unit": check.unit}
                for name, check in sorted(result.checks.items())
            },
        }
        if result.snapshot is not None:
            observations.update(
                effective_cpu_cores=result.snapshot.effective_cpu_cores,
                ram_available_bytes=result.snapshot.ram_available_bytes,
                gpu_free_bytes=result.snapshot.gpu_free_bytes,
                gpu_uuid=result.snapshot.gpu_uuid,
            )
        if result.status == "FAIL":
            for name, check in sorted(result.checks.items()):
                if check.status == "FAIL":
                    reasons.append(check.reason)
        if result.cleanup_state != "CLEAR":
            reasons.append(result.cleanup_state)
        return not reasons, tuple(reasons), observations
