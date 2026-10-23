"""The macOS MPS single-worker runtime configurations and the schema-agnostic loader."""

from __future__ import annotations

from dataclasses import dataclass, fields
from pathlib import Path
from typing import ClassVar, Mapping

from so101_demo.parallel_batch.contracts.common import (
    ContractError,
    _require_finite,
    _require_id,
    _require_positive_int,
    _require_probability,
)
from so101_demo.parallel_batch.contracts.identity import _closed_mapping_fields, _load_closed_yaml
from so101_demo.parallel_batch.contracts.linux_cuda import (
    BatchKind,
    ClockRulesLinuxCuda,
    ParallelRuntimeConfigLinuxCuda,
    load_parallel_runtime_config_linux_cuda,
)
from so101_demo.parallel_batch.contracts.macos_two_worker import (
    ACCELERATOR_FIELDS,
    EXECUTION_MACOS_MPS_TWO_WORKER_FIELDS,
    MACOS_MPS_TWO_WORKER_CONFIG_FIELDS,
    START_GUARD_MACOS_MPS_TWO_WORKER_FIELDS,
    AcceleratorKind,
    AcceleratorSelectionMacosMpsTwoWorker,
    IpcTransport,
    ParallelRuntimeConfigMacosMpsTwoWorker,
    _require_fraction,
    _require_positive_bytes,
    _resolve_macos_mps_two_worker_transport,
    load_parallel_runtime_config_macos_mps_two_worker,
)
from so101_demo.parallel_batch.contracts.routes import (
    FROZEN_DARWIN_VALUES_MACOS_MPS_SINGLE_WORKER_FIRST_PASS,
    FROZEN_DARWIN_VALUES_MACOS_MPS_SINGLE_WORKER_RETRY,
    FROZEN_RUNTIME_VALUES_MACOS_MPS_SINGLE_WORKER_FIRST_PASS,
    FROZEN_RUNTIME_VALUES_MACOS_MPS_SINGLE_WORKER_RETRY,
    MACOS_MPS_SINGLE_WORKER_FIRST_PASS_PLATFORM_WORKER_COUNT,
    MACOS_MPS_SINGLE_WORKER_RETRY_PLATFORM_WORKER_COUNT,
    SINGLE_WORKER_PLATFORM_COMBINATIONS,
    ExecutionProfile,
)
from so101_demo.parallel_batch.frozen_models import (
    FROZEN_GROUNDED_SAM_MANIFEST_SHA256 as _FROZEN_GROUNDED_SAM_MANIFEST_SHA256,
)
from so101_demo.parallel_batch.frozen_models import (
    FROZEN_YOLO_WEIGHTS_SHA256 as _FROZEN_YOLO_WEIGHTS_SHA256,
)
from so101_demo.parallel_batch.start_guard import StartGuardPolicy


def load_runtime_config_any_schema(path: Path):
    """Load a runtime document, choosing the parser by its declared schema."""

    import yaml

    try:
        document = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except OSError as error:
        raise ContractError(f"CONFIG_READ_FAILED: {path}") from error
    except yaml.YAMLError as error:
        raise ContractError(f"CONFIG_YAML_INVALID: {path}") from error
    if not isinstance(document, dict):
        raise ContractError("CONFIG_MAPPING")
    version = document.get("schema_version")
    if version == 6:
        return load_parallel_runtime_config_macos_mps_single_worker_first_pass(Path(path))
    if version == 5:
        return load_parallel_runtime_config_macos_mps_single_worker_retry(Path(path))
    if version == 4:
        return load_parallel_runtime_config_macos_mps_two_worker(Path(path))
    if version == 3:
        return load_parallel_runtime_config_linux_cuda(Path(path))
    raise ContractError(f"SCHEMA_VERSION: {version!r}")


