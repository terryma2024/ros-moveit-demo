"""The macOS campaign entry point a service can own.

The service launches a fixed coordinator with one fixed argv (``supervisor.FIXED_COORDINATOR_FLAGS``)
and expects it to open the control socket named by ``SO101_FIXED_CONTROL_SOCKET``. On Linux that argv
is ``so101_parallel_batch``; on macOS that runner refuses the host
(``CONFIG_VERSION_UNSUPPORTED_FOR_EXECUTION``, then ``GPU_TARGET_UNAVAILABLE``), and the entry point
that does run here - ``so101_demo.cli.macos_w2_campaign`` - takes a different set of flags and has no
control path at all.

This module is the typed adapter between the two. It is deliberately narrow:

* it **validates** what it was asked to do instead of passing it along - run mode, exact-W2 worker
  count, the weights and manifest digests, the config schema, the campaign identity the service put in
  the environment - and refuses by name;
* it runs the real campaign as an **owned child in its own process group**, so a stop is a group stop
  and not a single-pid signal (this task's leak, in the service's own process tree);
* it serves the service's control wire from :mod:`parallel_batch.macos_control_endpoint`, reporting
  what it can prove and nothing more.

The child is given ``PYTORCH_ENABLE_MPS_FALLBACK=0`` in its environment. That keeps the campaign
launcher from re-executing itself: a re-exec replaces the kernel's argv with ``python -m <module>``,
which is not what the service asked for, and the service's spawn barrier compares exactly that.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
import signal
import subprocess
import sys
import time

# The service launches its coordinator as a *script* (``[sys.executable, <path>, ...flags]``), not as a
# module: a relative import here fails at the first live launch with "attempted relative import with no
# known parent package", which a test that imports this file as a module cannot see. Absolute imports
# need ``so101_demo`` to be importable, which the service guarantees - it imports that package itself to
# resolve its layout, and the child inherits the same path.
from so101_demo.parallel_batch.contracts import (
    BatchKindV2,
    ContractError,
    ExecutionProfile,
    ParallelRuntimeConfigV4,
    ParallelRuntimeConfigV5,
    ParallelRuntimeConfigV6,
    execution_route_for_schema,
    resolve_execution_route,
)
from so101_demo.parallel_batch.macos_control_endpoint import MacosFixedControlEndpoint
from so101_demo.parallel_batch.start_guard_probe import (
    StartGuardRefused,
    run_campaign_start_guard,
)
from so101_demo.parallel_batch.w2_composition import (
    CompositionError,
    load_execution_config_for_schema,
)
from so101_demo.runtime.owner_records import (
    ROOT_VARIABLE as OWNER_ROOT_VARIABLE,
    OwnerContext,
    OwnerRecordError,
    OwnerSpawnRecorder,
    owner_context_from_environment,
    spawner_token_from_environment,
)

#: The exact-W2 worker count, kept for the refusal vocabulary this adapter has always used.
EXACT_W2_WORKERS = 2

#: The launcher this adapter drives for exact W2. The two W1 routes are named by the table below.
CAMPAIGN_MODULE = "so101_demo.cli.macos_w2_campaign"

#: The closed dispatch table: ``(schema_version, execution_profile)`` -> the one entry point that
#: executes it. There is no default entry, no generic ``--batch-kind`` fallback and no cross-profile
#: reuse: a key that is not in this table is refused by name before anything is spawned.
ROUTE_MODULES = {
    (4, str(ExecutionProfile.MPS_W2_FIRST_PASS)): "so101_demo.cli.macos_w2_campaign",
    (5, str(ExecutionProfile.MPS_W1_FULL_RESTART_RETRY)): "so101_demo.cli.macos_n1_retry",
    (6, str(ExecutionProfile.MPS_W1_FIRST_PASS)): "so101_demo.cli.macos_n1_first_pass",
}

#: The config class each admitted schema must resolve to.
ROUTE_CONFIG_CLASSES = {
    4: ParallelRuntimeConfigV4,
    5: ParallelRuntimeConfigV5,
    6: ParallelRuntimeConfigV6,
}

#: Optional request declarations. The service's argv cannot carry them, so when the environment names
#: them they are checked against the document instead of being silently ignored.
BATCH_KIND_VARIABLE = "SO101_FIXED_CONTROL_BATCH_KIND"
EXECUTION_PROFILE_VARIABLE = "SO101_FIXED_CONTROL_EXECUTION_PROFILE"

#: Bounded stop: SIGTERM, then SIGKILL, then a fresh read of the group.
STOP_TERM_TIMEOUT_S = 5.0
STOP_KILL_TIMEOUT_S = 5.0

#: The admitted-retry binding the service sends for a `FULL_RESTART_RETRY`, in the caller's own
#: vocabulary. The adapter parses these and forwards them verbatim. It deliberately accepts no
#: `--retry-root`: the service sends the digests its store already admitted, while a root would make
#: the v5 route re-hash the prior document's bytes and refuse `RETRY_SOURCE_MISMATCH` against a
#: genuinely different admitted digest.
RETRY_BINDING_FLAGS = {
    "original_selection_sha256": "--original-selection-sha256",
    "original_result_sha256": "--original-result-sha256",
    "original_catalog_sha256": "--original-catalog-sha256",
    "original_batch_id": "--original-batch-id",
}

#: The two an admitted retry cannot be executed without; the other two are optional.
REQUIRED_RETRY_BINDING = ("original_selection_sha256", "original_result_sha256")


class ServiceCampaignError(RuntimeError):
    """The request cannot be executed on this platform. Never a warning."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="so101_macos_service_campaign",
        description="Run one exact-W2 macOS MPS campaign under a service's control endpoint.",
    )
    parser.add_argument("--points", type=Path, required=True,
                        help="the selection document the service resolved")
    parser.add_argument("--config", type=Path, required=True,
                        help="the schema-v4 macOS MPS document")
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--worker-count", type=int, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--broker-image", required=True,
                        help="the container broker image the service resolved; unused on MPS, recorded")
    parser.add_argument("--yolo-weights", type=Path, required=True)
    parser.add_argument("--yolo-weights-sha256", required=True)
    parser.add_argument("--grounded-root", type=Path, required=True)
    parser.add_argument("--grounded-manifest-sha256", required=True)
    parser.add_argument("--run-mode", required=True)
    parser.add_argument("--point-id", action="append", default=[])
    # The admitted-retry binding, forwarded to the v5 route exactly as the service declared it.
    for name, flag in RETRY_BINDING_FLAGS.items():
        parser.add_argument(flag, dest=name, default=None)
    parser.add_argument("--provenance-binding", type=Path, default=None)
    return parser


