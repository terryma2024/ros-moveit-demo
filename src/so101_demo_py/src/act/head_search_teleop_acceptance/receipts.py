"""Bundle, teardown, bridge cleanup, end-to-end and acceptance receipts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
import json
import os
from pathlib import Path
import time

KIND = "head_search_teleop_acceptance_receipt"


SCHEMA_VERSION = 1


OPERATION = "TELEOP_ACCEPTANCE"


PROFILE = "mujoco"


E2E_CASE = "e2e/head-camera.spec.ts"


E2E_MANIFEST = "head-camera-evidence.json"


E2E_COMMAND = "bun run test:e2e -- e2e/head-camera.spec.ts"


RECEIPT_ARTIFACT = "teleop-acceptance-receipt.json"


CONNECTION_ARTIFACT = "runtime-connection.json"


TEARDOWN_ARTIFACT = "teardown-receipt.json"


CLEANUP_ARTIFACT = "cleanup-receipt.json"


STATE_ARTIFACT = "calibration-state.json"


SOCKET_PATH_LIMIT_BYTES = 103


MINIMUM_SCREENSHOTS = 6


BRIDGE_SOCKET_NAMES = ("normal.sock", "safety.sock")


HEAD_CAMERA_IMAGE_TOPIC = "/head_camera/color"


DEFAULT_FRAME_PROBE = 10


DEFAULT_WEB_PORT = 18082


STOP_SAMPLES = 3


APP_START_TIMEOUT_S = 90.0


APP_STOP_TIMEOUT_S = 30.0


E2E_TIMEOUT_S = 900.0


TEARDOWN_TIMEOUT_S = 30.0


PASSED = "PASSED"


REFUSED = "REFUSED"


FAILED = "FAILED"


TELEOP_INPUTS_INCOMPLETE = "TELEOP_ACCEPTANCE_INPUTS_INCOMPLETE"


TELEOP_RUN_ROOT_EXISTS = "TELEOP_ACCEPTANCE_RUN_ROOT_EXISTS"


TELEOP_RUNTIME_UNVERIFIED = "TELEOP_ACCEPTANCE_RUNTIME_UNVERIFIED"


TELEOP_BUNDLE_MISMATCH = "TELEOP_ACCEPTANCE_BUNDLE_MISMATCH"


TELEOP_REPORT_NOT_PUBLISHED = "TELEOP_ACCEPTANCE_REPORT_NOT_PUBLISHED"


TELEOP_REPORT_NOT_CLOSED = "TELEOP_ACCEPTANCE_REPORT_NOT_CLOSED"


TELEOP_SOCKET_PATH_TOO_LONG = "TELEOP_ACCEPTANCE_SOCKET_PATH_TOO_LONG"


TELEOP_OWNERSHIP_REFUSED = "TELEOP_ACCEPTANCE_OWNERSHIP_REFUSED"


TELEOP_STACK_START_FAILED = "TELEOP_ACCEPTANCE_STACK_START_FAILED"


TELEOP_DETECTOR_FAILED = "TELEOP_ACCEPTANCE_DETECTOR_FAILED"


TELEOP_FRAME_PROBE_FAILED = "TELEOP_ACCEPTANCE_FRAME_PROBE_FAILED"


TELEOP_APP_NOT_SERVED = "TELEOP_ACCEPTANCE_APP_NOT_SERVED"


TELEOP_PROBE_FAILED = "TELEOP_ACCEPTANCE_PROBE_FAILED"


TELEOP_E2E_FAILED = "TELEOP_ACCEPTANCE_E2E_FAILED"


TELEOP_E2E_EVIDENCE_MISSING = "TELEOP_ACCEPTANCE_E2E_EVIDENCE_MISSING"


TELEOP_TEARDOWN_UNPROVEN = "TELEOP_ACCEPTANCE_TEARDOWN_UNPROVEN"


TELEOP_GPU_NOT_RELEASED = "TELEOP_ACCEPTANCE_GPU_NOT_RELEASED"


TELEOP_PROBE_ERROR = "TELEOP_ACCEPTANCE_PROBE_ERROR"


FIT_WARNING = (
    "the acceptance owns one production composition, one CUDA detector and one unified app for the "
    "duration of the case and proves all three gone before the receipt is written; it is a separate "
    "functional-acceptance fixture and never mutates the qualification report it consumes"
)


def _digest(path) -> str:
    target = Path(path)
    if not target.is_file():
        return ""
    return hashlib.sha256(target.read_bytes()).hexdigest()


def _canonical_sha256(value: object) -> str:
    from so101_demo.perception_benchmark.contracts import canonical_sha256

    return canonical_sha256(value)


def _utc_now(now=time.gmtime) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", now())


def _read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def socket_paths(socket_root) -> list[str]:
    """The two bridge endpoints the plan validates, under the registered root's short namespace."""

    root = Path(socket_root)
    return [str(root / name) for name in BRIDGE_SOCKET_NAMES]


