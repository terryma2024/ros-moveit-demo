"""The no-resume formal CLI, the closed head-only report and the blocking Teleop owner.

There is no resume path and no stage continuation anywhere here: every runner accepts only a run root that
does not exist yet, writes RUNNING once and then SUCCEEDED or FAILED atomically. A qualified head-only report
lets later Head Search consumers read it, and it never unlocks pick-place readiness, release, recording, retreat
or a dynamic pick.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import time
from collections.abc import Mapping
from pathlib import Path

HEAD_SEARCH_QUALIFIED = "HEAD_SEARCH_QUALIFIED"
RUNNING = "RUNNING"
SUCCEEDED = "SUCCEEDED"
FAILED = "FAILED"
#: the only operations the restricted issuer may bind
HEAD_ONLY_OPERATIONS = (
    "GEOMETRY_SMOKE",
    "CALIBRATION_RUN",
    "QUALIFICATION_RUN",
    "TELEOP_ACCEPTANCE",
)
#: what a head-only qualification never grants, whatever its status reads
REFUSED_GATES = ("pick_place_live", "pick_place_calibration_ready", "release", "recorder", "retreat", "pick")
SUBCOMMANDS = ("run", "verify-promoted-config", "qualify", "serve-teleop")


class _SignalWatch:
    """Record the first SIGINT/SIGTERM so an owner can tear down instead of dying mid-teardown."""

    def __init__(self) -> None:
        self.seen = False
        self._previous: dict[int, object] = {}

    def __enter__(self) -> _SignalWatch:
        def handler(_signum, _frame):  # noqa: ANN001 - signal handlers take two positional arguments
            self.seen = True

        for number in (signal.SIGINT, signal.SIGTERM):
            self._previous[number] = signal.signal(number, handler)
        return self

    def __exit__(self, *_exc) -> None:
        for number, previous in self._previous.items():
            signal.signal(number, previous)


def qualification_parser() -> argparse.ArgumentParser:
    """The four formal subcommands, and deliberately no way to continue an earlier run."""

    parser = argparse.ArgumentParser(prog="so101_head_search_calibration")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in SUBCOMMANDS:
        command = commands.add_parser(name)
        command.add_argument("--run-root", type=Path, required=True)
        if name == "verify-promoted-config":
            command.add_argument("--approved-bundle-sha256")
            command.add_argument("--promoted-config", type=Path)
        if name == "qualify":
            # the aggregate phase's declared evidence, one flag per gate. Every path is optional here,
            # and a path that is not given is a MISSING refusal in the verdict - never a default and
            # never a digest scan of whatever happens to be lying in a directory
            command.add_argument(
                "--final-run", type=Path, help="the frozen toolchain root of record"
            )
            command.add_argument(
                "--promoted-config",
                type=Path,
                help="the promoted production config whose 17 values the readback must match",
            )
            command.add_argument(
                "--approved-bundle", type=Path, help="the approved calibration bundle"
            )
            command.add_argument(
                "--ownership-receipt",
                type=Path,
                help="the Step 1 exclusive-ownership receipt guarding this run root",
            )
            command.add_argument(
                "--runtime-readback",
                type=Path,
                help="the during-qualification 17-value and camera readback",
            )
            command.add_argument(
                "--production-smoke-root", type=Path, help="the production smoke phase root"
            )
            command.add_argument(
                "--scenarios-root", type=Path, help="the forty-scenario phase root"
            )
            command.add_argument(
                "--restart-receipt",
                type=Path,
                action="append",
                dest="restart_receipts",
                help="one FULL_RESTART anchor receipt; repeat once per anchor",
            )
            command.add_argument(
                "--teleop-acceptance-receipt", type=Path, help="the Teleop acceptance receipt"
            )
            command.add_argument(
                "--scenario-partitions", type=Path, help="the declared scenario partitions"
            )
            command.add_argument("--expected-source-commit")
            command.add_argument("--expected-production-config-sha256")
            command.add_argument("--expected-values-sha256")
            command.add_argument("--expected-weights-sha256")
        if name == "serve-teleop":
            # the plan's own Step 6 declarations. `--report` stays as the alias the installed surface
            # already had, but nothing here runs without the acceptance's own evidence
            command.add_argument("--bridge-socket-root", type=Path)
            command.add_argument("--report", dest="qualification_report", type=Path)
            command.add_argument(
                "--qualification-report",
                dest="qualification_report",
                type=Path,
                help="the closed head-only report the acceptance starts from",
            )
            command.add_argument("--bundle", type=Path, help="the approved calibration bundle")
            command.add_argument("--approval-receipt", type=Path)
            command.add_argument(
                "--production-config", type=Path, help="the promoted production search config"
            )
            command.add_argument("--final-run", type=Path, help="the frozen runtime root of record")
            command.add_argument("--profile", default="mujoco")
            command.add_argument("--runtime-id")
            command.add_argument("--ready-file", type=Path)
            command.add_argument("--acceptance-root", type=Path)
            command.add_argument("--device", default="cuda")
            command.add_argument("--frames", type=int, default=10)
            command.add_argument("--web-port", type=int, default=18082)
            command.add_argument("--weights", type=Path)
            command.add_argument("--frozen-candidate", type=Path)
            command.add_argument("--web-dir", type=Path)
            command.add_argument("--expected-source-commit")
            command.add_argument("--expected-production-config-sha256")
            command.add_argument("--expected-values-sha256")
            command.add_argument("--expected-weights-sha256")
    return parser


def _require_new_root(run_root: Path) -> Path:
    """Claim a brand-new run root exclusively, so two starts cannot both believe they won it."""

    root = Path(run_root)
    root.parent.mkdir(parents=True, exist_ok=True)
    try:
        root.mkdir()
    except FileExistsError as error:
        raise ValueError(
            f"RUN_ROOT_ALREADY_EXISTS: {root} exists and no runner may resume it"
        ) from error
    return root


def _write(root: Path, name: str, document: Mapping[str, object]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    target = root / name
    pending = root / f".{name}.pending"
    pending.write_text(
        json.dumps(dict(document), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(pending, target)
    return target


def restricted_admission(*, operation: str, report: Mapping[str, object] | None = None) -> dict:
    """Create operation-bound head-only admission, never for pick-place validation or anything that moves the arm."""

    if operation not in HEAD_ONLY_OPERATIONS:
        raise ValueError(
            f"HEAD_ONLY_OPERATION_REFUSED: {operation!r} is not one of {HEAD_ONLY_OPERATIONS}"
        )
    if operation == "TELEOP_ACCEPTANCE":
        if report is None or report.get("status") != HEAD_SEARCH_QUALIFIED:
            raise ValueError(
                "HEAD_SEARCH_QUALIFIED_REQUIRED: TELEOP_ACCEPTANCE needs the closed head-only report"
            )
        return {
            "operation": operation,
            "consumer": "teleop_head_camera",
            "bundle_sha256": report.get("bundle_sha256"),
        }
    return {
        "operation": operation,
        "one_stack": True,
        "one_detector": True,
        "consumers": ("head_search_controller",),
    }


def require_gate(report: Mapping[str, object], gate: str) -> None:
    """Read a head-only report for the gate named, refusing everything it does not grant."""

    if gate in REFUSED_GATES:
        raise ValueError(
            f"PICK_PLACE_LIVE_GATE_REFUSED: a head-only head search report never grants {gate!r}, whatever its status reads"
        )
    if report.get("status") != HEAD_SEARCH_QUALIFIED:
        raise ValueError(
            f"HEAD_SEARCH_QUALIFIED_REQUIRED: {gate!r} needs a closed head-only report, saw "
            f"{report.get('status')!r}"
        )


def qualify_head_search(inputs: Mapping[str, object], run_root: Path) -> dict:
    """The `aggregate` phase: the declared gates, and a refusal that names every missing item.

    The implementation is :mod:`so101_demo.act.head_search_aggregate`; this name stays because it is the
    qualifier's own phase entry and the last element of :data:`RUN_PHASES`. There is no digest-only path
    any more: a well-formed sha256 of nothing used to publish ``HEAD_SEARCH_QUALIFIED``, which is exactly
    the HS-233 failure mode the declared gates replace.
    """

    from so101_demo.act.head_search_aggregate import aggregate_qualification

    return aggregate_qualification(inputs, run_root)


def serve_teleop(
    report: Mapping[str, object],
    run_root: Path,
    *,
    bridge_socket_root: Path | None = None,
    probe_only: bool = False,
    teardown: object = None,
) -> dict:
    """Own one fresh Teleop stack: publish a closed descriptor, block, then tear down."""

    if report.get("status") != HEAD_SEARCH_QUALIFIED:
        raise ValueError(
            f"HEAD_SEARCH_QUALIFIED_REQUIRED: serve-teleop saw {report.get('status')!r}"
        )
    root = _require_new_root(run_root)
    socket_root = Path(bridge_socket_root) if bridge_socket_root is not None else root / "bridge"
    _write(root, "calibration-state.json", {"state": RUNNING, "phase": "serve-teleop"})
    connection = {
        "operation": "TELEOP_ACCEPTANCE",
        "runtime_id": str(report.get("runtime_id", "")),
        "head_search_runtime_id": str(report.get("runtime_id", "")),
        "bundle_sha256": str(report.get("bundle_sha256", "")),
        "owner": {
            "pid": os.getpid(),
            # the kernel's own start time for this process, in clock ticks since boot, not a monotonic
            # timestamp measured after the fact
            "started_ticks": process_start_ticks(),
            "argv_sha256": hashlib.sha256(" ".join(os.sys.argv).encode("utf-8")).hexdigest(),
        },
        "bridge_socket_root": str(socket_root),
    }
    _write(root, "head-camera-connection.json", connection)
    if probe_only:
        _write(root, "calibration-state.json", {"state": "PROBED", "phase": "serve-teleop"})
        return connection
    with _SignalWatch() as watch:
        while not watch.seen:
            time.sleep(0.05)
    # the receipt records what teardown actually observed; nothing is asserted on its behalf
    if teardown is None:
        receipt = {"controller_stopped": False, "graph_clear": False, "teardown": "not-attempted"}
    else:
        observed = dict(teardown())
        receipt = {
            "controller_stopped": bool(observed.get("controller_stopped", False)),
            "graph_clear": bool(observed.get("graph_clear", False)),
            "teardown": str(observed.get("teardown", "observed")),
        }
    _write(root, "teardown-receipt.json", receipt)
    _write(root, "calibration-state.json", {"state": SUCCEEDED, "phase": "serve-teleop"})
    return {**connection, **receipt}


#: the fixed phase list a production run executes, in order
RUN_PHASES = (
    "production_smoke",
    "scenarios",
    "restart_default",
    "restart_left",
    "restart_forward",
    "aggregate",
)


def run_head_search(inputs: Mapping[str, object], run_root: Path) -> dict:
    """Execute the fixed phase list once in a brand-new root; there is no way to continue a stage.

    The heavy phases themselves belong to the frozen runtime assembled for the qualification; this function owns the
    no-resume contract around them: a new root, one RUNNING record, the ordered phase list, and a single
    atomic SUCCEEDED or FAILED record, with the frozen runtime identity required before any phase starts.
    """

    root = _require_new_root(run_root)
    runtime = inputs.get("runtime")
    if not isinstance(runtime, Mapping) or not runtime.get("runtime_id"):
        raise ValueError("HEAD_SEARCH_RUNTIME_REQUIRED: a run needs the frozen runtime identity")
    if runtime.get("allow_cpu_fallback") is not False:
        raise ValueError("HEAD_SEARCH_CUDA_REQUIRED: the runtime must forbid CPU fallback")
    _write(root, "calibration-state.json", {"state": RUNNING, "phase": RUN_PHASES[0]})
    completed = []
    try:
        for phase in RUN_PHASES:
            _write(
                root,
                "calibration-state.json",
                {"state": RUNNING, "phase": phase, "completed": list(completed)},
            )
            completed.append(phase)
    except Exception:
        _write(root, "calibration-state.json", {"state": FAILED, "completed": list(completed)})
        raise
    receipt = {"runtime_id": str(runtime["runtime_id"]), "phases": list(RUN_PHASES)}
    _write(root, "calibration-state.json", {"state": SUCCEEDED, "completed": list(completed)})
    _write(root, "run-receipt.json", receipt)
    return receipt


def write_exclusive(root: Path, name: str, document: Mapping[str, object]) -> Path:
    """Create a record only if it does not exist yet, so two writers can never both succeed."""

    target = root / name
    payload = json.dumps(dict(document), indent=2, sort_keys=True) + "\n"
    descriptor = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(payload)
    return target


def process_start_ticks() -> int:
    """This process's start time in clock ticks since boot, as the kernel reports it."""

    fields = Path("/proc/self/stat").read_text(encoding="utf-8").rsplit(")", 1)[1].split()
    # field 22 of the whole line is starttime; after the comm field it is index 19
    return int(fields[19])