def retry_binding_values(arguments) -> dict:
    """The retry binding this argv declares, with every unset flag left out."""

    return {name: getattr(arguments, name, None) for name in RETRY_BINDING_FLAGS
            if getattr(arguments, name, None) is not None}


def require_retry_binding(arguments, route) -> dict:
    """The declared retry binding, or a refusal by name before anything is spawned.

    A half-named binding is worse than none: the v5 entry would refuse it in the child, after the
    adapter had already taken a start guard and created a campaign child. A retry flag on a route
    that executes no retry would otherwise be dropped silently, so it is refused here too.
    """

    values = retry_binding_values(arguments)
    if not values:
        return {}
    is_retry_route = (
        str(route.batch_kind) == str(BatchKindV2.FULL_RESTART_RETRY)
        and str(route.execution_profile) == str(ExecutionProfile.MPS_W1_FULL_RESTART_RETRY))
    if not is_retry_route:
        raise ServiceCampaignError(
            "RETRY_BINDING_UNSUPPORTED",
            f"{route.execution_profile} executes no retry, so "
            f"{sorted(RETRY_BINDING_FLAGS[name] for name in values)} cannot be honoured")
    missing = [RETRY_BINDING_FLAGS[name] for name in REQUIRED_RETRY_BINDING
               if name not in values]
    if missing:
        raise ServiceCampaignError(
            "RETRY_ROOT_REQUIRED",
            "an admitted retry must name " + " and ".join(missing)
            + " beside the flags it did name")
    return values


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclass(frozen=True)
class AdapterRoute:
    """The resolved dispatch key: the document, its closed route, the executing module and the
    JSON-safe request record."""

    config: object
    route: object
    module: str
    record: dict


