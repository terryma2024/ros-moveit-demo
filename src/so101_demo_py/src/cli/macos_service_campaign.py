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
from so101_demo.parallel_batch.macos_control_endpoint import MacosFixedControlEndpoint

#: The exact-W2 worker count this platform runs, and the reason for the refusal below.
EXACT_W2_WORKERS = 2

#: The launcher this adapter drives.
CAMPAIGN_MODULE = "so101_demo.cli.macos_w2_campaign"

#: Bounded stop: SIGTERM, then SIGKILL, then a fresh read of the group.
STOP_TERM_TIMEOUT_S = 5.0
STOP_KILL_TIMEOUT_S = 5.0


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
    parser.add_argument("--provenance-binding", type=Path, default=None)
    return parser


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def validate(arguments, *, environment=None) -> dict:
    """Refuse anything this platform cannot execute, by name, before anything is spawned.

    Every refusal here is a fact about the request, not about the host's mood: the worker count is the
    exact-W2 count this platform declares, the digests are the ones the service resolved from the
    installed layout, and the campaign identity is the one the service minted with the control token.
    """
    environment = os.environ if environment is None else environment
    if arguments.run_mode != "execute":
        raise ServiceCampaignError("RUN_MODE_UNSUPPORTED", str(arguments.run_mode))
    if arguments.worker_count != EXACT_W2_WORKERS:
        raise ServiceCampaignError(
            "PLATFORM_WORKER_COUNT_UNSUPPORTED", str(arguments.worker_count)
        )
    if not arguments.config.is_file():
        raise ServiceCampaignError("CONFIG_MISSING", str(arguments.config))
    from so101_demo.parallel_batch.contracts import ContractError, ParallelRuntimeConfigV4
    from so101_demo.parallel_batch.w2_composition import (
        CompositionError,
        load_execution_config_for_schema,
    )

    try:
        config = load_execution_config_for_schema(arguments.config)
    except (ContractError, CompositionError, ValueError) as error:
        raise ServiceCampaignError("CONFIG_UNREADABLE", f"{type(error).__name__}: {error}") from error
    if not isinstance(config, ParallelRuntimeConfigV4):
        raise ServiceCampaignError(
            "CONFIG_VERSION_UNSUPPORTED_FOR_EXECUTION", str(getattr(config, "schema_version", "?"))
        )
    if getattr(config, "worker_count", None) != EXACT_W2_WORKERS:
        raise ServiceCampaignError(
            "PLATFORM_WORKER_COUNT_UNSUPPORTED", f"config says {getattr(config, 'worker_count', '?')}"
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
    return {
        "campaign_id": campaign_id,
        "batch_id": arguments.batch_id,
        "coordinator_epoch": int(epoch),
        "control_socket": control_socket,
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
    }


def campaign_argv(arguments) -> list[str]:
    """The argv the existing macOS campaign CLI is driven with. Nothing else is added to it."""
    argv = [
        sys.executable, "-m", CAMPAIGN_MODULE,
        "--config", str(arguments.config),
        "--campaign-id", os.environ["SO101_FIXED_CONTROL_CAMPAIGN_ID"],
        "--batch-id", arguments.batch_id,
        "--evidence-root", str(arguments.evidence_root),
        "--yolo-weights", str(arguments.yolo_weights),
        "--grounded-root", str(arguments.grounded_root),
    ]
    for point_id in arguments.point_id:
        argv.extend(("--point-id", point_id))
    return argv


class OwnedCampaign:
    """The campaign child, owned exactly: one process group, cleared as a group, never one pid."""

    def __init__(self, argv: list[str], *, log_path: Path) -> None:
        environment = dict(os.environ)
        # Keep the launcher from re-executing: a re-exec rewrites the kernel argv the service checks.
        environment["PYTORCH_ENABLE_MPS_FALLBACK"] = "0"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log = open(log_path, "xb", buffering=0)
        self.process = subprocess.Popen(
            argv,
            env=environment,
            start_new_session=True,
            stdin=subprocess.DEVNULL,
            stdout=self._log,
            stderr=subprocess.STDOUT,
            close_fds=True,
        )
        self.pgid = self.process.pid  # start_new_session makes the child its own group leader
        self.log_path = log_path

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


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(sys.argv[1:] if argv is None else argv)
    document: dict = {"status": "PENDING"}
    try:
        validated = validate(arguments)
    except ServiceCampaignError as error:
        document.update(status="REFUSED", stage="validate",
                        refusal=error.reason, detail=error.detail)
        print(json.dumps(document, indent=2, sort_keys=True))
        return 1
    document["request"] = validated

    result_path = arguments.evidence_root / "campaign-result.json"
    campaign = OwnedCampaign(
        campaign_argv(arguments), log_path=arguments.evidence_root / "campaign.log"
    )
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
        campaign_id=validated["campaign_id"],
        batch_id=validated["batch_id"],
        coordinator_epoch=validated["coordinator_epoch"],
        path=Path(validated["control_socket"]),
        control_token=os.environ["SO101_FIXED_CONTROL_TOKEN"],
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
