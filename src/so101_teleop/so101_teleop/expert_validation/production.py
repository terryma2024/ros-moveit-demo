"""Production composition root for the dedicated expert-validation service."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Mapping

from so101_teleop.expert_validation.artifacts import ValidationArtifactRegistry
from so101_teleop.expert_validation.executor_registry import ExecutorRegistry, QualificationProbes
from so101_teleop.expert_validation.lease import ValidationLeaseService
from so101_teleop.expert_validation.manifest_geometry import (
    current_manifest_source_hash,
)
from so101_teleop.expert_validation.preflight import (
    CampaignStartRequest,
    PreflightEngine,
)
from so101_teleop.expert_validation.process_owner import (
    ExecutionProcessOwner,
)
from so101_teleop.expert_validation.production_service.campaigns import CampaignStart
from so101_teleop.expert_validation.production_service.candidates import CandidateFirstPass
from so101_teleop.expert_validation.production_service.capabilities import ServiceCapabilities
from so101_teleop.expert_validation.production_service.guard import (
    _HostResourceProbe,
    _LazyStartGuard,
)
from so101_teleop.expert_validation.production_service.layout import (
    ProductionRuntimeLayout,
    _sha256,
)
from so101_teleop.expert_validation.production_service.projection import CampaignProjection
from so101_teleop.expert_validation.production_service.restore import CampaignRestore
from so101_teleop.expert_validation.production_service.retry import CampaignRetry
from so101_teleop.expert_validation.service import ExpertValidationService
from so101_teleop.expert_validation.store import SupervisorStore
from so101_teleop.expert_validation.supervisor import ExpertValidationSupervisor


class ProductionExpertValidationService(CampaignRestore, ServiceCapabilities, CampaignStart, CampaignProjection, CampaignRetry, CandidateFirstPass, ExpertValidationService):
    """API-complete facade over the durable supervisor composition."""

    #: How often the lease-expiry loop runs. A lease is short-lived by design, so this is the delay
    #: between its deadline passing and its state becoming EXPIRED.
    MAINTENANCE_INTERVAL_S = 0.25

    def __init__(self, *, layout: ProductionRuntimeLayout, registry, artifacts, **kwargs):
        super().__init__(**kwargs)
        self.layout = layout
        self._maintenance_task: asyncio.Task | None = None
        self.maintenance_failed = False
        self._current_source_config_sha256 = lambda: current_manifest_source_hash(self.layout)
        self.registry = registry
        self.artifacts = artifacts
        self._pending: dict[str, tuple[CampaignStartRequest, object, dict[str, object]]] = {}
        self._campaigns: dict[str, dict[str, object]] = {}
        self._campaign_requests: dict[str, CampaignStartRequest] = {}
        self._subscribers: set[asyncio.Queue] = set()
        self._restore_campaigns()

    # -- lease maintenance ---------------------------------------------------------------
    #
    # ``create_expert_validation_app`` runs this loop inside its own lifespan. The unified service
    # mounts the validation *routes* without that lifespan and asks the service for a
    # ``start_maintenance`` hook instead; no implementation provided one, so nothing ever expired a
    # lease there and an expired lease stayed ACTIVE in the store - which refuses every later acquire
    # with LEASE_ALREADY_HELD, for good, on a domain a session has walked away from.

    def health(self):
        return {
            "ok": True,
            "service": "expert-validation",
            "lease_maintenance_failed": self.maintenance_failed,
        }

    def subscribe(self):
        queue = asyncio.Queue()
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue):
        self._subscribers.discard(queue)


def default_admission_factory(environment: Mapping[str, str], *, config_path=None):
    """Compose the installed shared gate from the full verified P/Q/M/D authority.

    The identity is derived from the discovered v2 config, the installed and source
    inventory bytes and real hardware facts, then verified against the declared
    execution identity; an unreadable or mismatching authority raises instead of
    degrading to a permissive gate.
    """

    return _LazyStartGuard(environment, config_path)


def create_production_service(
    evidence_root: Path,
    *,
    environment: Mapping[str, str] | None = None,
    execution_port=None,
    admission_factory=None,
) -> ProductionExpertValidationService:
    """Compose all durable authorities used by the installed server entry point.

    ``execution_port`` is a typed test seam: only the repository's L2
    installed-test launcher passes it.  The production console entry point
    (``main.py``) never does, so installed production composition always
    targets the installed upstream executables.
    """


    environment = dict(os.environ if environment is None else environment)
    layout = ProductionRuntimeLayout.discover(environment)
    state_root = (Path(evidence_root) / "validation-service").resolve()
    # The owner tree is the service's own durable spawn record, and the root the demo-side
    # spawn boundaries inherit: it is created by the first record, never up front.
    owner_tree_root = (Path(evidence_root) / "owner-tree").resolve()
    store = SupervisorStore.open(state_root)
    try:
        owner = ExecutionProcessOwner(store=store, owner_tree_root=owner_tree_root)
        if admission_factory is None:
            start_guard = default_admission_factory(
                environment, config_path=layout.parallel_config_path)
        else:
            start_guard = admission_factory(environment)
        preflight = PreflightEngine(
            _HostResourceProbe(start_guard=start_guard),
            singleton_probe=lambda: not owner.has_active_execution(),
        )
        supervisor = ExpertValidationSupervisor(
            store=store, process_owner=owner, preflight_engine=preflight,
            execution_port=execution_port,
        )
        lease = ValidationLeaseService(store, supervisor)
        probes = QualificationProbes(
            fixed_upstream=layout.coordinator_executable.is_file(),
            parallel_config=layout.parallel_config_path.is_file(),
            broker_image=bool(layout.broker_image_id),
            resource_probe=True,
            two_worker_live_acceptance=(
                str(layout.parallel_acceptance) if layout.parallel_acceptance else None
            ),
            adaptive_runner=True,
            adaptive_pool=True,
            adaptive_wrapper=layout.adaptive_wrapper.is_file(),
            adaptive_cleanup=layout.cleanup_executable.is_file(),
            adaptive_config=layout.adaptive_config_path.is_file(),
            adaptive_fault_injection=layout.adaptive_fault_injection is not None,
            adaptive_twenty_point_acceptance=(
                str(layout.adaptive_acceptance) if layout.adaptive_acceptance else None
            ),
            adaptive_performance_evidence=layout.adaptive_performance_tiers,
        )
        registry = ExecutorRegistry.v1(probes)
        artifacts = ValidationArtifactRegistry()
        service = ProductionExpertValidationService(
            layout=layout,
            registry=registry,
            artifacts=artifacts,
            store=store,
            supervisor=supervisor,
            lease_service=lease,
            current_source_config_sha256=lambda: _sha256(layout.parallel_config_path),
        )
        supervisor.service = service
        return service
    except Exception:
        store.close()
        raise