def resolve_request(arguments, *, environment=None, platform=None) -> AdapterRoute:
    """Resolve and refuse the request, by name, before anything is spawned.

    The dispatch key is ``(schema_version, execution_profile, batch_kind, worker_count)``. The schema
    and the profile come from the document, the batch kind is the one that profile admits (and is
    checked against the request's own declaration when the service supplies one), and the worker
    count is the one the request and the document must agree on. Every refusal here is a fact about
    the request, not about the host's mood.
    """
    environment = os.environ if environment is None else environment
    if arguments.run_mode != "execute":
        raise ServiceCampaignError("RUN_MODE_UNSUPPORTED", str(arguments.run_mode))
    if arguments.worker_count not in (1, EXACT_W2_WORKERS):
        raise ServiceCampaignError(
            "PLATFORM_WORKER_COUNT_UNSUPPORTED", str(arguments.worker_count)
        )
    if not arguments.config.is_file():
        raise ServiceCampaignError("CONFIG_MISSING", str(arguments.config))
    try:
        config = load_execution_config_for_schema(arguments.config, platform=platform)
    except (ContractError, CompositionError, ValueError) as error:
        raise ServiceCampaignError("CONFIG_UNREADABLE", f"{type(error).__name__}: {error}") from error
    version = getattr(config, "schema_version", None)
    expected_class = ROUTE_CONFIG_CLASSES.get(version)
    if expected_class is None or not isinstance(config, expected_class):
        raise ServiceCampaignError("CONFIG_VERSION_UNSUPPORTED_FOR_EXECUTION", str(version))
    # The schema owns exactly one approved route; the profile and the batch kind come from that
    # table rather than from the document, so a document cannot name its own profile.
    try:
        approved = execution_route_for_schema(version)
    except ContractError as error:
        raise ServiceCampaignError(
            "CONFIG_VERSION_UNSUPPORTED_FOR_EXECUTION", str(version)) from error
    execution_profile = str(approved.execution_profile)
    declared_profile = str(environment.get(EXECUTION_PROFILE_VARIABLE) or execution_profile)
    if declared_profile != execution_profile:
        raise ServiceCampaignError(
            "PROFILE_SCHEMA_MISMATCH", f"request says {declared_profile} for schema v{version}"
        )
    # The argv the service launches cannot carry a batch kind - the flag set is fixed - so the
    # profile's own kind is the request's, and a declaration the service *does* make in the
    # environment has to agree with the document rather than override it.
    declared_kind = str(environment.get(BATCH_KIND_VARIABLE) or approved.batch_kind)
    try:
        route = resolve_execution_route(
            schema_version=version, execution_profile=execution_profile,
            batch_kind=declared_kind, worker_count=arguments.worker_count)
    except ContractError as error:
        raise ServiceCampaignError(str(error), f"schema v{version} {execution_profile}") from error
    module = ROUTE_MODULES.get((route.schema_version, str(route.execution_profile)))
    if module is None:
        raise ServiceCampaignError(
            "EXECUTION_ROUTE_UNSUPPORTED", f"{route.schema_version}/{route.execution_profile}"
        )
    if not arguments.yolo_weights.is_file():
        raise ServiceCampaignError("YOLO_WEIGHTS_MISSING", str(arguments.yolo_weights))
    observed_weights = _digest(arguments.yolo_weights)
    if observed_weights != arguments.yolo_weights_sha256:
        raise ServiceCampaignError(
            "YOLO_WEIGHTS_SHA256_MISMATCH",
            f"{observed_weights} != {arguments.yolo_weights_sha256}",
        )
    manifest = arguments.grounded_root / "manifest.json"
    if not manifest.is_file():
        raise ServiceCampaignError("GROUNDED_MANIFEST_MISSING", str(manifest))
    observed_manifest = _digest(manifest)
    if observed_manifest != arguments.grounded_manifest_sha256:
        raise ServiceCampaignError(
            "GROUNDED_MANIFEST_SHA256_MISMATCH",
            f"{observed_manifest} != {arguments.grounded_manifest_sha256}",
        )
    if not arguments.points.is_file():
        raise ServiceCampaignError("POINTS_MISSING", str(arguments.points))
    if not arguments.point_id:
        raise ServiceCampaignError("SELECTED_POINTS_REQUIRED")
    retry_binding = require_retry_binding(arguments, route)
    campaign_id = str(environment.get("SO101_FIXED_CONTROL_CAMPAIGN_ID") or "")
    control_socket = str(environment.get("SO101_FIXED_CONTROL_SOCKET") or "")
    control_token = str(environment.get("SO101_FIXED_CONTROL_TOKEN") or "")
    if not campaign_id:
        raise ServiceCampaignError("CONTROL_CAMPAIGN_ID_MISSING")
    if not control_socket or not control_token:
        raise ServiceCampaignError("CONTROL_ENDPOINT_UNSPECIFIED")
    epoch = environment.get("SO101_FIXED_CONTROL_EPOCH", "1")
    if not str(epoch).isdigit() or int(epoch) <= 0:
        raise ServiceCampaignError("CONTROL_EPOCH_INVALID", str(epoch))
    record = {
        "campaign_id": campaign_id,
        "batch_id": arguments.batch_id,
        "coordinator_epoch": int(epoch),
        "control_socket": control_socket,
        "schema_version": route.schema_version,
        "execution_profile": str(route.execution_profile),
        "batch_kind": str(route.batch_kind),
        "worker_count": route.worker_count,
        "campaign_module": module,
        # Recorded, not silently dropped: the in-process MPS broker makes a container image
        # meaningless here, and a reader should see that this was a decision rather than an omission.
        "broker_image": arguments.broker_image,
        "broker_image_used": False,
        "broker_image_note": "MPS broker runs in the campaign process; no container image is used",
        "provenance_binding": str(arguments.provenance_binding)
        if arguments.provenance_binding is not None
        else None,
        "yolo_weights_sha256": observed_weights,
        "grounded_manifest_sha256": observed_manifest,
        "selected_point_ids": list(arguments.point_id),
        # Recorded, so the evidence says which admitted chain a retry executed.
        "retry_binding": retry_binding,
    }
    return AdapterRoute(config=config, route=route, module=module, record=record)


