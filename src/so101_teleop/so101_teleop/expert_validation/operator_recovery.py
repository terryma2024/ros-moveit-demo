"""Offline operator recovery. It observes runtime; it never kills or claims success."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import subprocess
import sys
import time

import yaml

from .models import _identifier
from .store import StoreConflict, SupervisorStore, _json


class RecoveryError(RuntimeError):
    """The absence of a runtime side effect could not be proved."""


def _containers(batch_id):
    result = subprocess.run(
        ["docker", "ps", "--no-trunc", "--filter", f"label=com.so101.batch-id={batch_id}",
         "--format", "{{.ID}}"], capture_output=True, text=True, timeout=10, check=True,
    )
    identifiers = result.stdout.split()
    if any(re.fullmatch(r"[0-9a-f]{64}", value) is None for value in identifiers):
        raise RecoveryError("RECOVERY_CONTAINER_INVENTORY_INVALID")
    return identifiers


def _domain_in_use(domain):
    from so101_demo.parallel_batch.resources import SystemResourceProbe
    return SystemResourceProbe().ros_domain_in_use(domain)


class RuntimeInspector:
    def __init__(self, *, proc_root=Path("/proc"), container_probe=_containers,
                 domain_probe=_domain_in_use):
        self.proc_root = Path(proc_root)
        self.container_probe = container_probe
        self.domain_probe = domain_probe

    def inspect(self, owners, domains, batch_ids):
        if not self.proc_root.is_dir():
            raise RecoveryError("RECOVERY_PROC_UNAVAILABLE")
        leaders = sorted({value for owner in owners for value in (owner["pid"], owner["runner_pid"])
                          if value is not None})
        groups = sorted({owner["pgid"] for owner in owners})
        for pid in leaders:
            if os.path.lexists(self.proc_root / str(pid)):
                # Also reject PID reuse: absence, not a guessed identity, is required.
                raise RecoveryError("RECOVERY_LEADER_PRESENT")
        for process in self.proc_root.iterdir():
            if not process.name.isdigit():
                continue
            try:
                document = (process / "stat").read_text()
                fields = document[document.rfind(")") + 2:].split()
                if int(fields[2]) in groups:
                    raise RecoveryError("RECOVERY_PROCESS_GROUP_PRESENT")
            except (FileNotFoundError, ProcessLookupError):
                if os.path.lexists(process):
                    raise RecoveryError("RECOVERY_PROC_UNVERIFIABLE")
            except (OSError, ValueError, IndexError) as error:
                raise RecoveryError("RECOVERY_PROC_UNVERIFIABLE") from error
        for batch_id in batch_ids:
            if self.container_probe(batch_id):
                raise RecoveryError("RECOVERY_CONTAINER_PRESENT")
        for domain in domains:
            # Reject non-boolean/unknown results, not just a truthy known claim.
            if self.domain_probe(domain) is not False:
                raise RecoveryError("RECOVERY_DOMAIN_NOT_CLEAR")
        return {"leaders_absent": leaders, "process_groups_absent": groups,
                "containers_absent_for_batches": list(batch_ids), "domains_clear": list(domains)}


def _write_private(path, data):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "wb") as output:
        output.write(data)
        output.flush()
        os.fsync(output.fileno())
    _sync_directory(path.parent)


def _sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _private_directory(path):
    path.mkdir(mode=0o700, exist_ok=True)
    metadata = path.stat(follow_symlinks=False)
    if (path.is_symlink() or not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) != 0o700):
        raise RecoveryError("RECOVERY_OUTPUT_NOT_PRIVATE")


def recover(*, store, campaign_id, command_id, parallel_config, inspector=None,
            source_commit, apply=False):
    _identifier("campaign_id", campaign_id)
    _identifier("command_id", command_id)
    if not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        raise RecoveryError("RECOVERY_SOURCE_COMMIT_INVALID")
    context = store.operator_recovery_context(campaign_id)
    if context["campaign"]["execution_mode"] not in {"SEQUENTIAL", "PARALLEL"}:
        raise RecoveryError("RECOVERY_MODE_UNSUPPORTED")
    config = Path(parallel_config)
    if not config.is_absolute() or config != config.resolve(strict=True):
        raise RecoveryError("RECOVERY_CONFIG_PATH_INVALID")
    config_bytes = config.read_bytes()
    config_sha = hashlib.sha256(config_bytes).hexdigest()
    if config_sha != context["preflight"].get("parallel_config_sha256"):
        raise RecoveryError("RECOVERY_CONFIG_MISMATCH")
    document = yaml.safe_load(config_bytes)
    domains = document.get("ros_domain_ids") if isinstance(document, dict) else None
    if (not isinstance(domains, list) or not domains or len(set(domains)) != len(domains)
            or any(type(domain) is not int or not 0 <= domain <= 232 for domain in domains)):
        raise RecoveryError("RECOVERY_DOMAIN_SCOPE_INVALID")
    previous = store.operator_recovery(campaign_id)
    if previous is not None:
        if previous["command_id"] != command_id:
            raise StoreConflict("RECOVERY_ALREADY_RESOLVED")
        return previous
    owners = context["owners"]
    batch_ids = [batch["batch_id"] for batch in context["batches"]]
    if (not owners or {owner["batch_id"] for owner in owners} != set(batch_ids)
            or any(owner["state"] != "RUNNING" or any(
            type(owner[name]) is not int or owner[name] <= 0 for name in ("pid", "pgid", "started_ticks")
    ) for owner in owners)):
        raise RecoveryError("RECOVERY_OWNER_UNACKNOWLEDGED")
    inspector = inspector or RuntimeInspector()
    try:
        checks = inspector.inspect(owners, domains, batch_ids)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        raise RecoveryError("RECOVERY_RUNTIME_UNVERIFIABLE") from error
    report = {"schema_version": 1, "campaign_id": campaign_id, "command_id": command_id,
              "fence_sha256": context["fence_sha256"], "binding_sha256": context["binding_sha256"],
              "source_commit": source_commit, "operator_uid": os.getuid(),
              "tool_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "parallel_config_sha256": config_sha, "observed_at_ns": time.time_ns(), "checks": checks}
    if not apply:
        return {"status": "RECOVERY_ELIGIBLE_PREVIEW", "report": report}
    parent = store.root / "operator-recovery"
    _private_directory(parent)
    output = parent / command_id
    output.mkdir(mode=0o700)  # A failed/unknown prior attempt is retained, never overwritten.
    _sync_directory(parent)
    backup = output / "supervisor-before.sqlite3"
    _write_private(backup, b"")
    connection = sqlite3.connect(backup)
    try:
        store._connection.backup(connection)
    finally:
        connection.close()
    with backup.open("rb") as source:
        os.fsync(source.fileno())
    try:
        report["checks"] = inspector.inspect(owners, domains, batch_ids)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        raise RecoveryError("RECOVERY_RUNTIME_UNVERIFIABLE") from error
    if config.read_bytes() != config_bytes:
        raise RecoveryError("RECOVERY_CONFIG_CHANGED")
    report["observed_at_ns"] = time.time_ns()
    report_path = output / "probe.json"
    config_path = output / "parallel-config.yaml"
    _write_private(config_path, config_bytes)
    _write_private(report_path, _json(report).encode("utf-8"))
    receipt = {"schema_version": 1, "campaign_id": campaign_id, "command_id": command_id,
               "fence_sha256": context["fence_sha256"], "binding_sha256": context["binding_sha256"],
               "status": "OPERATOR_RECOVERED_ABORTED", "execution_success": False,
               "upstream_cleanup_claimed": False}
    for prefix, path in (("report", report_path), ("backup", backup), ("config", config_path)):
        receipt[f"{prefix}_path"] = str(path)
        receipt[f"{prefix}_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    return store.record_operator_recovery(receipt)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store-root", type=Path, required=True)
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--command-id", required=True)
    parser.add_argument("--parallel-config", type=Path, required=True,
                        help="Must byte-match the original preflight config; domain scope is derived, not supplied")
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--apply", action="store_true", help="Default is eligibility preview; requires Web service offline")
    options = parser.parse_args(argv)
    store = None
    try:
        if not (options.store_root / "supervisor.sqlite3").is_file():
            raise RecoveryError("RECOVERY_STORE_NOT_FOUND")
        store = SupervisorStore.open(options.store_root)
        result = recover(store=store, campaign_id=options.campaign_id, command_id=options.command_id,
                         parallel_config=options.parallel_config, source_commit=options.source_commit,
                         apply=options.apply)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (RecoveryError, StoreConflict, OSError, ValueError, sqlite3.Error) as error:
        print(str(error), file=sys.stderr)
        return 1
    finally:
        if store is not None:
            store.close()


if __name__ == "__main__":
    raise SystemExit(main())
