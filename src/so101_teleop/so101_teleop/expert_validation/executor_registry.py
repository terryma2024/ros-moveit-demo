"""Explicit V1 executor capability registry."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from pydantic import BaseModel, ConfigDict


class UnknownOperation(LookupError):
    pass


class MoveItValidationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    manifest_id: str
    execution_mode: str = "SEQUENTIAL"


@dataclass(frozen=True, slots=True)
class ModeAvailability:
    available: bool
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class ExecutorCapability:
    executor_id: str
    operation_id: str
    request_model: type[BaseModel]
    evidence_schema_id: str
    execution_modes: tuple[str, ...]
    batch_kinds: tuple[str, ...]
    mode_availability: Mapping[str, ModeAvailability]
    success_contract_id: str
    default_execution_mode: str
    performance_qualified_tiers: tuple[int, ...] = ()
    contract_supported_live_unqualified_tiers: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class QualificationProbes:
    fixed_upstream: bool
    parallel_config: bool
    broker_image: bool
    resource_probe: bool
    two_worker_live_acceptance: str | None
    adaptive_runner: bool
    adaptive_pool: bool
    adaptive_wrapper: bool
    adaptive_cleanup: bool
    adaptive_config: bool
    adaptive_fault_injection: bool
    adaptive_twenty_point_acceptance: str | None
    adaptive_performance_evidence: tuple[int, ...]


class ExecutorRegistry:
    def __init__(self) -> None:
        self._capabilities: dict[tuple[str, str], ExecutorCapability] = {}

    def register(self, capability: ExecutorCapability) -> None:
        key = (capability.executor_id, capability.operation_id)
        if key in self._capabilities:
            raise ValueError("EXECUTOR_CAPABILITY_ALREADY_REGISTERED")
        self._capabilities[key] = capability

    def require(self, executor_id: str, operation_id: str) -> ExecutorCapability:
        try:
            return self._capabilities[(executor_id, operation_id)]
        except KeyError as error:
            raise UnknownOperation(f"UNKNOWN_OPERATION: {executor_id}/{operation_id}") from error

    @classmethod
    def v1(cls, probes: QualificationProbes) -> "ExecutorRegistry":
        # Availability is a statement about the *deployed* composition, not about a retired
        # per-N budget: what a mode needs is the executor, the shared queue, the broker and
        # the adaptive runner files actually being installed. The removed acceptance
        # aggregates and performance tiers were budget qualifications; requiring them made a
        # correctly deployed service advertise only SEQUENTIAL while fixed counts 1..8 were
        # selectable, which is exactly the mismatch this correction reports.
        fixed = probes.fixed_upstream and probes.parallel_config
        parallel = all(
            (
                fixed,
                probes.broker_image,
                probes.resource_probe,
            )
        )
        adaptive = all(
            (
                probes.adaptive_runner,
                probes.adaptive_pool,
                probes.adaptive_wrapper,
                probes.adaptive_cleanup,
                probes.adaptive_config,
            )
        )
        modes = MappingProxyType(
            {
                "SEQUENTIAL": ModeAvailability(
                    fixed, None if fixed else "FIXED_NOT_QUALIFIED"
                ),
                "PARALLEL": ModeAvailability(
                    parallel, None if parallel else "PARALLEL_COMPOSITION_UNAVAILABLE"
                ),
                "ADAPTIVE": ModeAvailability(
                    adaptive, None if adaptive else "ADAPTIVE_COMPOSITION_UNAVAILABLE"
                ),
            }
        )
        capability = ExecutorCapability(
            executor_id="moveit_expert",
            operation_id="validate_pick_place",
            request_model=MoveItValidationRequest,
            evidence_schema_id="so101.moveit-expert.evidence.v1",
            execution_modes=("SEQUENTIAL", "PARALLEL", "ADAPTIVE"),
            batch_kinds=("FIRST_PASS", "FULL_RESTART_RETRY"),
            mode_availability=modes,
            success_contract_id="so101.moveit-expert.success.v1",
            default_execution_mode="SEQUENTIAL",
            performance_qualified_tiers=tuple(
                level
                for level in (1, 2, 4, 6, 8, 10)
                if level in probes.adaptive_performance_evidence
            ),
            contract_supported_live_unqualified_tiers=(16,),
        )
        registry = cls()
        registry.register(capability)
        return registry