def validate(arguments, *, environment=None, platform=None) -> dict:
    """The JSON-safe request record, resolved through the closed route table.

    Kept as the adapter's validating entry point: it refuses by name and returns the record the
    evidence documents quote.
    """

    return resolve_request(arguments, environment=environment, platform=platform).record


def campaign_argv(arguments, module: str = CAMPAIGN_MODULE, *,
                  campaign_id: str | None = None) -> list[str]:
    """The argv one campaign entry point is driven with.

    A first-pass argv is byte-identical to what it was before the retry binding existed: the four
    flags are appended only when the request declared them, and then verbatim, so the child parses
    exactly the digests the service admitted. A half-named binding is refused here as well as in
    `require_retry_binding`, so a direct caller cannot drop the missing half silently.
    """

    if campaign_id is None:
        campaign_id = os.environ["SO101_FIXED_CONTROL_CAMPAIGN_ID"]
    binding = retry_binding_values(arguments)
    missing = [RETRY_BINDING_FLAGS[name] for name in REQUIRED_RETRY_BINDING
               if name not in binding]
    if binding and missing:
        raise ServiceCampaignError(
            "RETRY_ROOT_REQUIRED",
            "an admitted retry must name " + " and ".join(missing)
            + " beside the flags it did name")
    argv = [
        sys.executable, "-m", module,
        "--config", str(arguments.config),
        "--campaign-id", campaign_id,
        "--batch-id", arguments.batch_id,
        "--evidence-root", str(arguments.evidence_root),
        "--yolo-weights", str(arguments.yolo_weights),
        "--grounded-root", str(arguments.grounded_root),
    ]
    for name, flag in RETRY_BINDING_FLAGS.items():
        if name in binding:
            argv.extend((flag, str(binding[name])))
    for point_id in arguments.point_id:
        argv.extend(("--point-id", point_id))
    return argv


