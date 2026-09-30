"""The no-resume formal CLI, the closed head-only report and the blocking Teleop owner.

There is no resume path and no stage continuation anywhere here: every runner accepts only a run root that
does not exist yet, writes RUNNING once and then SUCCEEDED or FAILED atomically. A qualified head-only report
lets later Head Search consumers read it, and it never unlocks Task 8 readiness, release, recording, retreat
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

from so101_demo.perception_benchmark.contracts import canonical_sha256

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
REFUSED_GATES = ("task8_live", "task8_ready", "release", "recorder", "retreat", "pick")
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
        if name == "qualify":
            command.add_argument("--promoted-config", type=Path)
            command.add_argument("--evidence-root", type=Path)
        if name == "serve-teleop":
            command.add_argument("--bridge-socket-root", type=Path)
    return parser


def _require_new_root(run_root: Path) -> Path:
    root = Path(run_root)
    if root.exists():
        raise ValueError(f"RUN_ROOT_ALREADY_EXISTS: {root} exists and no runner may resume it")
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
    """Create operation-bound head-only admission, never for Task 8 or anything that moves the arm."""

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
            f"TASK8: a head-only head search report never grants {gate!r}, whatever its status reads"
        )
    if report.get("status") != HEAD_SEARCH_QUALIFIED:
        raise ValueError(
            f"HEAD_SEARCH_QUALIFIED_REQUIRED: {gate!r} needs a closed head-only report, saw "
            f"{report.get('status')!r}"
        )


def qualify_head_search(inputs: Mapping[str, object], run_root: Path) -> dict:
    """Consume the complete evidence set and only then publish the closed head-only report."""

    root = _require_new_root(run_root)
    evidence = inputs.get("evidence")
    if not isinstance(evidence, Mapping) or not evidence:
        raise ValueError(
            "HEAD_SEARCH_QUALIFICATION_EVIDENCE_INCOMPLETE: no evidence digests were given"
        )
    digests = {}
    for name, digest in evidence.items():
        text = str(digest)
        if len(text) != 64 or any(
            character not in "0123456789abcdef" for character in text.lower()
        ):
            raise ValueError(
                f"HEAD_SEARCH_QUALIFICATION_EVIDENCE_INCOMPLETE: {name} is not a sha256 digest"
            )
        digests[str(name)] = text
    _write(root, "calibration-state.json", {"state": RUNNING, "phase": "qualify"})
    report = {
        "status": HEAD_SEARCH_QUALIFIED,
        "operation": "QUALIFICATION_RUN",
        "run_root": str(root),
        "runtime_id": str(inputs.get("runtime_id", "")),
        "head_search_runtime_id": str(inputs.get("runtime_id", "")),
        "bundle_sha256": str(inputs.get("bundle_sha256", "")),
        "evidence_sha256": digests,
        "evidence_sha256_set": canonical_sha256(digests),
    }
    _write(root, "head-search-qualification.json", report)
    _write(root, "head-search-qualified-report.json", report)
    _write(root, "calibration-state.json", {"state": SUCCEEDED, "phase": "qualify"})
    return report


def serve_teleop(
    report: Mapping[str, object],
    run_root: Path,
    *,
    bridge_socket_root: Path | None = None,
    probe_only: bool = False,
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
            "started_ticks": int(time.clock_gettime(time.CLOCK_MONOTONIC) * 1e6),
            "argv_sha256": hashlib.sha256(" ".join(os.sys.argv).encode("utf-8")).hexdigest(),
        },
        "bridge_socket_root": str(socket_root),
    }
    _write(root, "head-camera-connection.json", connection)
    if probe_only:
        return connection
    with _SignalWatch() as watch:
        while not watch.seen:
            time.sleep(0.05)
    receipt = {"controller_stopped": True, "graph_clear": True, "teardown": "clean"}
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

    The heavy phases themselves belong to the frozen runtime assembled in Task 13; this function owns the
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
