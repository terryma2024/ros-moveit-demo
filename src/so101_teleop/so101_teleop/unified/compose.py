"""Production composition root for the unified web service.

Composition connects only approved runtimes. There is no auto-discovery: when the ROS
python, install prefix, evidence root or upstream packages are missing, the affected domain
is reported unavailable with a reason instead of the service guessing another runtime.
"""

from __future__ import annotations

import time
import os
from dataclasses import replace
from pathlib import Path
from typing import Mapping

from .admission import AdmissionGateway, AdmissionHook, UnifiedWorkloadService
from .arbiter import GlobalMutationArbiter
from .bridge import BridgeLaunch, BridgeClient, BridgeProcessOwner, ActChildRegistry, process_start_marker
from .contracts import Domain
from .goals import GoalRegistry
from .gpu_workload import ActGpuWorkloadArbiter
from .instances import InstanceRegistry, LeaseBindingCoordinator
from .intent_store import IntentStore
from .ports import UnknownBudgetSource, UnifiedServices
from .safety import SafetyLane, SafetyLimits
from .teleop_service import BackendView, ProductionTeleopService

SOCKET_DIR_ENV = "SO101_UNIFIED_SOCKET_DIR"
EVIDENCE_ROOT_ENV = "SO101_UNIFIED_EVIDENCE_ROOT"
RUNTIME_ID_ENV = "SO101_UNIFIED_RUNTIME_ID"
ROS_PYTHON_ENV = "SO101_UNIFIED_ROS_PYTHON"
INSTALL_PREFIX_ENV = "SO101_UNIFIED_INSTALL_PREFIX"
DELIVERY_ENV = "SO101_UNIFIED_CANCEL_DELIVERY_S"
STOP_ENV = "SO101_UNIFIED_CANCEL_STOP_S"
PENDING_ENV = "SO101_UNIFIED_CANCEL_MAX_PENDING"
ACT_GPU_SELECTOR_ENV = "SO101_ACT_GPU_SELECTOR"
ACT_BINDING_ENV = "SO101_ACT_RESOURCE_BINDING_ID"


class CompositionBlocked(RuntimeError):
    """Composition refused; the affected domain must report unavailable."""


def safety_limits_from_environment(environment: Mapping[str, str]) -> SafetyLimits:
    return SafetyLimits(
        delivery_s=float(environment.get(DELIVERY_ENV, "0.5")),
        stop_s=float(environment.get(STOP_ENV, "2.0")),
        max_pending=int(environment.get(PENDING_ENV, "4")),
    )


def _build_validation(evidence_root: Path, environment: Mapping[str, str], execution_port):
    try:
        from so101_teleop.expert_validation.production import create_production_service
    except Exception as error:  # noqa: BLE001 - a missing upstream becomes a domain reason
        raise CompositionBlocked(f"VALIDATION_DEPENDENCY_MISSING: {type(error).__name__}") from error
    return create_production_service(
        evidence_root, environment=dict(environment), execution_port=execution_port
    )


def resolve_visible_physical_uuids(devices, environment: Mapping[str, str]) -> tuple[str, ...]:
    """Resolve CUDA visibility order against the actual NVML physical inventory."""
    from so101_demo.parallel_batch.start_guard import ProbeError, _visible_indices

    devices = tuple(devices)
    indices = [device.index for device in devices]
    uuids = [device.uuid for device in devices]
    if (not devices or len(indices) != len(set(indices)) or len(uuids) != len(set(uuids))
            or any(type(index) is not int or index < 0 for index in indices)
            or any(not isinstance(uuid, str) or not uuid.startswith("GPU-") for uuid in uuids)):
        raise ValueError("GPU_INVENTORY_INVALID")
    try:
        visible = _visible_indices(environment, devices)
    except ProbeError as error:
        raise ValueError(str(error)) from error
    by_index = {device.index: device.uuid for device in devices}
    ordered = tuple(by_index[index] for index in (
        sorted(by_index) if visible is None else visible
    ) if index in by_index)
    if not ordered or (visible is not None and len(ordered) != len(visible)):
        raise ValueError("GPU_MAPPING_AMBIGUOUS")
    return ordered


def _physical_gpu_inventory(environment: Mapping[str, str]) -> tuple[str, ...]:
    from so101_demo.parallel_batch.start_guard import CtypesNvmlPort

    return resolve_visible_physical_uuids(CtypesNvmlPort().devices(), environment)