def adapter_owner_context(arguments, *, environment=None) -> OwnerContext | None:
    """The owner context this adapter records its CAMPAIGN spawn under, or ``None`` when inert.

    ``SO101_OWNER_TREE_ROOT`` is the switch: without it this adapter owns no tree and spawns exactly
    as it did before owner records existed. With it, the campaign identity this adapter already
    validated fills in whatever the environment did not carry, because the service sets the root for
    the process it launches while the campaign id, the batch id and the epoch are facts this adapter
    must have anyway to serve the control endpoint. A root with an identity that cannot be used is
    *inert*, not a refusal: refusing would take a campaign down over an evidence path.
    """

    environment = os.environ if environment is None else environment
    context = owner_context_from_environment(environment)
    if context is not None:
        return context
    raw_root = environment.get(OWNER_ROOT_VARIABLE)
    if not isinstance(raw_root, str) or not raw_root.strip():
        return None
    try:
        return OwnerContext(
            root=Path(raw_root),
            campaign_id=str(environment.get("SO101_FIXED_CONTROL_CAMPAIGN_ID") or ""),
            batch_id=str(arguments.batch_id or ""),
            generation=int(environment.get("SO101_FIXED_CONTROL_EPOCH") or 1),
            parent_spawn_token=spawner_token_from_environment(environment),
        )
    except (OwnerRecordError, TypeError, ValueError):
        return None