@dataclass(frozen=True, slots=True)
class ParallelRuntimeConfigMacosMpsSingleWorkerRetry:
    """The closed version-five document: single-worker ``FULL_RESTART_RETRY`` on Darwin/MPS."""

    schema_version: int
    backend: str
    max_worker_count: int
    ros_domain_ids: tuple[int, ...]
    heartbeat_interval_s: float
    heartbeat_timeout_s: float
    lease_duration_s: float
    lease_ack_timeout_s: float
    attempt_start_ack_timeout_s: float
    result_ack_timeout_s: float
    initializing_hard_timeout_s: float
    executing_hard_timeout_s: float
    finalizing_hard_timeout_s: float
    batch_hard_timeout_s: float
    worker_recovery_timeout_s: float
    broker_recovery_timeout_s: float
    broker_max_frame_bytes: int
    broker_queue_capacity_per_model: int
    broker_inflight_per_worker_per_model: int
    yolo_queue_timeout_s: float
    yolo_inference_timeout_s: float
    grounded_sam_queue_timeout_s: float
    grounded_sam_inference_timeout_s: float
    max_frame_age_s: float
    max_rgbd_skew_s: float
    max_tf_skew_s: float
    yolo_model_id: str
    yolo_imgsz: int
    allow_cpu_fallback: bool
    grounding_box_threshold: float
    grounding_text_threshold: float
    grounding_duplicate_iou: float
    grounding_max_candidates: int
    sam_mask_quality_threshold: float
    sam_min_mask_pixels: int
    sam_max_mask_area_ratio: float
    clock: ClockRulesLinuxCuda
    start_guard: "StartGuardPolicy"
    accelerator: AcceleratorSelectionMacosMpsTwoWorker
    requested_device: str
    worker_count: int
    ipc_transport: IpcTransport
    mujoco_gl: str
    mps_process_memory_fraction: float | None
    max_input_snapshot_bytes: int

    FROZEN_YOLO_WEIGHTS_SHA256: ClassVar[str] = _FROZEN_YOLO_WEIGHTS_SHA256
    FROZEN_GROUNDED_SAM_MANIFEST_SHA256: ClassVar[str] = (
        _FROZEN_GROUNDED_SAM_MANIFEST_SHA256
    )

    def __post_init__(self) -> None:
        _validate_single_worker_profile(
            self,
            schema_version=5,
            worker_count=MACOS_MPS_SINGLE_WORKER_RETRY_PLATFORM_WORKER_COUNT,
            frozen_runtime_values=FROZEN_RUNTIME_VALUES_MACOS_MPS_SINGLE_WORKER_RETRY,
            darwin_values=FROZEN_DARWIN_VALUES_MACOS_MPS_SINGLE_WORKER_RETRY,
        )

    @property
    def execution_profile(self) -> ExecutionProfile:
        return ExecutionProfile.MPS_SINGLE_WORKER_FULL_RESTART_RETRY

    @property
    def batch_kind(self) -> BatchKind:
        return BatchKind.FULL_RESTART_RETRY

    @property
    def mps_minimum_headroom_bytes(self) -> int | None:
        return self.start_guard.mps_minimum_headroom_bytes

    @property
    def yolo_weights_sha256(self) -> str:
        return self.FROZEN_YOLO_WEIGHTS_SHA256

    @property
    def grounded_sam_manifest_sha256(self) -> str:
        return self.FROZEN_GROUNDED_SAM_MANIFEST_SHA256

    def resolved_manifest(self) -> dict:
        return _single_worker_resolved_manifest(self)


