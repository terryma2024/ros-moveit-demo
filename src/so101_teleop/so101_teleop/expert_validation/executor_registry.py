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
        fixed = probes.fixed_upstream and probes.parallel_config
        parallel = all(
            (
                fixed,
                probes.broker_image,
                probes.resource_probe,
                probes.two_worker_live_acceptance is not None,
            )
        )
        adaptive = all(
            (
                probes.adaptive_runner,
                probes.adaptive_pool,
                probes.adaptive_wrapper,
                probes.adaptive_cleanup,
                probes.adaptive_config,
                probes.adaptive_fault_injection,
                probes.adaptive_twenty_point_acceptance is not None,
                {1, 2, 4, 6, 8}.issubset(probes.adaptive_performance_evidence),
            )
        )
        modes = MappingProxyType(
            {
                "SEQUENTIAL": ModeAvailability(
                    fixed, None if fixed else "FIXED_NOT_QUALIFIED"
                ),
                "PARALLEL": ModeAvailability(
                    parallel, None if parallel else "PARALLEL_NOT_QUALIFIED"
                ),
                "ADAPTIVE": ModeAvailability(
                    adaptive, None if adaptive else "ADAPTIVE_NOT_QUALIFIED"
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
