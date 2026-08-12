"""Sole backend, policy variant, adapter, and qualification-bundle composition point."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ..core.policy_registry import LoadedPolicy, load_policy_variant
from ..ports.capabilities import BackendCapabilities
from ..ports.lifecycle import LifecyclePort
from ..ports.phase_evidence import PhaseEvidencePort
from ..ports.planning_scene import PlanningScenePort
from ..ports.robot_control import RobotControlPort
from ..ports.world import WorldPort
from .provenance import QualificationBundle, build_bundle_manifest


class RuntimeCompositionError(ValueError):
    """Backend selection or adapter wiring is incomplete or unsupported."""


@dataclass(frozen=True, slots=True)
class CompositionRequest:
    backend: str
    policy_id: str
    policy_version: str
    share_dir: Path
    source_commit: str
    installed_prefix: Path


@dataclass(frozen=True, slots=True)
class BackendAdapters:
    robot_control: RobotControlPort
    planning_scene: PlanningScenePort
    world: WorldPort
    lifecycle: LifecyclePort
    phase_evidence: PhaseEvidencePort | None = None


@dataclass(frozen=True, slots=True)
class BackendComposition:
    backend: str
    capabilities: BackendCapabilities
    robot_control: RobotControlPort
    planning_scene: PlanningScenePort
    world: WorldPort
    lifecycle: LifecyclePort
    phase_evidence: PhaseEvidencePort | None
    policy: LoadedPolicy
    bundle: QualificationBundle


_CAPABILITIES = {
    "mujoco": BackendCapabilities(True, True, True, True, True, True, True),
    "gazebo": BackendCapabilities(False, True, True, False, False, True, False),
    "real_stub": BackendCapabilities(False, False, False, False, False, False, False),
}


def backend_capabilities(backend: str) -> BackendCapabilities:
    """Return the immutable declared capability set for one explicit backend."""

    try:
        return _CAPABILITIES[backend]
    except KeyError as error:
        raise RuntimeCompositionError(f"unsupported backend: {backend}") from error


def compose_backend(
    request: CompositionRequest,
    adapter_provider: Callable[[str], BackendAdapters] | None = None,
) -> BackendComposition:
    """Compose exactly one explicit backend without policy or adapter fallback."""

    capabilities = backend_capabilities(request.backend)
    if adapter_provider is None:
        raise RuntimeCompositionError("backend adapter context is required")
    policy = load_policy_variant(
        request.policy_id,
        request.policy_version,
        request.backend,
        request.share_dir,
    )
    adapters = adapter_provider(request.backend)
    if capabilities.lossless_physics_step_trace and adapters.phase_evidence is None:
        raise RuntimeCompositionError("lossless phase-evidence adapter is required")
    bundle = build_bundle_manifest(
        {
            "backend": request.backend,
            "installed_prefix": str(request.installed_prefix),
            "policy": policy.path,
            "policy_manifest": policy.path.parent / "manifest.yaml",
            "source_commit": request.source_commit,
            "runtime_composition": "fusion-v1",
        }
    )
    return BackendComposition(
        request.backend,
        capabilities,
        adapters.robot_control,
        adapters.planning_scene,
        adapters.world,
        adapters.lifecycle,
        adapters.phase_evidence,
        policy,
        bundle,
    )


def resume_backend(backend: str, config: object) -> bool:
    """Route lifecycle behavior at the runtime boundary, never in application code."""

    if backend == "mujoco":
        from ..backends.mujoco.lifecycle import resume_physics

        return resume_physics(config)
    raise RuntimeCompositionError(f"backend does not support resume: {backend}")