class OwnedCampaign:
    """The campaign child, owned exactly: one process group, cleared as a group, never one pid."""

    def __init__(
        self,
        argv: list[str],
        *,
        log_path: Path,
        owner_context: OwnerContext | None = None,
        owner_confirm_deadline_s: float = 2.0,
    ) -> None:
        environment = dict(os.environ)
        # Keep the launcher from re-executing: a re-exec rewrites the kernel argv the service checks.
        environment["PYTORCH_ENABLE_MPS_FALLBACK"] = "0"
        recorder = None
        if owner_context is not None:
            # The intent is durable before Popen, and the campaign child is handed its own token plus
            # this adapter's token, so the campaign, its Workers and their stations all land in the
            # same owner tree.
            recorder = OwnerSpawnRecorder.begin(
                context=owner_context,
                role="CAMPAIGN",
                argv=argv,
                parent_spawn_token=spawner_token_from_environment(os.environ),
                own_session=True,
            )
            environment = recorder.child_environment(environment)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log = open(log_path, "xb", buffering=0)
        try:
            self.process = subprocess.Popen(
                argv,
                env=environment,
                start_new_session=True,
                stdin=subprocess.DEVNULL,
                stdout=self._log,
                stderr=subprocess.STDOUT,
                close_fds=True,
            )
        except BaseException as error:
            self._log.close()
            self._abandon(recorder, error)
            raise
        self.record = recorder
        if recorder is not None:
            try:
                recorder.confirm(self.process.pid, deadline_s=owner_confirm_deadline_s)
            except OwnerRecordError as error:
                # A child whose kernel identity can never be read back is not one this adapter may
                # claim to own, so the record is abandoned and the failure is reported rather than
                # a campaign running under a record that does not name it.
                self._log.close()
                self._abandon(recorder, error)
                raise
        self.pgid = self.process.pid  # start_new_session makes the child its own group leader
        self.log_path = log_path

    @staticmethod
    def _abandon(recorder: OwnerSpawnRecorder | None, error: BaseException) -> None:
        """Mark the record of a campaign that never started. The original failure still propagates."""

        if recorder is None:
            return
        reason = error.code if isinstance(error, OwnerRecordError) else "SPAWN_FAILED"
        try:
            recorder.abandon(reason)
        except (OwnerRecordError, OSError):
            pass

    def poll(self) -> int | None:
        return self.process.poll()

    def _live_members(self) -> list[int]:
        """Non-zombie members of the owned group, read after the signals were sent."""
        try:
            import psutil
        except ImportError:
            return [self.pgid]  # cannot prove the group is empty, so it is not reported empty
        members = []
        for process in psutil.process_iter(["pid", "status"]):
            try:
                if os.getpgid(process.info["pid"]) != self.pgid:
                    continue
            except (psutil.Error, OSError):
                continue
            if process.info["status"] != psutil.STATUS_ZOMBIE:
                members.append(process.info["pid"])
        return sorted(members)

    def _await_clear(self, timeout_s: float) -> list[int]:
        deadline = time.monotonic() + timeout_s
        survivors = self._live_members()
        while survivors and time.monotonic() < deadline:
            time.sleep(0.05)
            survivors = self._live_members()
        return survivors

    def stop(self, *, timeout_s: float = STOP_TERM_TIMEOUT_S) -> dict:
        """Terminate the whole group, escalating once, and report what is left."""
        started = time.monotonic()
        term_sent = self._signal(signal.SIGTERM)
        survivors = self._await_clear(timeout_s)
        kill_sent = False
        if survivors:
            kill_sent = self._signal(signal.SIGKILL)
            survivors = self._await_clear(STOP_KILL_TIMEOUT_S)
        if self.process.poll() is None:
            try:
                self.process.wait(timeout=STOP_KILL_TIMEOUT_S)
            except subprocess.TimeoutExpired:
                pass
        return {
            "pgid": self.pgid,
            "leader_pid": self.process.pid,
            "term_sent": term_sent,
            "kill_sent": kill_sent,
            "survivors": survivors,
            "clear": not survivors,
            "elapsed_s": round(time.monotonic() - started, 3),
        }

    def _signal(self, number: int) -> bool:
        try:
            os.killpg(self.pgid, number)
        except (ProcessLookupError, PermissionError):
            return False
        return True

    def close(self) -> None:
        self._log.close()


def adapter_start_guard(route: AdapterRoute, arguments, *, guard=None,
                       environment=None):
    """One fresh start-guard admission before any campaign child process is created.

    Design section 7: the campaign adapter runs a fresh check before it creates anything. The
    probe wiring is composed for the document's own profile, and a previous preflight result is
    never reused - there is no cache here to reuse. The returned document is the audit record.
    """

    from so101_demo.cli.macos_w2_campaign import guard_document

    environment = os.environ if environment is None else environment
    runner = guard or run_campaign_start_guard
    policy = route.config.start_guard
    try:
        result = runner(policy=policy, batch_id=arguments.batch_id,
                        worker_count=route.route.worker_count,
                        state_root=Path(arguments.evidence_root) / "start-guard-state")
    except StartGuardRefused as refusal:
        result = refusal.result
    document = guard_document(result)
    root = Path(arguments.evidence_root)
    root.mkdir(parents=True, exist_ok=True)
    (root / "start-guard.json").write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    return document, result