@dataclass(frozen=True, slots=True)
class ParallelRuntimeConfigMacosMpsSingleWorkerFirstPass:
    """The closed version-six document: single-worker ``FIRST_PASS`` on Darwin/MPS."""

    schema_version: int
    backend: str
    max_worker_count: int
    ros_domain_ids: tuple[int, ...]
    heartbeat_interval_s: float
    heartbeat_timeout_s: float
    lease_duration_s: float
    lease_ack_timeout_s: float
    attempt_start_ack_timeout_s: float
    result_ack_timeout_s: float
    initializing_hard_timeout_s: float
    executing_hard_timeout_s: float
    finalizing_hard_timeout_s: float
    batch_hard_timeout_s: float
    worker_recovery_timeout_s: float
    broker_recovery_timeout_s: float
    broker_max_frame_bytes: int
    broker_queue_capacity_per_model: int
    broker_inflight_per_worker_per_model: int
    yolo_queue_timeout_s: float
    yolo_inference_timeout_s: float
    grounded_sam_queue_timeout_s: float
    grounded_sam_inference_timeout_s: float
    max_frame_age_s: float
    max_rgbd_skew_s: float
    max_tf_skew_s: float
    yolo_model_id: str
    yolo_imgsz: int
    allow_cpu_fallback: bool
    grounding_box_threshold: float
    grounding_text_threshold: float
    grounding_duplicate_iou: float
    grounding_max_candidates: int
    sam_mask_quality_threshold: float
    sam_min_mask_pixels: int
    sam_max_mask_area_ratio: float
    clock: ClockRulesLinuxCuda
    start_guard: "StartGuardPolicy"
    accelerator: AcceleratorSelectionMacosMpsTwoWorker
    requested_device: str
    worker_count: int
    ipc_transport: IpcTransport
    mujoco_gl: str
    mps_process_memory_fraction: float | None
    max_input_snapshot_bytes: int

    FROZEN_YOLO_WEIGHTS_SHA256: ClassVar[str] = _FROZEN_YOLO_WEIGHTS_SHA256
    FROZEN_GROUNDED_SAM_MANIFEST_SHA256: ClassVar[str] = (
        _FROZEN_GROUNDED_SAM_MANIFEST_SHA256
    )

    def __post_init__(self) -> None:
        _validate_single_worker_profile(
            self,
            schema_version=6,
            worker_count=MACOS_MPS_SINGLE_WORKER_FIRST_PASS_PLATFORM_WORKER_COUNT,
            frozen_runtime_values=FROZEN_RUNTIME_VALUES_MACOS_MPS_SINGLE_WORKER_FIRST_PASS,
            darwin_values=FROZEN_DARWIN_VALUES_MACOS_MPS_SINGLE_WORKER_FIRST_PASS,
        )

    @property
    def execution_profile(self) -> ExecutionProfile:
        return ExecutionProfile.MPS_SINGLE_WORKER_FIRST_PASS

    @property
    def batch_kind(self) -> BatchKind:
        return BatchKind.FIRST_PASS

    @property
    def mps_minimum_headroom_bytes(self) -> int | None:
        return self.start_guard.mps_minimum_headroom_bytes

    @property
    def yolo_weights_sha256(self) -> str:
        return self.FROZEN_YOLO_WEIGHTS_SHA256

    @property
    def grounded_sam_manifest_sha256(self) -> str:
        return self.FROZEN_GROUNDED_SAM_MANIFEST_SHA256

    def resolved_manifest(self) -> dict:
        return _single_worker_resolved_manifest(self)