def check_socket_paths(paths: Sequence[str], *, limit: int = SOCKET_PATH_LIMIT_BYTES) -> dict:
    """Both complete AF_UNIX endpoint paths must fit the kernel's sockaddr limit, before launch."""

    declared = [str(item) for item in paths]
    lengths = [len(os.fsencode(item)) for item in declared]
    overlong = [item for item, size in zip(declared, lengths) if size > limit]
    return {
        "paths": declared,
        "path_bytes": lengths,
        "max_bytes": max(lengths) if lengths else 0,
        "limit_bytes": limit,
        "within_limit": bool(declared) and not overlong,
        "overlong": overlong,
    }


def bundle_values_sha256(bundle: Mapping) -> str:
    """The approved bundle's own canonical digest of its 17 values, as the promotion binds them."""

    parameters = bundle.get("parameters")
    if isinstance(parameters, Mapping):
        values = {
            name: entry.get("value")
            for name, entry in parameters.items()
            if isinstance(entry, Mapping) and "value" in entry
        }
    else:
        values = bundle.get("values")
    if not isinstance(values, Mapping) or not values:
        raise ValueError(f"{TELEOP_INPUTS_INCOMPLETE}: the bundle declares no values")
    return _canonical_sha256(dict(values))


def verify_bundle(*, bundle_path, production_config) -> dict:
    """The declared bundle, its digest, and the promoted values it must agree with, read off disk."""

    bundle_file = Path(bundle_path)
    if not bundle_file.is_file():
        raise ValueError(f"{TELEOP_INPUTS_INCOMPLETE}: {bundle_file} is absent")
    bundle = _read_json(bundle_file)
    if not isinstance(bundle, Mapping):
        raise ValueError(f"{TELEOP_INPUTS_INCOMPLETE}: {bundle_file} is not a JSON object")
    config_file = Path(production_config)
    document = _read_json(config_file)
    if not isinstance(document, Mapping) or not isinstance(document.get("values"), Mapping):
        raise ValueError(f"{TELEOP_INPUTS_INCOMPLETE}: {config_file} declares no values block")
    promoted = dict(document["values"])
    declared = bundle_values_sha256(bundle)
    observed = _canonical_sha256(promoted)
    return {
        "path": str(bundle_file),
        "sha256": _digest(bundle_file),
        "values_sha256": declared,
        "promoted_config": str(config_file),
        "promoted_config_sha256": _digest(config_file),
        "promoted_values_sha256": observed,
        "values_match": declared == observed,
        "parameter_names": sorted(promoted),
        "values_count": len(promoted),
    }


def read_closed_report(path) -> dict:
    """The plan's precondition: a closed head-only report, verified where it was written."""

    if path is None:
        return {"path": None, "sha256": None, "status": None, "present": False}
    report_file = Path(path)
    if not report_file.is_file():
        return {"path": str(report_file), "sha256": None, "status": None, "present": False}
    document = _read_json(report_file)
    status = document.get("status") if isinstance(document, Mapping) else None
    return {
        "path": str(report_file),
        "sha256": _digest(report_file),
        "status": status,
        "present": True,
    }


