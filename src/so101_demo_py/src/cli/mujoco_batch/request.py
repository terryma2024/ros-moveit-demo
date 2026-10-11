"""Command-line parsing and the preparation of one validated batch request."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Callable, Mapping

from so101_demo.cli.mujoco_batch.common import (
    CliError,
    _absolute,
    _integer,
    _positive_float,
    _read_existing_json,
)
from so101_demo.cli.mujoco_batch.provenance import (
    _BROKER_IMAGE,
    _catalog,
    _runtime_package_root,
    verify_provenance,
)
from so101_demo.parallel_batch.adaptive_contracts import (
    AdaptiveBatchRequest,
    AdaptiveWorkerOptions,
    PoolRequest,
    load_adaptive_worker_options,
)
from so101_demo.parallel_batch.contracts import (
    BatchKind,
    BatchRequest,
    ContractError,
    RunMode,
    RuntimeConfig,
)


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise CliError(f"ARGUMENT_ERROR: {message}")


@dataclass(frozen=True, slots=True)
class PreparedBatch:
    start_guard: object | None
    request: BatchRequest | PoolRequest | None
    adaptive_request: AdaptiveBatchRequest | None
    config: RuntimeConfig
    config_path: Path
    adaptive_config_path: Path | None
    points_path: Path
    catalog: Mapping[str, Mapping[str, object]]
    expected_final_cup_pose_world: tuple[float, ...]
    catalog_sha256: str
    selection_sha256: str
    broker_image: str
    yolo_weights: Path
    yolo_weights_sha256: str
    grounded_root: Path
    grounded_manifest_sha256: str
    provenance: Mapping[str, object]
    manifest: Mapping[str, object]
    provenance_inputs: Mapping[str, object]
    provenance_verifier: Callable[[Mapping[str, object]], Mapping[str, object]]
    start_guard_evidence: Mapping[str, object] | None
    resume: bool


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="so101_parallel_batch")
    parser.add_argument("--points", type=Path, required=True)
    parser.add_argument("--point-id", action="append", default=[])
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--worker-count")
    parser.add_argument("--contract-version", default="2")
    parser.add_argument("--batch-kind", default="FIRST_PASS")
    parser.add_argument("--original-selection-sha256")
    parser.add_argument("--original-result-sha256")
    parser.add_argument("--original-catalog-sha256")
    parser.add_argument("--original-batch-id")
    parser.add_argument("--adaptive-workers", action="store_true")
    parser.add_argument("--adaptive-config", type=Path)
    parser.add_argument("--fallback-worker-counts")
    parser.add_argument("--initial-points-per-worker")
    parser.add_argument("--worker-start-timeout-s")
    parser.add_argument("--max-infra-attempts-per-point")
    parser.add_argument("--yolo-executor-count")
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--broker-image", required=True)
    # The sealed authority commits to an image digest; the tag above is what the local
    # runtime knows, so a measurement run carries both and each check reads its own.
    parser.add_argument("--broker-image-id")
    parser.add_argument("--yolo-weights", type=Path, required=True)
    parser.add_argument("--yolo-weights-sha256", required=True)
    parser.add_argument("--grounded-root", type=Path, required=True)
    parser.add_argument("--grounded-manifest-sha256", required=True)
    parser.add_argument("--run-mode", required=True)
    parser.add_argument("--live-headroom-evidence", type=Path)
    parser.add_argument("--live-headroom-acceptance", type=Path)
    parser.add_argument("--live-headroom-current-provenance-root", type=Path)
    parser.add_argument("--provenance-binding", type=Path)
    parser.add_argument("--measurement-authorization", type=Path)
    parser.add_argument("--measurement-authorization-sha256")
    parser.add_argument("--resume", action="store_true")
    return parser


def _adaptive_options(options) -> tuple[AdaptiveWorkerOptions, Path]:
    if options.adaptive_config is None:
        raise CliError("ADAPTIVE_CONFIG_REQUIRED")
    adaptive_config_path = _absolute("adaptive_config", options.adaptive_config)
    try:
        defaults = load_adaptive_worker_options(adaptive_config_path)
    except ContractError as error:
        raise CliError(str(error)) from error
    worker_count = (
        defaults.worker_count
        if options.worker_count is None
        else _integer("worker_count", options.worker_count)
    )
    if options.fallback_worker_counts is None:
        fallback_worker_counts = tuple(
            count for count in defaults.fallback_worker_counts if count < worker_count
        )
    else:
        try:
            fallback_worker_counts = tuple(
                _integer("fallback_worker_count", value)
                for value in options.fallback_worker_counts.split(",")
            )
        except CliError as error:
            raise CliError("FALLBACK_WORKER_COUNTS") from error
    initial_points_per_worker = (
        defaults.initial_points_per_worker
        if options.initial_points_per_worker is None
        else _integer(
            "initial_points_per_worker", options.initial_points_per_worker
        )
    )
    worker_start_timeout_s = (
        defaults.worker_start_timeout_s
        if options.worker_start_timeout_s is None
        else _positive_float(
            "worker_start_timeout_s", options.worker_start_timeout_s
        )
    )
    max_infra_attempts_per_point = (
        defaults.max_infra_attempts_per_point
        if options.max_infra_attempts_per_point is None
        else _integer(
            "max_infra_attempts_per_point",
            options.max_infra_attempts_per_point,
        )
    )
    yolo_executor_count = (
        defaults.yolo_executor_count
        if options.yolo_executor_count is None
        else _integer("yolo_executor_count", options.yolo_executor_count)
    )
    try:
        adaptive = AdaptiveWorkerOptions(
            worker_count=worker_count,
            fallback_worker_counts=fallback_worker_counts,
            initial_points_per_worker=initial_points_per_worker,
            worker_start_timeout_s=worker_start_timeout_s,
            max_infra_attempts_per_point=max_infra_attempts_per_point,
            ros_domain_ids=defaults.ros_domain_ids,
            yolo_executor_count=yolo_executor_count,
        )
    except ContractError as error:
        raise CliError(str(error)) from error
    return adaptive, adaptive_config_path


def _batch_evidence_root_state(*, evidence_root: Path, measurement: bool) -> None:
    """Apply the launcher's evidence-root rule for this run.

    A sealed measurement may arrive with its root already created: the measurement harness
    creates the sealed batch root before it spawns this CLI, and
    verify_measurement_arguments pins that root to the authorization's batch root, so
    exclusive creation cannot be required. What is still refused is a root that is not a
    private 0700 directory owned by this user, and one whose batch is already finalized.
    """

    if not measurement:
        if evidence_root.exists() or evidence_root.is_symlink():
            raise CliError("DUPLICATE_BATCH_EVIDENCE_ROOT")
        return
    if not evidence_root.exists():
        return
    root_info = evidence_root.lstat()
    if (
        evidence_root.is_symlink()
        or not stat.S_ISDIR(root_info.st_mode)
        or root_info.st_uid != os.getuid()
        or stat.S_IMODE(root_info.st_mode) != 0o700
    ):
        raise CliError("MEASUREMENT_EVIDENCE_ROOT_INVALID")
    if (evidence_root / "aggregate_results.json").exists():
        raise CliError("DUPLICATE_BATCH_EVIDENCE_ROOT")


def guard_scope(batch_id, worker_count, *, epoch=1, gpu_selector=None, device_selector=None):
    """The real owner/epoch scope for one start-guard check."""

    selector = gpu_selector or device_selector
    if not selector:
        raise CliError("START_GUARD_DEVICE_SELECTOR_REQUIRED")
    from so101_demo.parallel_batch.start_guard import GuardScope
    from so101_demo.parallel_batch.start_guard_probe import read_process_identity

    identity = read_process_identity(os.getpid())
    return GuardScope(
        batch_id=batch_id,
        epoch=epoch,
        owner_pid=os.getpid(),
        owner_starttime_ticks=identity.start_time_ticks if identity is not None else 0,
        gpu_selector=selector,
        worker_count=worker_count,
    )


def device_selector_for(config) -> str:
    """``UUID:<uuid>`` or ``INDEX:<n>`` from the active v3 config; never a host default."""

    selector = getattr(config, "gpu_device", None)
    if selector is None:
        raise CliError("CONFIG_VERSION_UNSUPPORTED_FOR_EXECUTION")
    return f"{selector.selector_kind}:{selector.selector}"


def _prepare_start_guard(options, config, *, batch_id, worker_count, start_guard=None,
                         epoch=1):
    """One bounded CPU/RAM/GPU check before this epoch spawns anything.

    No budget environment, profile or approval is consulted, and a FAIL refuses the start
    instead of allocating a partial batch.
    """

    for name in ("live_headroom_evidence", "live_headroom_acceptance",
                 "live_headroom_current_provenance_root"):
        if getattr(options, name, None) is not None:
            raise CliError("LIVE_HEADROOM_EVIDENCE_UNEXPECTED")
    guard = start_guard or compose_default_start_guard(config.start_guard)
    scope = guard_scope(batch_id, worker_count, epoch=epoch,
                        device_selector=device_selector_for(config))
    try:
        result = guard.require_startable(scope)
    except Exception as error:
        reason = getattr(error, "reason", None) or "START_GUARD_REFUSED"
        raise CliError(reason) from error
    return guard, {
        "policy": {
            "timeout_s": config.start_guard.timeout_s,
            "cpu_busy_warn_fraction": config.start_guard.cpu_busy_warn_fraction,
            "ram_minimum_bytes": config.start_guard.ram_minimum_bytes,
            "ram_minimum_fraction": config.start_guard.ram_minimum_fraction,
            "gpu_minimum_bytes": config.start_guard.gpu_minimum_bytes,
        },
        "status": result.status,
        "checked_monotonic_s": result.completed_monotonic_s,
        "cleanup_state": result.cleanup_state,
        "checks": {
            name: {"status": check.status, "reason": check.reason, "observed": check.observed,
                   "cutoff": check.cutoff, "unit": check.unit}
            for name, check in sorted(result.checks.items())
        },
        "gpu_uuid": None if result.snapshot is None else result.snapshot.gpu_uuid,
        "effective_cpu_cores": None if result.snapshot is None else result.snapshot.effective_cpu_cores,
        "ram_available_bytes": None if result.snapshot is None else result.snapshot.ram_available_bytes,
        "gpu_free_bytes": None if result.snapshot is None else result.snapshot.gpu_free_bytes,
    }


_LEGACY_QUOTA_FLAG = '--max-points-per-worker'


# Offline test entry point only: production callers leave this None so the fixed path
# stays fail-closed until an approved exact-N profile exists. Tests set it through the
# autouse fixture in their own module; no production code assigns it.
_DEFAULT_START_GUARD = None


def compose_default_start_guard(policy):
    """Installed composition: one shared task-level state root and lock."""

    from so101_demo.parallel_batch.start_guard_probe import compose_default_start_guard as compose

    return compose(policy)


def _load_runtime_config(path: Path):
    """New execution loads the closed document: v3 unchanged, v4 added for macOS MPS two-worker.

    The gate is delegated to `two_worker_composition.load_execution_config` so the CLI, the resource
    allocator and the offline tests cannot drift apart on which schemas are executable. v1 and v2
    remain history only, exactly as before.
    """

    from so101_demo.parallel_batch.two_worker_composition import load_execution_config

    return load_execution_config(Path(path))


def _reject_legacy_quota_flag(argv) -> None:
    """Refuse the retired lifetime quota flag before argparse or any resource work."""

    arguments = tuple(sys.argv[1:] if argv is None else argv)
    for argument in arguments:
        if argument == _LEGACY_QUOTA_FLAG or argument.startswith(f'{_LEGACY_QUOTA_FLAG}='):
            raise ContractError('LEGACY_MAX_POINTS_PER_WORKER_UNSUPPORTED')


def prepare_batch(
    argv=None, *, provenance_verifier=verify_provenance, start_guard=None
) -> PreparedBatch:
    _reject_legacy_quota_flag(argv)
    options = build_parser().parse_args(argv)
    retry_names = (
        "original_selection_sha256", "original_result_sha256",
        "original_catalog_sha256", "original_batch_id",
    )
    supplied_retry_names = tuple(
        name for name in retry_names if getattr(options, name) is not None
    )
    if options.batch_kind == "FULL_RESTART_RETRY":
        if options.adaptive_workers:
            raise CliError("RETRY_FIXED_BATCH_REQUIRED")
        if len(supplied_retry_names) != len(retry_names):
            raise CliError("RETRY_ROOT_REQUIRED")
        for name in retry_names[:3]:
            if re.fullmatch(r"[0-9a-f]{64}", getattr(options, name)) is None:
                raise CliError("RETRY_SOURCE_INVALID")
        if (
            re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]*", options.original_batch_id) is None
            or options.original_batch_id == options.batch_id
        ):
            raise CliError("RETRY_ORIGINAL_BATCH_INVALID")
    elif supplied_retry_names:
        raise CliError("RETRY_BINDING_UNSUPPORTED")
    if options.measurement_authorization is not None or (
        options.measurement_authorization_sha256 is not None
    ):
        raise CliError("MEASUREMENT_AUTHORIZATION_RETIRED")
    adaptive_only = (
        options.adaptive_config,
        options.fallback_worker_counts,
        options.initial_points_per_worker,
        options.worker_start_timeout_s,
        options.max_infra_attempts_per_point,
        options.yolo_executor_count,
    )
    if options.adaptive_workers:
        if options.resume:
            raise CliError("ADAPTIVE_RESUME_CONFLICT")
        if any(
            value is not None
            for value in (
                options.live_headroom_evidence,
                options.live_headroom_acceptance,
                options.live_headroom_current_provenance_root,
            )
        ):
            raise CliError("ADAPTIVE_LIVE_HEADROOM_CONFLICT")
        adaptive_worker_options, adaptive_config_path = _adaptive_options(options)
        worker_count = adaptive_worker_options.worker_count
    else:
        if any(value is not None for value in adaptive_only):
            raise CliError("ADAPTIVE_OPTIONS_REQUIRE_FLAG")
        adaptive_worker_options = None
        adaptive_config_path = None
        worker_count = _integer("worker_count", options.worker_count or "2")
    evidence_root = _absolute("evidence_root", options.evidence_root)
    if options.resume:
        try:
            root_info = evidence_root.lstat()
        except OSError as error:
            raise CliError("RECOVERY_BATCH_EVIDENCE_ROOT_MISSING") from error
        if (
            evidence_root.is_symlink()
            or not stat.S_ISDIR(root_info.st_mode)
            or root_info.st_uid != os.getuid()
            or stat.S_IMODE(root_info.st_mode) != 0o700
        ):
            raise CliError("RECOVERY_BATCH_EVIDENCE_ROOT_INVALID")
        if (evidence_root / "aggregate_results.json").exists():
            raise CliError("RECOVERY_BATCH_ALREADY_FINALIZED")
    elif options.adaptive_workers:
        runtime_root = evidence_root / "r" / options.batch_id
        if runtime_root.exists() or runtime_root.is_symlink():
            raise CliError("DUPLICATE_BATCH_EVIDENCE_ROOT")
        if evidence_root.exists() or evidence_root.is_symlink():
            root_info = evidence_root.lstat()
            if (
                evidence_root.is_symlink()
                or not stat.S_ISDIR(root_info.st_mode)
                or root_info.st_uid != os.getuid()
                or stat.S_IMODE(root_info.st_mode) != 0o700
            ):
                raise CliError("ADAPTIVE_EVIDENCE_ROOT_INVALID")
    else:
        _batch_evidence_root_state(evidence_root=evidence_root, measurement=False)
    try:
        mode = RunMode(options.run_mode)
    except ValueError as error:
        raise CliError("UNKNOWN_RUN_MODE") from error
    catalog, catalog_sha = _catalog(options.points)
    if (
        options.batch_kind == "FULL_RESTART_RETRY"
        and options.original_catalog_sha256 != catalog_sha
    ):
        raise CliError("RETRY_CATALOG_MISMATCH")
    supplied = tuple(options.point_id)
    if len(supplied) != len(set(supplied)):
        raise CliError("DUPLICATE_POINT_ID")
    unknown = set(supplied) - set(catalog)
    if unknown:
        raise CliError(f"UNKNOWN_POINT_ID: {sorted(unknown)!r}")
    selected = tuple(point_id for point_id in catalog if not supplied or point_id in supplied)
    selection_payload = json.dumps(list(selected), separators=(",", ":")).encode("utf-8")
    selection_sha = hashlib.sha256(selection_payload).hexdigest()
    config_path = options.config.resolve()
    config = _load_runtime_config(config_path)
    start_guard = None
    guard_summary = None
    if options.adaptive_workers:
        # The adaptive pool allocates through the same guard as the fixed-N path, one check per
        # level; the run prepares it once, for the initial worker count.  Composing it here and
        # threading it into the pool request is what keeps `START_GUARD_UNAVAILABLE` from being
        # raised for every level by an adaptive run that simply never prepared a guard.
        start_guard, _guard_summary = _prepare_start_guard(
            options, config, batch_id=options.batch_id or "cli",
            worker_count=adaptive_worker_options.worker_count, start_guard=start_guard)
    else:
        start_guard, guard_summary = _prepare_start_guard(
            options, config, batch_id=options.batch_id or "cli", worker_count=worker_count,
            start_guard=start_guard)
    if options.yolo_weights_sha256 != config.yolo_weights_sha256:
        raise CliError("YOLO_HASH_MISMATCH")
    if options.grounded_manifest_sha256 != config.grounded_sam_manifest_sha256:
        raise CliError("GROUNDED_HASH_MISMATCH")
    if options.broker_image != _BROKER_IMAGE:
        raise CliError("BROKER_IMAGE_MISMATCH")
    try:
        if options.adaptive_workers:
            request = None
            adaptive_request = AdaptiveBatchRequest(
                options.batch_id,
                mode,
                selected,
                adaptive_worker_options,
                evidence_root,
                start_guard=start_guard,
            )
        else:
            contract_version = _integer(
                "contract_version", options.contract_version or "2"
            )
            if contract_version != 2:
                raise ContractError("LEGACY_CONTRACT_EXECUTION_FORBIDDEN")
            batch_kind = BatchKind(options.batch_kind or "FIRST_PASS")
            request = BatchRequest(
                options.batch_id,
                mode,
                selected,
                worker_count,
                evidence_root,
                batch_kind,
            )
            adaptive_request = None
    except ContractError as error:
        message = str(error)
        if "INSUFFICIENT_CAPACITY" in message:
            raise CliError(f"INSUFFICIENT_CAPACITY: {message}") from error
        raise CliError(message) from error
    inputs = {
        "points": options.points.resolve(),
        "config": config_path,
        "catalog_sha256": catalog_sha,
        "broker_image": options.broker_image,
        "yolo_weights": options.yolo_weights,
        "yolo_weights_sha256": options.yolo_weights_sha256,
        "grounded_root": options.grounded_root,
        "grounded_manifest_sha256": options.grounded_manifest_sha256,
    }
    if options.provenance_binding is not None:
        inputs["provenance_binding"] = _absolute(
            "provenance_binding", options.provenance_binding
        )
    if adaptive_config_path is not None:
        inputs["adaptive_config"] = adaptive_config_path
    try:
        provenance = provenance_verifier(inputs)
    except CliError:
        raise
    except Exception as error:
        # Keep the stable code, but put the underlying failure in the log: the generic wrapper
        # hid a real exception for several rounds because only its message was recorded.
        import traceback

        print(f"PROVENANCE_VERIFICATION_DETAIL: {type(error).__name__}: {error}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        raise CliError("PROVENANCE_VERIFICATION_FAILED") from error
    if not isinstance(provenance, Mapping) or not provenance:
        raise CliError("PROVENANCE_VERIFICATION_FAILED")
    try:
        from so101_demo.core.dynamic_pick import compose_pose, inverse_pose
        from so101_demo.core.dynamic_pick_policy import load_dynamic_policy_variant

        package_root = _runtime_package_root()
        loaded_policy = load_dynamic_policy_variant(package_root, backend="mujoco")
        expected_final_cup_pose_world = compose_pose(
            loaded_policy.template.place_tcp_world,
            inverse_pose(loaded_policy.template.cup_to_tcp_grasp),
        ).values
    except Exception as error:
        raise CliError("TRUSTED_FINAL_TARGET_INVALID") from error
    if adaptive_request is not None:
        manifest = {
            "schema_version": 1,
            "batch_id": adaptive_request.batch_id,
            "run_mode": adaptive_request.run_mode.value,
            "selected_point_ids": list(selected),
            "selection_sha256": selection_sha,
            "catalog_sha256": catalog_sha,
            "expected_final_cup_pose_world": list(expected_final_cup_pose_world),
            "evidence_root": str(evidence_root),
            "provenance": dict(provenance),
            "adaptive_config_path": str(adaptive_config_path),
            "adaptive_worker_options": {
                "worker_count": adaptive_worker_options.worker_count,
                "fallback_worker_counts": list(
                    adaptive_worker_options.fallback_worker_counts
                ),
                "initial_points_per_worker": (
                    adaptive_worker_options.initial_points_per_worker
                ),
                "worker_start_timeout_s": (
                    adaptive_worker_options.worker_start_timeout_s
                ),
                "max_infra_attempts_per_point": (
                    adaptive_worker_options.max_infra_attempts_per_point
                ),
                "ros_domain_ids": list(adaptive_worker_options.ros_domain_ids),
                "yolo_executor_count": adaptive_worker_options.yolo_executor_count,
            },
        }
    else:
        manifest = {
            "schema_version": 3,
            "batch_kind": request.batch_kind.value,
            "batch_id": request.batch_id,
            "run_mode": request.run_mode.value,
            "selected_point_ids": list(selected),
            "selection_sha256": selection_sha,
            "catalog_sha256": catalog_sha,
            "expected_final_cup_pose_world": list(expected_final_cup_pose_world),
            "worker_count": worker_count,
            "evidence_root": str(evidence_root),
            "provenance": dict(provenance),
            "start_guard": None if guard_summary is None else {
                # The frozen plan records only what it will enforce. A guard *status* is a
                # host observation (busy CPU can turn PASS into WARN between two identical
                # runs), so embedding it would make a resume refuse a legitimate replay;
                # the observation itself is kept in the guard evidence and the receipts.
                "cleanup_state": guard_summary["cleanup_state"],
                "policy": dict(guard_summary["policy"]),
            },
        }
        if options.batch_kind == "FULL_RESTART_RETRY":
            manifest["retry_binding"] = {
                name: getattr(options, name) for name in retry_names
            }
    if options.resume:
        existing = _read_existing_json(
            evidence_root / "batch_manifest.json", label="BATCH_MANIFEST"
        )
        if existing != manifest:
            raise CliError("RECOVERY_BATCH_MANIFEST_MISMATCH")
    return PreparedBatch(
        start_guard=start_guard,
        request=request,
        adaptive_request=adaptive_request,
        config=config,
        config_path=config_path,
        adaptive_config_path=adaptive_config_path,
        points_path=options.points.resolve(),
        catalog=catalog,
        expected_final_cup_pose_world=tuple(expected_final_cup_pose_world),
        catalog_sha256=catalog_sha,
        selection_sha256=selection_sha,
        broker_image=options.broker_image,
        yolo_weights=options.yolo_weights,
        yolo_weights_sha256=options.yolo_weights_sha256,
        grounded_root=options.grounded_root,
        grounded_manifest_sha256=options.grounded_manifest_sha256,
        provenance=dict(provenance),
        manifest=manifest,
        provenance_inputs=dict(inputs),
        provenance_verifier=provenance_verifier,
        start_guard_evidence=guard_summary,
        resume=options.resume,
    )