def _validate_single_worker_profile(config: object, *, schema_version: int, worker_count: int,
                         frozen_runtime_values: Mapping[str, object],
                         darwin_values: Mapping[str, object]) -> None:
    """The closed validation the two single-worker profiles share, in the v4 order and vocabulary."""

    if type(config.schema_version) is not int or config.schema_version != schema_version:
        raise ContractError("SCHEMA_VERSION")
    if config.backend != "mujoco":
        raise ContractError("BACKEND")
    if not isinstance(config.accelerator, AcceleratorSelectionMacosMpsTwoWorker):
        raise ContractError("ACCELERATOR_SELECTION")
    try:
        transport = IpcTransport(config.ipc_transport)
    except ValueError as error:
        raise ContractError("IPC_TRANSPORT") from error
    object.__setattr__(config, "ipc_transport", transport)

    combination = (
        str(config.accelerator.kind), config.requested_device, str(transport), config.mujoco_gl,
    )
    if combination not in SINGLE_WORKER_PLATFORM_COMBINATIONS:
        # A CPU device, a CPU fallback or the Linux transport is a different platform claim.
        raise ContractError("PLATFORM_COMBINATION_UNSUPPORTED")

    if isinstance(config.worker_count, bool) or config.worker_count != worker_count:
        raise ContractError("PLATFORM_WORKER_COUNT_UNSUPPORTED")

    if not isinstance(config.allow_cpu_fallback, bool) or config.allow_cpu_fallback:
        raise ContractError("ALLOW_CPU_FALLBACK")

    for name in (
        "max_worker_count", "broker_max_frame_bytes", "broker_queue_capacity_per_model",
        "broker_inflight_per_worker_per_model", "yolo_imgsz", "grounding_max_candidates",
        "sam_min_mask_pixels", "max_input_snapshot_bytes",
    ):
        object.__setattr__(config, name, _require_positive_int(name, getattr(config, name)))
    if not isinstance(config.ros_domain_ids, (list, tuple)):
        raise ContractError("ROS_DOMAIN_IDS")
    domains = tuple(config.ros_domain_ids)
    for domain_id in domains:
        _require_positive_int("ros_domain_id", domain_id)
    object.__setattr__(config, "ros_domain_ids", domains)
    for name in (
        "heartbeat_interval_s", "heartbeat_timeout_s", "lease_duration_s",
        "lease_ack_timeout_s", "attempt_start_ack_timeout_s", "result_ack_timeout_s",
        "initializing_hard_timeout_s", "executing_hard_timeout_s",
        "finalizing_hard_timeout_s", "batch_hard_timeout_s", "worker_recovery_timeout_s",
        "broker_recovery_timeout_s", "yolo_queue_timeout_s", "yolo_inference_timeout_s",
        "grounded_sam_queue_timeout_s", "grounded_sam_inference_timeout_s",
    ):
        object.__setattr__(
            config, name, _require_finite(name, getattr(config, name), minimum=0.000001)
        )
    for name in ("max_frame_age_s", "max_rgbd_skew_s", "max_tf_skew_s"):
        object.__setattr__(config, name, _require_finite(name, getattr(config, name)))
    for name in (
        "grounding_box_threshold", "grounding_text_threshold",
        "grounding_duplicate_iou", "sam_mask_quality_threshold",
        "sam_max_mask_area_ratio",
    ):
        object.__setattr__(config, name, _require_probability(name, getattr(config, name)))
    object.__setattr__(config, "yolo_model_id", _require_id("yolo_model_id", config.yolo_model_id))
    if not isinstance(config.clock, ClockRulesLinuxCuda):
        raise ContractError("CLOCK_RULES")
    if not isinstance(config.start_guard, StartGuardPolicy):
        raise ContractError("START_GUARD_POLICY")

    # The Darwin-only half, unchanged from v4: the allocator cap is set before any MPS allocation
    # and the fixed unified-memory floor is a positive byte count.
    object.__setattr__(
        config, "mps_process_memory_fraction",
        _require_fraction("MPS_PROCESS_MEMORY_FRACTION", config.mps_process_memory_fraction),
    )
    headroom = config.start_guard.mps_minimum_headroom_bytes
    if headroom is None:
        raise ContractError("MPS_MINIMUM_HEADROOM_BYTES")
    _require_positive_bytes("MPS_MINIMUM_HEADROOM_BYTES", headroom)

    for name, expected in frozen_runtime_values.items():
        if getattr(config, name, None) != expected:
            raise ContractError(f"FROZEN_RUNTIME_VALUE: {name}")
    for name, expected in darwin_values.items():
        if name == "accelerator_kind":
            actual = str(config.accelerator.kind)
        elif name == "accelerator_selector":
            actual = config.accelerator.resolved_selector
        else:
            actual = getattr(config, name, None)
        if actual != expected:
            raise ContractError(f"FROZEN_PLATFORM_VALUE: {name}")
    if len(domains) != config.worker_count or len(set(domains)) != len(domains):
        raise ContractError("ROS_DOMAIN_IDS")


def _single_worker_resolved_manifest(config: object) -> dict:
    """The resolved platform values a single-worker manifest records; never ``auto`` and never a budget."""

    return {
        "schema_version": config.schema_version,
        "execution_profile": str(config.execution_profile),
        "batch_kind": str(config.batch_kind),
        "accelerator": str(config.accelerator.kind),
        "accelerator_selector": config.accelerator.resolved_selector,
        "requested_device": config.requested_device,
        "allow_cpu_fallback": config.allow_cpu_fallback,
        "ipc_transport": str(config.ipc_transport),
        "mujoco_gl": config.mujoco_gl,
        "worker_count": config.worker_count,
        "mps_process_memory_fraction": config.mps_process_memory_fraction,
        "mps_minimum_headroom_bytes": config.mps_minimum_headroom_bytes,
        "max_input_snapshot_bytes": config.max_input_snapshot_bytes,
        "yolo_model_id": config.yolo_model_id,
        "yolo_weights_sha256": config.yolo_weights_sha256,
        "grounded_sam_manifest_sha256": config.grounded_sam_manifest_sha256,
    }