def _stable_host_id() -> str:
    try:
        machine_id = Path("/etc/machine-id").read_text(encoding="ascii").strip()
    except (OSError, UnicodeError) as error:
        raise CompositionBlocked("ACT_HOST_ID_UNAVAILABLE") from error
    if len(machine_id) != 32 or any(char not in "0123456789abcdef" for char in machine_id):
        raise CompositionBlocked("ACT_HOST_ID_UNAVAILABLE")
    return "machine-" + machine_id


def _owner_identity() -> tuple[int, int]:
    pid = os.getpid()
    return pid, process_start_marker(pid)


def compose_domain_services(
    *,
    environment: Mapping[str, str],
    evidence_root: Path,
    worker=None,
    bridge_owner: BridgeProcessOwner | None = None,
    budget_source=None,
    validation_execution_port=None,
    act_inventory=None,
    act_host_id=None,
    act_owner_identity=None,
) -> UnifiedServices:
    """Build the domain services on top of an already-owned child and store."""
    environment = dict(environment)
    evidence_root = Path(evidence_root)
    state_root = evidence_root / "unified"
    store = IntentStore.open(state_root)
    clock = time.monotonic_ns
    arbiter = GlobalMutationArbiter(store, clock_ns=clock)
    runtime_id = environment.get(RUNTIME_ID_ENV, "unified-R0")
    registry = InstanceRegistry(
        arbiter,
        service_epoch=environment.get("SO101_UNIFIED_SERVICE_EPOCH", "unified"),
        origin=environment.get("SO101_UNIFIED_ORIGIN", "http://127.0.0.1:8000"),
        clock_ns=clock,
    )
    goals = GoalRegistry()
    safety = SafetyLane(
        goals,
        arbiter,
        limits=safety_limits_from_environment(environment),
        authorize=_authorize_from_registry(registry),
        authorize_pending=None,
        service_epoch=registry.service_epoch,
    )
    gateway = AdmissionGateway(arbiter, registry)
    teleop = None
    tasks = None
    if worker is not None:
        from .parents import ParentSequencer

        sequencer = ParentSequencer(worker, arbiter, authority_guard=_guard_from_registry(registry))
        teleop = ProductionTeleopService(
            worker,
            admission=gateway,
            parents=sequencer,
            safety=safety,
            arbiter=arbiter,
            backend_view=BackendView(
                backend=environment.get("SO101_UNIFIED_BACKEND", "unconfigured"),
                owner_package=environment.get("SO101_UNIFIED_OWNER_PACKAGE", ""),
                owner_executable=environment.get("SO101_UNIFIED_OWNER_EXECUTABLE", ""),
                capabilities={},
            ),
            runtime_id=runtime_id,
            service_epoch=registry.service_epoch,
        )
    validation = None
    validation_error = None
    try:
        validation = _build_validation(evidence_root, environment, validation_execution_port)
    except Exception as error:  # noqa: BLE001 - a blocked domain reports a reason, not a crash
        validation_error = f"{type(error).__name__}: {error}"
    act_workload = None
    act_error = None
    if ACT_GPU_SELECTOR_ENV in environment or ACT_BINDING_ENV in environment:
        try:
            selector = environment[ACT_GPU_SELECTOR_ENV]
            binding = environment[ACT_BINDING_ENV]
            if (not selector or selector != selector.strip()
                    or not binding or binding != binding.strip()):
                raise CompositionBlocked("ACT_CONFIG_INVALID")
            visible = tuple((act_inventory or (lambda: _physical_gpu_inventory(environment)))())
            # Validate inventory before exposing admission, even if no campaign starts.
            from .gpu_workload import resolve_physical_gpu

            resolve_physical_gpu(selector, visible)
            host_id = (act_host_id or _stable_host_id)()
            owner_pid, owner_started_ticks = (act_owner_identity or _owner_identity)()
            if (not isinstance(host_id, str) or not host_id.strip()
                    or type(owner_pid) is not int or owner_pid <= 0
                    or type(owner_started_ticks) is not int or owner_started_ticks <= 0):
                raise CompositionBlocked("ACT_OWNER_IDENTITY_INVALID")
            act_workload = UnifiedWorkloadService(
                arbiter=arbiter, gpu_arbiter=ActGpuWorkloadArbiter(store, clock_ns=clock),
                child_registry=ActChildRegistry(), service_epoch=registry.service_epoch,
                runtime_id=runtime_id, stable_host_id=host_id, gpu_selector=selector,
                visible_physical_uuids=visible, resource_binding_id=binding,
                owner_pid=owner_pid, owner_started_ticks=owner_started_ticks,
                clock_ns=clock,
            )
        except Exception as error:  # noqa: BLE001 - ACT remains unavailable without physical proof
            act_error = f"{type(error).__name__}: {error}"
    services = UnifiedServices(
        teleop=teleop,
        tasks=tasks,
        validation=validation,
        arbiter=arbiter,
        instances=registry,
        safety=safety,
        bridge=bridge_owner,
        budget_source=budget_source or UnknownBudgetSource(),
        act_workload=act_workload,
        act_error=act_error,
    )
    services.store = store  # type: ignore[attr-defined]
    services.validation_error = validation_error  # type: ignore[attr-defined]
    return services


