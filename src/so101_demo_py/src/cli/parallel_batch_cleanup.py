"""Exact, idempotent cleanup for one adaptive batch runtime root."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
import time

from so101_demo.parallel_batch.adaptive_pool import adaptive_socket_paths
from so101_demo.parallel_batch.journal import CoordinatorJournal
from so101_demo.parallel_batch.resources import (
    ResourceAllocationError,
    SystemResourceProbe,
)
from so101_demo.runtime.parallel_processes import ProcessSupervisor


class CleanupError(RuntimeError):
    """Cleanup could not prove that only the requested batch was retired."""


_PROC_SCAN_QUIESCENCE_ATTEMPTS = 601
_PROC_SCAN_QUIESCENCE_INTERVAL_S = 0.05
_TRANSIENT_PROC_SCAN_BOUNDARIES = (
    "PROC_IDENTITY_UNVERIFIABLE:",
    "PROC_METADATA_UNVERIFIABLE:",
    "PROC_ENV_UNVERIFIABLE:",
    "PROC_CLASSIFICATION_UNVERIFIABLE:",
    "PROC_IDENTITY_CHANGED:",
)


def _ros_domain_in_use_after_quiescence(
    probe: SystemResourceProbe, domain_id: int
) -> bool:
    """Rescan bounded transient process-table races before releasing a claim."""

    for attempt in range(_PROC_SCAN_QUIESCENCE_ATTEMPTS):
        try:
            return probe.ros_domain_in_use(domain_id)
        except ResourceAllocationError as error:
            transient = str(error).startswith(_TRANSIENT_PROC_SCAN_BOUNDARIES)
            if not transient or attempt + 1 >= _PROC_SCAN_QUIESCENCE_ATTEMPTS:
                raise
            time.sleep(_PROC_SCAN_QUIESCENCE_INTERVAL_S)
    raise AssertionError("unreachable process scan retry loop")


def _read_json(path: Path, label: str):
    descriptor = -1
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        identity = os.fstat(descriptor)
        payload = os.read(descriptor, 1024 * 1024 + 1)
        if len(payload) > 1024 * 1024:
            raise ValueError("oversized document")
        document = json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CleanupError(f"{label}_READ") from error
    except ValueError as error:
        raise CleanupError(f"{label}_READ") from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if (
        not stat.S_ISREG(identity.st_mode)
        or identity.st_uid != os.getuid()
        or type(document) is not dict
    ):
        raise CleanupError(f"{label}_IDENTITY")
    return document


def _write_receipt(path: Path, document: dict[str, object]) -> None:
    payload = json.dumps(
        document, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    try:
        existing = _read_json(path, "CLEANUP_RECEIPT")
    except CleanupError:
        if os.path.lexists(path):
            raise
    else:
        if existing != document:
            raise CleanupError("CLEANUP_RECEIPT_CONFLICT")
        return
    descriptor, temporary = tempfile.mkstemp(
        prefix=".cleanup-receipt-", dir=path.parent
    )
    try:
        os.fchmod(descriptor, 0o600)
        os.write(descriptor, payload)
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary, path)
        parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(parent)
        finally:
            os.close(parent)
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _active_pool(runtime_root: Path):
    journal_root = runtime_root / "journal"
    if not os.path.lexists(journal_root):
        return None
    identity = journal_root.lstat()
    if not stat.S_ISDIR(identity.st_mode) or identity.st_uid != os.getuid():
        raise CleanupError("TOP_JOURNAL_IDENTITY")
    journal = CoordinatorJournal(journal_root, runtime_root.name)
    try:
        events, _terminal, _epoch, tail = journal._read_history()
    except Exception as error:
        raise CleanupError("TOP_JOURNAL_INVALID") from error
    if tail:
        raise CleanupError("TOP_JOURNAL_TORN")
    starts = [event for event in events if event.type == "POOL_STARTING"]
    if not starts:
        return None
    payload = starts[-1].payload
    generation = payload.get("generation")
    worker_count = payload.get("worker_count")
    if (
        type(generation) is not int
        or generation <= 0
        or type(worker_count) is not int
        or not 1 <= worker_count <= 16
    ):
        raise CleanupError("ACTIVE_POOL_IDENTITY")
    return generation, worker_count


def _retire_processes(pool_root: Path, pool_batch_id: str) -> None:
    manifest_path = pool_root / "owned-processes.json"
    if not os.path.lexists(manifest_path):
        return
    document = _read_json(manifest_path, "PROCESS_MANIFEST")
    supervisor = ProcessSupervisor(pool_batch_id, manifest_path=manifest_path)
    try:
        retired = supervisor.retire_manifest(document)
    except Exception as error:
        raise CleanupError("PROCESS_RETIREMENT_FAILED") from error
    if retired is not True:
        raise CleanupError("PROCESS_RETIREMENT_FAILED")


def _retire_container(pool_root: Path, pool_batch_id: str) -> None:
    broker_root = pool_root / "ipc/broker"
    cid_path = broker_root / "container.cid"
    if not os.path.lexists(cid_path):
        return
    descriptor = os.open(cid_path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        identity = os.fstat(descriptor)
        if not stat.S_ISREG(identity.st_mode) or identity.st_uid != os.getuid():
            raise CleanupError("CONTAINER_IDENTITY")
        container_id = os.read(descriptor, 66).decode("ascii").strip()
    finally:
        os.close(descriptor)
    if re.fullmatch(r"[0-9a-f]{64}", container_id) is None:
        raise CleanupError("CONTAINER_ID")
    inspected = subprocess.run(
        ["docker", "inspect", "--type", "container", container_id],
        check=False,
        capture_output=True,
        text=True,
        timeout=10.0,
    )
    if inspected.returncode != 0:
        if "No such object" in inspected.stderr or "No such container" in inspected.stderr:
            return
        raise CleanupError("CONTAINER_INSPECT")
    try:
        documents = json.loads(inspected.stdout)
        container = documents[0]
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as error:
        raise CleanupError("CONTAINER_INSPECT") from error
    labels = container.get("Config", {}).get("Labels", {})
    mounts = {
        (item.get("Source"), item.get("Destination"))
        for item in container.get("Mounts", ())
        if type(item) is dict
    }
    if (
        container.get("Id") != container_id
        or labels.get("com.so101.batch-id") != pool_batch_id
        or (str(broker_root), "/runtime") not in mounts
    ):
        raise CleanupError("CONTAINER_IDENTITY")
    stopped = subprocess.run(
        ["docker", "stop", "--timeout", "5", container_id],
        check=False,
        capture_output=True,
        text=True,
        timeout=10.0,
    )
    if stopped.returncode != 0:
        raise CleanupError("CONTAINER_STOP")
    verified = subprocess.run(
        ["docker", "inspect", "--type", "container", container_id],
        check=False,
        capture_output=True,
        text=True,
        timeout=10.0,
    )
    if verified.returncode != 0:
        if "No such object" in verified.stderr or "No such container" in verified.stderr:
            return
        raise CleanupError("CONTAINER_READBACK")
    try:
        document = json.loads(verified.stdout)[0]
        stopped_and_owned = (
            document.get("Id") == container_id
            and document.get("Config", {}).get("Labels", {}).get(
                "com.so101.batch-id"
            ) == pool_batch_id
            and document.get("State", {}).get("Running") is False
        )
    except (IndexError, TypeError, json.JSONDecodeError) as error:
        raise CleanupError("CONTAINER_READBACK") from error
    if not stopped_and_owned:
        raise CleanupError("CONTAINER_READBACK")


def _remove_sockets(pool_root: Path, worker_count: int) -> None:
    for path in adaptive_socket_paths(pool_root, worker_count):
        try:
            identity = path.lstat()
        except FileNotFoundError:
            continue
        if not stat.S_ISSOCK(identity.st_mode) or identity.st_uid != os.getuid():
            raise CleanupError("SOCKET_IDENTITY")
        path.unlink()


def _release_claims(pool_root: Path, pool_batch_id: str) -> tuple[int, ...]:
    manifest_path = pool_root / "resource_manifest.json"
    if not os.path.lexists(manifest_path):
        return ()
    manifest = _read_json(manifest_path, "RESOURCE_MANIFEST")
    claims = manifest.get("domain_claims")
    workers = manifest.get("workers")
    if not isinstance(claims, list) or not isinstance(workers, list):
        raise CleanupError("RESOURCE_MANIFEST_SCHEMA")
    probe = SystemResourceProbe()
    released = []
    for worker in workers:
        domain_id = worker.get("ros_domain_id")
        if type(domain_id) is not int or _ros_domain_in_use_after_quiescence(
            probe, domain_id
        ):
            raise CleanupError("ROS_DOMAIN_ACTIVE")
    for claim in claims:
        if type(claim) is not dict:
            raise CleanupError("DOMAIN_CLAIM_SCHEMA")
        domain_id = claim.get("domain_id")
        path = Path(claim.get("claim_path", ""))
        if (
            type(domain_id) is not int
            or not path.is_absolute()
            or claim.get("batch_id") != pool_batch_id
            or claim.get("evidence_root") != str(pool_root)
        ):
            raise CleanupError("DOMAIN_CLAIM_IDENTITY")
        descriptor = os.open(path, os.O_RDWR | os.O_NOFOLLOW)
        try:
            identity = os.fstat(descriptor)
            if (
                not stat.S_ISREG(identity.st_mode)
                or identity.st_uid != os.getuid()
                or stat.S_IMODE(identity.st_mode) & 0o077
            ):
                raise CleanupError("DOMAIN_CLAIM_FILE_IDENTITY")
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            payload = os.read(descriptor, 8193)
            if len(payload) > 8192:
                raise CleanupError("DOMAIN_CLAIM_OVERSIZED")
            current = json.loads(payload.decode("utf-8"))
            if type(current) is not dict or any(
                current.get(name) != claim.get(name)
                for name in (
                    "protocol", "scope", "domain_id", "uid", "batch_id",
                    "evidence_root", "claim_path", "generation",
                )
            ):
                raise CleanupError("DOMAIN_CLAIM_CHANGED")
            if current.get("claim_state") == "RELEASED":
                if current.get("cleanup_verified") is not True:
                    raise CleanupError("DOMAIN_CLAIM_RELEASE_UNVERIFIED")
                released.append(domain_id)
                continue
            if current.get("claim_state") != "ACTIVE":
                raise CleanupError("DOMAIN_CLAIM_CHANGED")
            current.update(claim_state="RELEASED", cleanup_verified=True)
            payload = (
                json.dumps(current, sort_keys=True, separators=(",", ":")) + "\n"
            ).encode("utf-8")
            os.lseek(descriptor, 0, os.SEEK_SET)
            os.ftruncate(descriptor, 0)
            os.write(descriptor, payload)
            os.fsync(descriptor)
            released.append(domain_id)
        finally:
            os.close(descriptor)
    return tuple(released)


def cleanup_runtime(runtime_root: Path) -> dict[str, object]:
    root = Path(runtime_root)
    if (
        not root.is_absolute()
        or not root.is_dir()
        or root.is_symlink()
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,4}", root.name) is None
    ):
        raise CleanupError("RUNTIME_ROOT")
    receipt_path = root / "cleanup-receipt.json"
    active = _active_pool(root)
    if active is None:
        receipt = {
            "schema_version": 1,
            "runtime_root": str(root),
            "active_generation": None,
            "worker_count": 0,
            "released_domain_ids": [],
            "cleanup_complete": True,
        }
        _write_receipt(receipt_path, receipt)
        return receipt
    generation, worker_count = active
    pool_batch_id = f"{root.name}-g{generation:02d}-w{worker_count:02d}"
    pool_root = root / f"p/g{generation:02d}w{worker_count:02d}"
    if not pool_root.is_dir() or pool_root.is_symlink():
        # A pool that failed before it allocated anything wrote only its failure marker.  There is
        # nothing to retire, and refusing here (the old POOL_ROOT error) left the campaign stuck in
        # CLEANING_UP forever because cleanup never produced a receipt.  The marker stays on disk.
        if not (root / f"p/g{generation:02d}w{worker_count:02d}-failure.json").is_file():
            raise CleanupError("POOL_ROOT")
        receipt = {
            "schema_version": 1,
            "runtime_root": str(root),
            "active_generation": generation,
            "worker_count": 0,
            "released_domain_ids": [],
            "cleanup_complete": True,
            "pool_failure": f"p/g{generation:02d}w{worker_count:02d}-failure.json",
        }
        _write_receipt(receipt_path, receipt)
        return receipt
    _retire_processes(pool_root, pool_batch_id)
    _retire_container(pool_root, pool_batch_id)
    _remove_sockets(pool_root, worker_count)
    released = _release_claims(pool_root, pool_batch_id)
    receipt = {
        "schema_version": 1,
        "runtime_root": str(root),
        "active_generation": generation,
        "worker_count": worker_count,
        "released_domain_ids": list(released),
        "cleanup_complete": True,
    }
    _write_receipt(receipt_path, receipt)
    return receipt


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="so101_parallel_batch_cleanup")
    parser.add_argument("--runtime-root", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        receipt = cleanup_runtime(args.runtime_root)
        print(json.dumps(receipt, sort_keys=True))
        return 0
    except (CleanupError, OSError, ValueError, subprocess.SubprocessError) as error:
        print(
            json.dumps({"status": "ERROR", "message": str(error)}, sort_keys=True),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