def _parse_single_worker_document(document: object, *, schema_version: int, config_class):
    """Validate a single-worker document against the closed v4-shaped schema, at its own version."""

    top = _closed_mapping_fields("CONFIG", document, set(MACOS_MPS_TWO_WORKER_CONFIG_FIELDS))
    if type(top["schema_version"]) is not int or top["schema_version"] != schema_version:
        raise ContractError("SCHEMA_VERSION")
    accelerator_fields = _closed_mapping_fields(
        "ACCELERATOR", top["accelerator"], set(ACCELERATOR_FIELDS)
    )
    execution = _closed_mapping_fields("EXECUTION", top["execution"], set(EXECUTION_MACOS_MPS_TWO_WORKER_FIELDS))
    guard = _closed_mapping_fields(
        "START_GUARD", top["start_guard"], set(START_GUARD_MACOS_MPS_TWO_WORKER_FIELDS),
        {"mps_minimum_headroom_bytes"},
    )
    clock = _closed_mapping_fields(
        "CLOCK", execution.pop("clock"), {item.name for item in fields(ClockRulesLinuxCuda)}
    )
    try:
        accelerator = AcceleratorSelectionMacosMpsTwoWorker(
            kind=AcceleratorKind(accelerator_fields["kind"]),
            selector=accelerator_fields["selector"],
        )
    except (ValueError, KeyError) as error:
        raise ContractError(f"ACCELERATOR_INVALID: {error}") from error

    resolved = _resolve_macos_mps_two_worker_transport(top["ipc_transport"], accelerator)
    try:
        guard_policy = StartGuardPolicy(**guard)
    except ValueError as error:
        raise ContractError(f"START_GUARD_INVALID: {error}") from error
    return config_class(
        schema_version=schema_version,
        clock=ClockRulesLinuxCuda(**clock),
        start_guard=guard_policy,
        accelerator=accelerator,
        requested_device=top["requested_device"],
        allow_cpu_fallback=top["allow_cpu_fallback"],
        worker_count=top["worker_count"],
        ipc_transport=resolved.get("ipc_transport", top["ipc_transport"]),
        mujoco_gl=resolved.get("mujoco_gl", top["mujoco_gl"]),
        mps_process_memory_fraction=top["mps_process_memory_fraction"],
        max_input_snapshot_bytes=top["max_input_snapshot_bytes"],
        **execution,
    )


def parse_parallel_runtime_config_macos_mps_single_worker_retry(document: object) -> ParallelRuntimeConfigMacosMpsSingleWorkerRetry:
    """Validate a version-five document: single-worker ``FULL_RESTART_RETRY`` on Darwin/MPS only."""

    return _parse_single_worker_document(document, schema_version=5, config_class=ParallelRuntimeConfigMacosMpsSingleWorkerRetry)


def parse_parallel_runtime_config_macos_mps_single_worker_first_pass(document: object) -> ParallelRuntimeConfigMacosMpsSingleWorkerFirstPass:
    """Validate a version-six document: single-worker ``FIRST_PASS`` on Darwin/MPS only."""

    return _parse_single_worker_document(document, schema_version=6, config_class=ParallelRuntimeConfigMacosMpsSingleWorkerFirstPass)


def load_parallel_runtime_config_macos_mps_single_worker_retry(path: Path) -> ParallelRuntimeConfigMacosMpsSingleWorkerRetry:
    """Load the closed version-five YAML document; any drift or other platform is refused."""

    return parse_parallel_runtime_config_macos_mps_single_worker_retry(_load_closed_yaml(path))


def load_parallel_runtime_config_macos_mps_single_worker_first_pass(path: Path) -> ParallelRuntimeConfigMacosMpsSingleWorkerFirstPass:
    """Load the closed version-six YAML document; any drift or other platform is refused."""

    return parse_parallel_runtime_config_macos_mps_single_worker_first_pass(_load_closed_yaml(path))


def require_macos_mps_single_worker_retry_execution(request_version: int, config_version: int) -> None:
    """Refuse new execution for any contract version other than version five."""

    if type(request_version) is not int or type(config_version) is not int:
        raise ContractError("CONFIG_VERSION_UNSUPPORTED_FOR_EXECUTION")
    if request_version != 5 or config_version != 5:
        raise ContractError("CONFIG_VERSION_UNSUPPORTED_FOR_EXECUTION")


def require_macos_mps_single_worker_first_pass_execution(request_version: int, config_version: int) -> None:
    """Refuse new execution for any contract version other than version six."""

    if type(request_version) is not int or type(config_version) is not int:
        raise ContractError("CONFIG_VERSION_UNSUPPORTED_FOR_EXECUTION")
    if request_version != 6 or config_version != 6:
        raise ContractError("CONFIG_VERSION_UNSUPPORTED_FOR_EXECUTION")


#: Any execution profile document the parallel-validation runtime may load.
RuntimeConfig = (
    ParallelRuntimeConfigLinuxCuda | ParallelRuntimeConfigMacosMpsTwoWorker
    | ParallelRuntimeConfigMacosMpsSingleWorkerRetry | ParallelRuntimeConfigMacosMpsSingleWorkerFirstPass
)