def process_group_alive(pid: int) -> bool:
    """True while any process still belongs to the process group led by ``pid``."""

    if int(pid) <= 0:
        return False
    try:
        os.killpg(int(pid), 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def owned_groups(pids: Sequence[int]) -> dict:
    """One entry per owned process group: its leader and whether the whole group is gone."""

    groups = {}
    for pid in pids:
        pid = int(pid)
        groups[str(pid)] = {"leader": pid, "alive": process_group_alive(pid)}
    return groups


def teardown_receipt(
    *,
    owned_pids: Sequence[int],
    processes: Sequence[Mapping],
    nodes: Sequence[str],
    gpu_compute_apps: Sequence[Mapping],
    before: Mapping | None = None,
) -> dict:
    """What teardown actually observed: no owned group alive, an empty graph and a released GPU."""

    groups = owned_groups(owned_pids)
    exited = [name for name, entry in groups.items() if entry["alive"] is False]
    remaining = [str(item.get("cmd") or item.get("pid") or item) for item in processes]
    node_list = [str(node) for node in nodes]
    gpu = [str(item.get("process_name") or item.get("pid") or item) for item in gpu_compute_apps]
    graph_clear = not node_list
    gpu_released = not gpu
    controller_stopped = bool(exited) and not remaining
    return {
        "controller_stopped": controller_stopped,
        "controller_owner_stopped": controller_stopped,
        "children_exited": not remaining,
        "graph_clear": graph_clear,
        "process_groups_exited": len(exited),
        "process_groups_declared": len(groups),
        "groups": groups,
        "remaining_processes": remaining,
        "remaining_nodes": node_list,
        "gpu_compute_apps": gpu,
        "gpu_released": gpu_released,
        "before": dict(before or {}),
        "after": {
            "processes": remaining,
            "nodes": node_list,
            "gpu_compute_apps": gpu,
        },
        "teardown": "observed",
    }


def bridge_cleanup_receipt(
    *, socket_root, declared_paths: Sequence[str], created: Sequence[str] = ()
) -> dict:
    """The bridge namespace after the run: what was declared, what existed, what is gone now."""

    root = Path(socket_root)
    declared = [str(item) for item in declared_paths]
    existed = [item for item in declared if Path(item).exists()]
    made = [str(item) for item in created]
    return {
        "kind": "head_search_teleop_bridge_cleanup",
        "operation": OPERATION,
        "socket_root": str(root),
        "socket_paths": declared,
        "socket_path_bytes": [len(os.fsencode(item)) for item in declared],
        "limit_bytes": SOCKET_PATH_LIMIT_BYTES,
        "created": made,
        "existed_before_cleanup": existed,
        "remaining": [item for item in declared if Path(item).exists()],
        "directory_retained": root.is_dir(),
        "cleaned": not [item for item in declared if Path(item).exists()],
    }


def read_e2e_evidence(evidence_root, *, report_path=None) -> dict:
    """The installed case's own on-disk evidence: its manifest, its screenshots, its Playwright report."""

    root = Path(evidence_root)
    manifest_file = root / E2E_MANIFEST
    manifest = _read_json(manifest_file)
    if not isinstance(manifest, Mapping):
        return {
            "present": False,
            "manifest": str(manifest_file),
            "case": None,
            "status": None,
            "screenshots": [],
            "missing_screenshots": [],
            "raw_overlay_pairs": [],
            "refusals": [],
        }
    raw_shots = manifest.get("screenshots")
    raw_shots = (
        raw_shots
        if isinstance(raw_shots, Sequence) and not isinstance(raw_shots, (str, bytes))
        else []
    )
    screenshots: list[Path] = []
    for name in raw_shots:
        candidate = Path(str(name))
        screenshots.append(candidate if candidate.is_absolute() else root / candidate)
    missing = [str(item) for item in screenshots if not item.is_file()]
    pairs = manifest.get("raw_overlay_pairs")
    pairs = pairs if isinstance(pairs, Sequence) and not isinstance(pairs, (str, bytes)) else []
    if report_path is None:
        report_path = root / "reports" / "playwright-default.json"
    report = _read_json(report_path) if Path(report_path).is_file() else None
    return {
        "present": True,
        "manifest": str(manifest_file),
        "manifest_sha256": _digest(manifest_file),
        "case": manifest.get("case"),
        "status": manifest.get("status"),
        "runtime_id": manifest.get("runtime_id"),
        "operation": manifest.get("operation"),
        "states": list(manifest.get("states") or []),
        "screenshots": [str(item) for item in screenshots],
        "missing_screenshots": missing,
        "raw_overlay_pairs": [dict(item) for item in pairs if isinstance(item, Mapping)],
        "refusals": [
            dict(item) for item in (manifest.get("refusals") or []) if isinstance(item, Mapping)
        ],
        "chrome": dict(manifest.get("chrome") or {}),
        "report": {
            "path": str(report_path) if report_path is not None else None,
            "sha256": _digest(report_path) if report_path is not None else None,
            "passed": _playwright_passed(report),
        },
    }


def _playwright_passed(report) -> bool | None:
    """Playwright's own JSON report, reduced to whether every case passed."""

    if not isinstance(report, Mapping):
        return None
    suites = report.get("suites")
    if not isinstance(suites, Sequence) or isinstance(suites, (str, bytes)):
        return None
    outcome = True
    pending = [dict(item) for item in suites if isinstance(item, Mapping)]
    while pending:
        suite = pending.pop()
        for spec in suite.get("specs") or []:
            if not isinstance(spec, Mapping):
                continue
            for case in spec.get("tests") or []:
                if isinstance(case, Mapping) and case.get("status") != "expected":
                    outcome = False
        for child in suite.get("suites") or []:
            if isinstance(child, Mapping):
                pending.append(dict(child))
    return outcome


def e2e_block(evidence: Mapping, *, command: str, rc: int | None) -> dict:
    """The gate's ``e2e`` block, taken from the evidence rather than from the caller's word."""

    screenshots = list(evidence.get("screenshots") or [])
    pairs = list(evidence.get("raw_overlay_pairs") or [])
    missing = list(evidence.get("missing_screenshots") or [])
    report_passed = (evidence.get("report") or {}).get("passed")
    status = evidence.get("status")
    if not evidence.get("present"):
        return {
            "case": None,
            "status": None,
            "command": command,
            "rc": rc,
            "raw_overlay_pairs": 0,
            "screenshots": [],
            "missing_screenshots": [],
            "states": [],
            "refusals": [],
            "manifest": evidence.get("manifest"),
            "manifest_sha256": None,
            "report": evidence.get("report"),
            "chrome": {},
            "minimum_screenshots": MINIMUM_SCREENSHOTS,
        }
    if (
        evidence.get("case") == E2E_CASE
        and status == PASSED
        and rc == 0
        and report_passed is not False
        and not missing
        and len(screenshots) >= MINIMUM_SCREENSHOTS
        and len(pairs) >= 1
    ):
        outcome = PASSED
    elif rc not in (0, None):
        outcome = FAILED
    else:
        # the case ran and did not produce the pass the plan requires: six screenshots, a real
        # raw/overlay pair and its own PASSED manifest. That is a refusal, never a quiet pass
        outcome = REFUSED
    return {
        "case": evidence.get("case"),
        "status": outcome,
        "command": command,
        "rc": rc,
        "raw_overlay_pairs": len(pairs),
        "screenshots": screenshots,
        "missing_screenshots": missing,
        "states": list(evidence.get("states") or []),
        "refusals": list(evidence.get("refusals") or []),
        "manifest": evidence.get("manifest"),
        "manifest_sha256": evidence.get("manifest_sha256"),
        "report": evidence.get("report"),
        "chrome": dict(evidence.get("chrome") or {}),
        "minimum_screenshots": MINIMUM_SCREENSHOTS,
    }


def acceptance_receipt(
    *,
    runtime: Mapping,
    bundle_sha256: str,
    runtime_id: str,
    report: Mapping,
    connection: Mapping | None,
    detector: Mapping,
    probes: Mapping,
    e2e: Mapping,
    teardown: Mapping,
    bridge: Mapping,
    checks: Sequence[Mapping],
    refusals: Sequence[Mapping],
    acceptance_root,
    run_root,
    started_at_utc: str,
    finished_at_utc: str,
    elapsed_s: float,
    profile: str = PROFILE,
) -> dict:
    """The acceptance receipt, in the shape the aggregate's ``teleop_acceptance`` gate consumes."""

    refused = [dict(item) for item in refusals]
    return {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "operation": OPERATION,
        "profile": profile,
        "status": REFUSED if refused else PASSED,
        "runtime_id": str(runtime_id),
        "source_commit": runtime.get("source_commit"),
        "bundle_sha256": str(bundle_sha256),
        "acceptance_root": str(acceptance_root),
        "run_root": str(run_root),
        "started_at_utc": started_at_utc,
        "finished_at_utc": finished_at_utc,
        "elapsed_s": float(elapsed_s),
        "runtime": {
            key: runtime.get(key)
            for key in (
                "final_run",
                "source_commit",
                "production_config",
                "production_config_sha256",
                "values_sha256",
                "values_count",
                "allow_cpu_fallback",
                "cuda_device",
                "weight_path",
                "weight_sha256_declared",
                "weight_sha256_observed",
            )
        },
        "qualification_report": dict(report),
        "connection": dict(connection or {}),
        "detector": dict(detector),
        "probes": {name: dict(value) for name, value in probes.items()},
        "e2e": dict(e2e),
        "teardown": dict(teardown),
        "bridge": dict(bridge),
        "checks": [dict(item) for item in checks],
        "refusals": refused,
        "fit_warning": FIT_WARNING,
    }


def validate_receipt(document: Mapping) -> list[str]:
    """Re-derive the aggregate's own ``teleop_acceptance`` conditions; the tests pin this list."""

    problems: list[str] = []
    if document.get("kind") != KIND or document.get("operation") != OPERATION:
        problems.append("kind/operation")
    if len(os.fsencode(E2E_CASE)) and document.get("e2e", {}).get("case") != E2E_CASE:
        problems.append("e2e.case")
    detector = document.get("detector") or {}
    if (
        int(detector.get("count", -1)) != 1
        or int(detector.get("teleop_detector_factory_count", -1)) != 0
    ):
        problems.append("detector")
    teardown = document.get("teardown") or {}
    if (
        teardown.get("controller_stopped") is not True
        or teardown.get("graph_clear") is not True
        or int(teardown.get("process_groups_exited", 0)) < 2
    ):
        problems.append("teardown")
    bridge = document.get("bridge") or {}
    sockets = bridge.get("socket_paths") or []
    if len(sockets) < 2 or any(
        len(os.fsencode(str(item))) > SOCKET_PATH_LIMIT_BYTES for item in sockets
    ):
        problems.append("bridge.socket_paths")
    cleanup = (bridge.get("cleanup_receipt") or {}).get("path")
    if not cleanup or not Path(str(cleanup)).is_file():
        problems.append("bridge.cleanup_receipt")
    e2e = document.get("e2e") or {}
    shots = e2e.get("screenshots") or []
    if (
        e2e.get("status") != PASSED
        or int(e2e.get("raw_overlay_pairs", 0)) < 1
        or len(shots) < MINIMUM_SCREENSHOTS
    ):
        problems.append("e2e")
    for name in shots:
        if not Path(str(name)).is_file():
            problems.append("e2e.screenshot_missing")
            break
    report = document.get("qualification_report") or {}
    if report.get("status") != "HEAD_SEARCH_QUALIFIED":
        problems.append("qualification_report.status")
    return problems