def main(argv: list[str] | None = None, *, guard=None, environment=None) -> int:
    arguments = build_parser().parse_args(sys.argv[1:] if argv is None else argv)
    environment = os.environ if environment is None else environment
    document: dict = {"status": "PENDING"}
    try:
        route = resolve_request(arguments, environment=environment)
    except ServiceCampaignError as error:
        document.update(status="REFUSED", stage="validate",
                        refusal=error.reason, detail=error.detail)
        print(json.dumps(document, indent=2, sort_keys=True))
        return 1
    document["request"] = route.record

    # The fresh admission runs before the campaign child exists. A FAIL is a refusal: nothing is
    # spawned and the reason is written down.
    audit, admission = adapter_start_guard(route, arguments, guard=guard, environment=environment)
    document["start_guard"] = audit
    if admission.status == "FAIL" or admission.cleanup_state != "CLEAR":
        document.update(status="REFUSED", stage="start_guard", refusal=audit["reason"],
                        start_guard=audit)
        print(json.dumps(document, indent=2, sort_keys=True))
        return 4

    result_path = arguments.evidence_root / "campaign-result.json"
    try:
        campaign = OwnedCampaign(
            campaign_argv(arguments, route.module,
                          campaign_id=route.record["campaign_id"]),
            log_path=arguments.evidence_root / "campaign.log",
            owner_context=adapter_owner_context(arguments, environment=environment),
        )
    except OwnerRecordError as error:
        # A durable owner record that cannot be written or confirmed refuses the campaign by name:
        # a campaign running with an unusable record is exactly what the recovery path must not see.
        document.update(status="REFUSED", stage="campaign_spawn",
                        refusal=error.code, detail=error.detail)
        print(json.dumps(document, indent=2, sort_keys=True))
        return 1
    stop_record: dict = {}

    def state() -> dict:
        """What the campaign can actually show, never what a caller would like it to show."""
        result: dict = {}
        if result_path.is_file():
            try:
                result = json.loads(result_path.read_text())
            except (OSError, ValueError):
                result = {}
        terminal = bool(result) or campaign.poll() is not None
        cleanup = result.get("cleanup") or {}
        return {
            "state": "TERMINAL" if terminal else "STOPPING" if stop_record else "RUNNING",
            "batch_terminal": terminal,
            # The campaign's own cleanup, and only when it ran: a stop acknowledgement is not one.
            "batch_cleanup_complete": bool(cleanup.get("complete")),
            "owned_descendants_gone": bool(stop_record.get("clear")),
        }

    def request_stop(command_id: str) -> None:
        receipt = campaign.stop()
        stop_record.update(receipt, command_id=command_id)
        (arguments.evidence_root / "control-stop.json").write_text(
            json.dumps(stop_record, indent=2, sort_keys=True) + "\n"
        )

    endpoint = MacosFixedControlEndpoint(
        campaign_id=route.record["campaign_id"],
        batch_id=route.record["batch_id"],
        coordinator_epoch=route.record["coordinator_epoch"],
        path=Path(route.record["control_socket"]),
        control_token=environment["SO101_FIXED_CONTROL_TOKEN"],
        state_provider=state,
        request_stop=request_stop,
    )

    def forward_signal(_number, _frame):
        # The service stops this process's group; the child leads a group of its own, so it has to be
        # taken down explicitly rather than relied on to notice.
        receipt = campaign.stop()
        stop_record.update(receipt, command_id="SERVICE_SIGNAL")
        raise SystemExit(0)

    exit_code = 1
    try:
        endpoint.start()
        for name in ("SIGTERM", "SIGINT"):
            signal.signal(getattr(signal, name), forward_signal)
        exit_code = campaign.process.wait()
    except SystemExit as stop:
        exit_code = int(stop.code or 0)
    finally:
        if campaign.poll() is None:
            stop_record.update(campaign.stop(), command_id="ADAPTER_EXIT")
        endpoint.close()
        campaign.close()

    document["campaign_exit_code"] = exit_code
    document["campaign_result"] = str(result_path) if result_path.is_file() else None
    document["control_stop"] = stop_record or None
    if result_path.is_file():
        try:
            inner = json.loads(result_path.read_text())
            document["campaign_status"] = inner.get("status")
            document["cleanup"] = inner.get("cleanup")
        except (OSError, ValueError):
            document["campaign_status"] = "UNREADABLE"
    document["status"] = (
        "SERVICE_CAMPAIGN_PASS"
        if document.get("campaign_status") == "W2_CAMPAIGN_PASS" and exit_code == 0
        else "SERVICE_CAMPAIGN_INCOMPLETE"
    )
    print(json.dumps(document, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
