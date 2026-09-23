#!/usr/bin/env python3
"""L2 fixed-mode helper: a real OS process playing the coordinator boundary.

It uses the upstream CoordinatorJournal writer, the upstream fixed control
endpoint, and the upstream sealed-attempt layout, so every Web-side read goes
through production verification.  It never claims robot, physics, or
perception truth; every produced attempt is an initial-gate business FAILED
declared by the spec file.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import threading
import time

for _entry in os.environ.get("AMENT_PREFIX_PATH", "").split(os.pathsep):
    _site = Path(_entry) / "lib" / "python3.12" / "site-packages"
    if _site.is_dir() and str(_site) not in sys.path:
        sys.path.insert(0, str(_site))

from so101_demo.parallel_batch.artifacts import verify_attempt
from so101_demo.parallel_batch.contracts import (
    AttemptIdentity,
    BatchKindV2,
    BatchRequestV2,
    RunMode,
)
from so101_demo.parallel_batch.journal import CoordinatorJournal
from so101_demo.parallel_batch.web_control import FixedCoordinatorControlServer

_MARKER = "e2e-test-execution-port-v1"


def _json_bytes(document) -> bytes:
    return json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(tmp, path)
    directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


class _HelperCoordinator:
    """Minimal in-process coordinator state owned by the control endpoint."""

    def __init__(self, request: BatchRequestV2, journal: CoordinatorJournal) -> None:
        self.request = request
        self.journal = journal
        self.terminal_reason: str | None = None
        self.cleanup_complete = False
        self._stopped = threading.Event()

    @property
    def stopped(self) -> threading.Event:
        return self._stopped

    def request_stop(self, reason: str):
        self.journal.append(
            "BATCH_STOPPING",
            f"stop-{reason}",
            {"delta": {"terminal_reason": reason}},
        )
        self.terminal_reason = reason
        self._stopped.set()
        return self.snapshot()

    def snapshot(self):
        summary = type(
            "Summary",
            (),
            {
                "batch_terminal": self.terminal_reason is not None,
                "batch_cleanup_complete": self.cleanup_complete,
            },
        )()
        return type(
            "Snapshot",
            (),
            {"summary": summary, "terminal_reason": self.terminal_reason},
        )()


def _seal_failed_attempt(
    batch_root: Path,
    identity: AttemptIdentity,
    *,
    simulation_session_id: str,
    reason: str,
) -> tuple[Path, str]:
    sealed = (
        batch_root / "workers" / identity.worker_id / "attempts"
        / identity.point_id / identity.attempt_id / "sealed"
    )
    sealed.mkdir(parents=True, exist_ok=False)
    pid, pgid = os.getpid(), os.getpgrp()
    source_stamp = {"simulation_session_id": simulation_session_id}
    identity_document = asdict(identity)
    shared = {
        "identity": identity_document,
        "run_mode": "execute",
        "worker_slot": identity.worker_id,
        "reset_epoch": "reset-1",
        "source_stamp": source_stamp,
    }
    (sealed / "perception" / "input").mkdir(parents=True)
    (sealed / "perception" / "input" / "rgb.npy").write_bytes(b"\x93NUMPY-e2e-helper\n")
    (sealed / "initial-rgb.png").write_bytes(
        bytes.fromhex(
            "89504e470d0a1a0a0000000d4948445200000001000000010806"
            "0000001f15c4890000000d49444154789c62606360f00f00000301"
            "0100c9fe92ef0000000049454e44ae426082"
        )
    )
    _atomic_write(
        sealed / "attempt-result.json",
        _json_bytes({"status": "FAILED", "reason": reason}) + b"\n",
    )
    _atomic_write(
        sealed / "workspace_identity.json",
        _json_bytes({**shared, "producer_pid": pid, "producer_pgid": pgid}) + b"\n",
    )
    files = []
    directories = []
    for path in sorted(sealed.rglob("*")):
        relative = path.relative_to(sealed).as_posix()
        if path.is_dir():
            directories.append(relative)
        else:
            payload = path.read_bytes()
            files.append({
                "relative_path": relative,
                "size": len(payload),
                "sha256": _sha256_bytes(payload),
                "producer_pid": pid,
                "producer_pgid": pgid,
            })
    required = sorted({
        "workspace_identity.json", "attempt-result.json",
        "initial-rgb.png", "perception/input/rgb.npy",
    })
    manifest = {
        **shared,
        "schema_version": 1,
        "producer_pid": pid,
        "producer_pgid": pgid,
        "files": files,
        "directories": directories,
        "tree_sha256": _sha256_bytes(_json_bytes({"files": files, "directories": directories})),
        "required": required,
        "status": "FAILED",
        "evidence_stage": "INITIAL_GATE_COMPLETE",
        "qualification": _MARKER,
    }
    payload = _json_bytes(manifest) + b"\n"
    _atomic_write(sealed / "attempt_result_manifest.json", payload)
    verify_attempt(sealed, identity)
    return sealed, _sha256_bytes(payload)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--batch-root", required=True, type=Path)
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--worker-count", required=True, type=int)
    parser.add_argument("--point-id", action="append", default=[])
    return parser.parse_args(argv)


def _canonical_first_pass(args: argparse.Namespace, spec: dict, batch_root: Path) -> int:
    """Publish the current campaign contract for retry acceptance tests.

    The binding comes from the service's already committed campaign and manifest. The helper
    supplies failed business results but cannot invent the selection that admitted the campaign.
    Retry batches continue through the legacy helper below so the two layouts are exercised.
    """

    store_path = batch_root.parents[2] / "validation-service" / "supervisor.sqlite3"
    with sqlite3.connect(f"file:{store_path}?mode=ro", uri=True) as store:
        row = store.execute(
            "SELECT c.execution_config_sha256, m.canonical_json FROM campaigns c "
            "JOIN manifests m ON m.manifest_id = c.manifest_id WHERE c.campaign_id = ?",
            (args.campaign_id,),
        ).fetchone()
    if row is None:
        raise RuntimeError("HELPER_CAMPAIGN_BINDING_MISSING")
    config_sha256, manifest_json = row
    manifest = json.loads(manifest_json)
    points = list(args.point_id)
    if points != manifest["point_ids"]:
        raise RuntimeError("HELPER_SELECTION_MISMATCH")
    binding = {
        "batch_id": args.batch_id,
        "campaign_id": args.campaign_id,
        "catalog_sha256": manifest["catalog_sha256"],
        "selected_point_ids": points,
        "binding": {
            "batch_id": args.batch_id,
            "campaign_id": args.campaign_id,
            "kind": "FIRST_PASS",
            "catalog_sha256": manifest["catalog_sha256"],
            "selection_sha256": manifest["selection_sha256"],
            "config_sha256": config_sha256,
            "selected_point_ids": points,
        },
    }
    _atomic_write(batch_root / "selection-binding.json", _json_bytes(binding) + b"\n")
    (batch_root / "point-results").mkdir()

    journal = CoordinatorJournal.create(batch_root / "journal", args.batch_id)
    coordinator = _HelperCoordinator(
        BatchRequestV2(
            batch_id=args.batch_id, run_mode=RunMode.EXECUTE,
            selected_point_ids=tuple(points), worker_count=args.worker_count,
            evidence_root=batch_root, batch_kind=BatchKindV2.FIRST_PASS,
        ),
        journal,
    )
    socket_path = Path(os.environ["SO101_FIXED_CONTROL_SOCKET"])
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(socket_path.parent, 0o700)
    control = FixedCoordinatorControlServer(
        coordinator=coordinator,
        campaign_id=os.environ["SO101_FIXED_CONTROL_CAMPAIGN_ID"],
        control_token=os.environ.get("SO101_FIXED_CONTROL_TOKEN", ""),
        path=socket_path,
    )
    control.start()
    try:
        journal.append_committed(
            "CAMPAIGN_STARTED", f"{args.campaign_id}/CAMPAIGN_STARTED",
            {"campaign_id": args.campaign_id, "batch_id": args.batch_id,
             "schema_version": journal.schema_version},
        )
        for index, point_id in enumerate(points):
            worker_id = f"worker-{index % args.worker_count + 1:02d}"
            attempt_id = f"attempt-{index + 1:03d}"
            slot_id = f"slot-{index % args.worker_count}"
            identity = AttemptIdentity(
                batch_id=args.batch_id, coordinator_epoch=journal.coordinator_epoch,
                worker_id=worker_id, worker_generation=1, point_id=point_id,
                attempt_id=attempt_id, lease_generation=1,
            )
            common = {
                "point_id": point_id, "attempt_id": attempt_id,
                "worker_id": worker_id, "slot_id": slot_id, "generation": 1,
            }
            journal.append_committed(
                "POINT_LEASED", f"{args.batch_id}/POINT_LEASED/{attempt_id}",
                {**common, "selection_sha256": manifest["selection_sha256"]},
            )
            journal.append_committed(
                "WORKER_REGISTERED", f"{args.batch_id}/WORKER_REGISTERED/{attempt_id}",
                common,
            )
            journal.append_committed(
                "ATTEMPT_STARTED", f"{args.batch_id}/ATTEMPT_STARTED/{attempt_id}",
                common,
            )
            time.sleep(float(spec.get("per_point_delay_s", 0.05)))
            outcome = spec.get("points", {}).get(point_id, {}).get("outcome", "FAILED")
            if outcome != "FAILED":
                raise RuntimeError("HELPER_ONLY_PRODUCES_BUSINESS_FAILED")
            reason = spec.get("points", {}).get(point_id, {}).get(
                "reason", "TARGET_TOLERANCE_EXCEEDED"
            )
            sealed, manifest_sha = _seal_failed_attempt(
                batch_root, identity,
                simulation_session_id=f"e2e-helper-{args.batch_id}", reason=reason,
            )
            result_sha256 = _sha256_bytes((sealed / "attempt-result.json").read_bytes())
            _atomic_write(
                batch_root / "point-results" / f"{point_id}.json",
                _json_bytes({
                    "committed": True, "point_id": point_id, "attempt_id": attempt_id,
                    "outcome": outcome,
                    "lease_identity": [args.campaign_id, args.batch_id, point_id,
                                       attempt_id, 1, worker_id],
                    "evidence_manifest_sha256": manifest_sha,
                }) + b"\n",
            )
            journal.append_committed(
                "RESULT_COMMITTED", f"{args.batch_id}/RESULT_COMMITTED/{attempt_id}",
                {**common, "outcome": outcome,
                 "evidence_manifest_sha256": manifest_sha},
            )
            journal.append_committed(
                "POINT_TERMINAL", f"{args.batch_id}/POINT_TERMINAL/{point_id}",
                {"point_id": point_id, "attempt_id": attempt_id, "outcome": outcome,
                 "state": "COMMITTED", "result_sha256": result_sha256},
            )
        journal.append_committed(
            "BATCH_TERMINAL", f"{args.batch_id}/BATCH_TERMINAL",
            {"outcome": "N1_CAMPAIGN_INCOMPLETE"},
        )
        journal.append_committed(
            "CLEANUP_COMMITTED", f"{args.batch_id}/CLEANUP_COMMITTED",
            {"cleanup_complete": True},
        )
        coordinator.cleanup_complete = True
        _atomic_write(
            batch_root / "cleanup-gates.json",
            _json_bytes({"batch_id": args.batch_id, "owned_descendants_gone": True,
                         "qualification": _MARKER}) + b"\n",
        )
        return 0
    finally:
        control.close()
        journal.close()


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    batch_root = args.batch_root
    batch_root.mkdir(parents=False, exist_ok=False)

    if spec.get("canonical_first_pass") and not args.batch_id.startswith("retry-"):
        return _canonical_first_pass(args, spec, batch_root)

    journal = CoordinatorJournal.create(batch_root / "coordinator", args.batch_id)
    coordinator = _HelperCoordinator(
        BatchRequestV2(
            batch_id=args.batch_id,
            run_mode=RunMode.EXECUTE,
            selected_point_ids=tuple(args.point_id),
            worker_count=args.worker_count,
            evidence_root=batch_root,
            batch_kind=BatchKindV2.FIRST_PASS,
        ),
        journal,
    )

    token = os.environ.get("SO101_FIXED_CONTROL_TOKEN", "")
    socket_path = Path(os.environ.get("SO101_FIXED_CONTROL_SOCKET", ""))
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(socket_path.parent, 0o700)
    control = FixedCoordinatorControlServer(
        coordinator=coordinator,
        campaign_id=os.environ["SO101_FIXED_CONTROL_CAMPAIGN_ID"],
        control_token=token,
        path=socket_path,
    )
    control.start()

    points = list(args.point_id)
    workers = [f"worker-{index + 1:02d}" for index in range(args.worker_count)]
    journal.append(
        "BATCH_STARTED",
        "batch-started",
        {
            "delta": {
                "points": {
                    point_id: {"status": "UNRUN", "attempts": 0, "terminal": False}
                    for point_id in points
                },
                "workers": {
                    worker_id: {"generation": 1, "state": "READY", "lease_count": 0}
                    for worker_id in workers
                },
                "broker_healthy": True,
            },
            "batch": {
                "batch_id": args.batch_id,
                "campaign_id": args.campaign_id,
                "worker_count": args.worker_count,
                "point_ids": points,
                "run_mode": "execute",
                "qualification": _MARKER,
            },
        },
    )

    def run_points() -> None:
        leases = {worker_id: 0 for worker_id in workers}
        for index, point_id in enumerate(points):
            if coordinator.stopped.is_set():
                break
            worker_id = workers[index % len(workers)]
            leases[worker_id] += 1
            attempt_id = f"attempt-{index + 1:03d}"
            identity = AttemptIdentity(
                batch_id=args.batch_id,
                coordinator_epoch=journal.coordinator_epoch,
                worker_id=worker_id,
                worker_generation=1,
                point_id=point_id,
                attempt_id=attempt_id,
                lease_generation=leases[worker_id],
            )
            journal.append(
                "LEASE_GRANTED",
                f"lease-{point_id}",
                {
                    "delta": {
                        "workers": {
                            worker_id: {
                                "state": "EXECUTING",
                                "lease_count": leases[worker_id],
                                "lease": {"point_id": point_id, "attempt_id": attempt_id},
                            }
                        },
                        "points": {point_id: {"active_attempt": attempt_id}},
                    }
                },
            )
            journal.append(
                "ATTEMPT_STARTED",
                f"attempt-started-{point_id}",
                {"identity": asdict(identity)},
            )
            time.sleep(float(spec.get("per_point_delay_s", 0.05)))
            outcome = spec.get("points", {}).get(point_id, {}).get("outcome", "FAILED")
            reason = spec.get("points", {}).get(point_id, {}).get(
                "reason", "TARGET_TOLERANCE_EXCEEDED"
            )
            if outcome != "FAILED":
                raise RuntimeError("HELPER_ONLY_PRODUCES_BUSINESS_FAILED")
            sealed, manifest_sha = _seal_failed_attempt(
                batch_root,
                identity,
                simulation_session_id=f"e2e-helper-{args.batch_id}",
                reason=reason,
            )
            identity_document = asdict(identity)
            location = str(sealed)
            tamper = spec.get("tamper") if index == 0 else None
            if tamper == "sha256":
                target = sealed / "initial-rgb.png"
                target.write_bytes(target.read_bytes() + b"tampered")
            elif tamper == "symlink":
                manifest_file = sealed / "attempt_result_manifest.json"
                manifest_file.unlink()
                os.symlink("/etc/hostname", manifest_file)
            elif tamper == "identity":
                identity_document = {**identity_document, "attempt_id": "attempt-999"}
            elif tamper == "escape":
                location = str(batch_root.parent / "outside-sealed")
            elif tamper is not None:
                raise RuntimeError("HELPER_TAMPER_MODE_UNKNOWN")
            journal.append(
                "RESULT_COMMITTED",
                f"result-{point_id}",
                {
                    "identity": {**identity_document, "location": location},
                    "response": {
                        "location": location,
                        "sha256": manifest_sha,
                        "status": "FAILED",
                    },
                    "delta": {
                        "points": {
                            point_id: {
                                "status": "FAILED",
                                "attempts": 1,
                                "terminal": True,
                                "active_attempt": None,
                                "blocked_by": reason,
                            }
                        },
                        "workers": {
                            worker_id: {"state": "READY", "lease": None}
                        },
                    },
                },
            )

    def finalize_cleanup() -> None:
        coordinator.cleanup_complete = True
        _atomic_write(
            batch_root / "cleanup-gates.json",
            _json_bytes({
                "batch_id": args.batch_id,
                "owned_descendants_gone": True,
                "qualification": _MARKER,
            }) + b"\n",
        )
        journal.append(
            "BATCH_FINISHED",
            "batch-finished",
            {"delta": {"batch_cleanup_complete": True}},
        )

    try:
        if spec.get("descendant_mode") == "survive":
            descendant = subprocess.Popen(
                [sys.executable, str(Path(__file__).parent / "descendant_helper.py")],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            print(f"descendant_pid={descendant.pid}", flush=True)
            return 0
        run_points()
        stopped = coordinator.stopped.is_set()
        if stopped:
            remaining = {
                point_id: {"status": "UNRUN", "terminal": True, "active_attempt": None}
                for point_id in points
            }
            journal.append(
                "CANCEL_RECONCILED",
                "cancel-reconciled",
                {"delta": {"points": remaining}},
            )
        terminal_reason = coordinator.terminal_reason or "POINTS_COMPLETE"
        journal.append(
            "BATCH_TERMINAL",
            "batch-terminal",
            {"delta": {"terminal_reason": terminal_reason}},
        )
        stop_after = spec.get("stop_after")
        if spec.get("stop_after_scope") == "retry" and not args.batch_id.startswith("retry-"):
            stop_after = None
        if stop_after == "terminal-before-cleanup":
            return 0
        finalize_cleanup()
        return 0
    finally:
        control.close()
        journal.close()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