def _authorize_from_registry(registry: InstanceRegistry):
    def authorize(authority, key) -> None:
        if authority.kind == "browser":
            if authority.instance is None:
                raise ValueError("INSTANCE_AUTHORITY_REQUIRED")
            registry.require_bound(authority.instance)
        elif authority.service_epoch != registry.service_epoch:
            raise ValueError("STALE_SERVICE_EPOCH")

    return authorize


def _guard_from_registry(registry: InstanceRegistry):
    async def guard(authority) -> None:
        registry.require_bound(authority)

    return guard


def compose_services(environment: Mapping[str, str] | None = None) -> UnifiedServices:
    """The production entry point: own the child first, then compose the domains."""
    import os

    environment = dict(os.environ if environment is None else environment)
    evidence_root = environment.get(EVIDENCE_ROOT_ENV)
    if not evidence_root:
        raise SystemExit(f"{EVIDENCE_ROOT_ENV} must name the registered evidence root")
    socket_root = environment.get(SOCKET_DIR_ENV)
    ros_python = environment.get(ROS_PYTHON_ENV)
    install_prefix = environment.get(INSTALL_PREFIX_ENV)
    bridge_owner = None
    worker = None
    if socket_root and ros_python and install_prefix:
        launch = BridgeLaunch(
            ros_python=Path(ros_python),
            install_prefix=Path(install_prefix),
            runtime_id=environment.get(RUNTIME_ID_ENV, "unified-R0"),
            environment=environment,
            socket_root=Path(socket_root),
        )
        arbiter_stub = None
        del arbiter_stub
        bridge_owner = _DeferredBridgeOwner(launch)
    services = compose_domain_services(
        environment=environment,
        evidence_root=Path(evidence_root),
        worker=worker,
        bridge_owner=bridge_owner,
    )
    if bridge_owner is not None:
        bridge_owner.bind(services.arbiter, services.safety)
        bridge_owner.bind_client_factory(
            lambda owner: BridgeClient(
                normal_socket=bridge_owner.socket_paths()[0],
                safety_socket=bridge_owner.socket_paths()[1],
                service_epoch=services.instances.service_epoch,
                runtime_id=launch.runtime_id,
                service_token=bridge_owner.service_token,
                owner=owner,
            )
        )
    return services


class _DeferredBridgeOwner:
    """Wraps BridgeProcessOwner so composition can build the arbiter and safety lane first."""

    def __init__(self, launch: BridgeLaunch) -> None:
        self.launch = launch
        self.service_token = ""
        self._owner: BridgeProcessOwner | None = None
        self._client_factory = None

    def bind(self, arbiter, safety) -> None:
        import os
        import secrets

        self.service_token = secrets.token_urlsafe(24)
        environment = dict(self.launch.environment)
        environment.update({
            "SO101_CHILD_SERVICE_EPOCH": environment.get("SO101_UNIFIED_SERVICE_EPOCH", "unified"),
            "SO101_CHILD_SERVICE_TOKEN": self.service_token,
            "SO101_CHILD_WEB_PID": str(os.getpid()),
        })
        self.launch = replace(self.launch, environment=environment)
        self._owner = BridgeProcessOwner(self.launch, arbiter, safety)

    def bind_client_factory(self, factory) -> None:
        self._client_factory = factory

    async def start(self):
        if self._owner is None:
            raise CompositionBlocked("BRIDGE_NOT_BOUND")
        return await self._owner.start()

    async def stop_owned(self) -> None:
        if self._owner is not None:
            await self._owner.stop_owned()

    def ready(self) -> bool:
        return bool(self._owner and self._owner.ready())

    def socket_paths(self) -> tuple[Path, Path]:
        root = Path(self.launch.socket_root)
        from .child_runtime import NORMAL_SOCKET_NAME, SAFETY_SOCKET_NAME

        return root / NORMAL_SOCKET_NAME, root / SAFETY_SOCKET_NAME
