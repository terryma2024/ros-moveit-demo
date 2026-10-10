"""Task 14 Step 6: the separately owned Teleop acceptance, with a teardown the receipt can prove.

The plan starts *one* new stack from the frozen install, the promoted config, the approved bundle, the
approval receipt and the closed head-only report; runs the installed unified app against that one stack
and its one detector; exercises the head-camera surface; and tears everything down before it writes
anything. The installed surface this module replaces wrote a connection descriptor immediately, ran no
probe and recorded ``teardown: not-attempted`` (HS-315 row 10).

What this module owns, in the plan's order and with no step optional:

1. read the frozen runtime's own identity off disk and refuse a runtime that is not the declared one;
2. verify the declared approved bundle against the promoted 17 values, and the socket paths against the
   AF_UNIX limit *before* anything is launched;
3. prove the pre-start process/ROS/GPU table empty, then start one production composition and its one
   CUDA detector, and measure the real head-camera frames it consumes;
4. publish the connection descriptor only after the probes pass, start the installed unified app against
   it, and record every head-camera probe (served, status, bounded absolute target, sealed interval,
   out-of-range refusal, no-frame and stale-frame capture refusals, the three-sample stop proof);
5. run the installed Playwright case and read *its own* on-disk evidence rather than a caller's claim;
6. stop the app and the stack, prove every owned process group gone and the GPU released, then write the
   teardown receipt, the bridge cleanup receipt and finally the acceptance receipt.

The receipt is the document the aggregate's ``teleop_acceptance`` gate consumes field by field. A closed
head-only report is a *precondition* the plan states and this module cannot invent: when it is absent the
acceptance still runs and records the truth, and the receipt says so in ``qualification_report`` and in
``refusals`` instead of claiming a report that does not exist.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import subprocess  # noqa: S404 - the app and the e2e runner are installed programs
import time
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from pathlib import Path

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


# --- pure readers and assemblers ----------------------------------------------------------------------


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


# --- the owned run ------------------------------------------------------------------------------------


class TeleopAcceptanceRefused(RuntimeError):
    """The acceptance refused by name; the code is the receipt's own vocabulary."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def _write(root: Path, name: str, document: Mapping) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    target = root / name
    target.write_text(json.dumps(dict(document), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


class TeleopAcceptance:
    """One owned Teleop acceptance: start, probe, run the case, tear down, then write the receipt.

    Every side effect is a seam so the unit tests can drive the whole orchestration with synthetic
    fixtures and assert the *ordering*: nothing is written before its own evidence exists, and the
    receipt is written only after the teardown has been observed.
    """

    def __init__(
        self,
        *,
        run_root,
        acceptance_root,
        socket_root,
        ready_file,
        runtime: Mapping,
        bundle: Mapping,
        report: Mapping,
        values: Mapping,
        runtime_id: str,
        model_id: str,
        weights_path,
        device: str = "cuda",
        frames: int = DEFAULT_FRAME_PROBE,
        web_port: int = DEFAULT_WEB_PORT,
        scene_path=None,
        urdf_path=None,
        plugin_config_path=None,
        controller_config_path=None,
        frozen_candidate_path=None,
        operating_point: Mapping | None = None,
        app_environment: Mapping | None = None,
        app_command: Sequence[str] | None = None,
        static_dir=None,
        web_dir=None,
        profile: str = PROFILE,
        stack_factory=None,
        detector_flight=None,
        app_factory=None,
        app_probe=None,
        e2e_runner=None,
        ownership_probe=None,
        observer=None,
        clock=time.monotonic,
        sleep=time.sleep,
        stdout=None,
        stderr=None,
    ) -> None:
        self.run_root = Path(run_root)
        self.acceptance_root = Path(acceptance_root)
        self.socket_root = Path(socket_root)
        self.ready_file = Path(ready_file)
        self.runtime = dict(runtime)
        self.bundle = dict(bundle)
        self.report = dict(report)
        self.values = dict(values)
        self.runtime_id = str(runtime_id)
        self.model_id = str(model_id)
        self.weights_path = Path(weights_path)
        self.device = str(device)
        self.frames = int(frames)
        self.web_port = int(web_port)
        self.scene_path = None if scene_path is None else Path(scene_path)
        self.urdf_path = None if urdf_path is None else Path(urdf_path)
        self.plugin_config_path = None if plugin_config_path is None else Path(plugin_config_path)
        self.controller_config_path = (
            None if controller_config_path is None else Path(controller_config_path)
        )
        self.frozen_candidate_path = (
            None if frozen_candidate_path is None else Path(frozen_candidate_path)
        )
        self.operating_point = dict(operating_point or {})
        if not self.operating_point and "tracking_iou" in self.values:
            self.operating_point = {"iou": float(self.values["tracking_iou"])}
        self.app_environment = dict(app_environment or {})
        self.app_command = list(app_command or ())
        self.static_dir = None if static_dir is None else Path(static_dir)
        self.web_dir = None if web_dir is None else Path(web_dir)
        self.profile = str(profile)
        self.stack_factory = stack_factory
        self.detector_flight = detector_flight
        self.app_factory = app_factory
        self.app_probe = app_probe
        self.e2e_runner = e2e_runner
        self.ownership_probe = ownership_probe
        self.observer = observer
        self.clock = clock
        self.sleep = sleep
        self.stdout = stdout
        self.stderr = stderr
        self.checks: list[dict] = []
        self.refusals: list[dict] = []
        self.evidence: dict = {}

    # -- helpers ---------------------------------------------------------------------------------------

    def log(self, message: str) -> None:
        if self.stdout is not None:
            self.stdout.write(f"[{_utc_now()}] teleop-acceptance: {message}\n")
            self.stdout.flush()

    def warn(self, message: str) -> None:
        if self.stderr is not None:
            self.stderr.write(f"[{_utc_now()}] teleop-acceptance: {message}\n")
            self.stderr.flush()

    def check(self, name: str, ok: bool, detail: str, **extra) -> bool:
        entry = {"name": name, "status": PASSED if ok else FAILED, "detail": detail}
        entry.update(extra)
        self.checks.append(entry)
        if not ok:
            self.warn(f"check {name} FAILED: {detail}")
        return bool(ok)

    def refuse(self, code: str, detail: str, *, fatal: bool = False) -> None:
        self.refusals.append({"code": code, "detail": detail, "fatal": bool(fatal)})
        self.warn(f"{code}: {detail}")
        if fatal:
            raise TeleopAcceptanceRefused(code, detail)

    # -- the run ---------------------------------------------------------------------------------------

    def run(self) -> dict:
        started = self.clock()
        started_at = _utc_now()
        root = self.run_root
        if root.exists():
            raise TeleopAcceptanceRefused(
                TELEOP_RUN_ROOT_EXISTS, f"{root} already exists; a run has no resume"
            )
        root.mkdir(parents=True)
        self.acceptance_root.mkdir(parents=True, exist_ok=True)
        self.socket_root.mkdir(parents=True, exist_ok=True)
        _write(root, STATE_ARTIFACT, {"state": "RUNNING", "phase": "teleop-acceptance"})

        declared = self.declared_identity()
        sockets = check_socket_paths(socket_paths(self.socket_root))
        if not sockets["within_limit"]:
            self.refuse(
                TELEOP_SOCKET_PATH_TOO_LONG,
                f"the bridge endpoints must be {SOCKET_PATH_LIMIT_BYTES} bytes or fewer: "
                f"{sockets['path_bytes']} for {sockets['paths']}",
                fatal=True,
            )
        if not declared["values_match"]:
            self.refuse(
                TELEOP_BUNDLE_MISMATCH,
                f"the declared bundle's values digest to {declared['values_sha256']}, the promoted config "
                f"digests to {declared['promoted_values_sha256']}",
                fatal=True,
            )
        if not self.report.get("present"):
            self.refuse(
                TELEOP_REPORT_NOT_PUBLISHED,
                f"no closed head-only report exists at {self.report.get('path')!r}: the plan's Step 5 "
                "documents are published only when the nine qualification gates hold, and they do not",
            )
        elif self.report.get("status") != "HEAD_SEARCH_QUALIFIED":
            self.refuse(
                TELEOP_REPORT_NOT_CLOSED,
                f"the cited report is {self.report.get('status')!r}, not HEAD_SEARCH_QUALIFIED",
            )

        stack = None
        app = None
        owned_pids: list[int] = []
        before = self.observe()
        if before.get("processes") or before.get("nodes") or before.get("gpu_compute_apps"):
            self.refuse(
                TELEOP_OWNERSHIP_REFUSED,
                f"a second owner is active before the acceptance starts: processes="
                f"{before.get('processes')} nodes={before.get('nodes')} "
                f"gpu={before.get('gpu_compute_apps')}",
                fatal=True,
            )
        try:
            self.log("starting the one production composition")
            stack, flight = self.start_stack_and_detector()
            owned_pids.extend(self.stack_pids(stack))
            self.evidence["flight"] = flight
            connection = self.publish_connection(flight)
            self.evidence["connection"] = connection
            app = self.start_app(connection)
            owned_pids.extend(self.app_pids(app))
            status = self.await_app()
            self.evidence["app_status"] = status
            self.evidence["status"] = status
            probes = self.run_probes(status)
            self.evidence["probes"] = probes
            e2e_rc = self.run_e2e()
        finally:
            if app is not None:
                self.stop_app(app)
            if stack is not None:
                self.stop_stack(stack)

        after = self.observe()
        teardown = teardown_receipt(
            owned_pids=owned_pids,
            processes=after.get("processes") or (),
            nodes=after.get("nodes") or (),
            gpu_compute_apps=after.get("gpu_compute_apps") or (),
            before={"processes": before.get("processes"), "nodes": before.get("nodes")},
        )
        if not (
            teardown["controller_stopped"]
            and teardown["graph_clear"]
            and teardown["process_groups_exited"] >= 2
        ):
            self.refuse(
                TELEOP_TEARDOWN_UNPROVEN,
                f"the acceptance stack could not be proven gone: {teardown}",
            )
        if not teardown["gpu_released"]:
            self.refuse(
                TELEOP_GPU_NOT_RELEASED, "a compute process still held the GPU after the teardown"
            )
        self.evidence["teardown"] = teardown
        teardown_path = _write(root, TEARDOWN_ARTIFACT, teardown)

        cleanup = bridge_cleanup_receipt(
            socket_root=self.socket_root, declared_paths=sockets["paths"]
        )
        cleanup_path = _write(root, CLEANUP_ARTIFACT, cleanup)
        cleanup["cleanup_receipt"] = {"path": str(cleanup_path), "sha256": _digest(cleanup_path)}

        evidence = read_e2e_evidence(
            self.acceptance_root,
            report_path=self.acceptance_root / "reports" / "playwright-default.json",
        )
        e2e = e2e_block(evidence, command=E2E_COMMAND, rc=e2e_rc)
        if e2e["status"] != PASSED:
            self.refuse(
                TELEOP_E2E_FAILED if evidence.get("present") else TELEOP_E2E_EVIDENCE_MISSING,
                f"the installed case did not pass with fresh evidence: case={e2e['case']!r} "
                f"status={e2e['status']!r} rc={e2e['rc']!r} pairs={e2e['raw_overlay_pairs']} "
                f"screenshots={len(e2e['screenshots'])} missing={e2e['missing_screenshots'][:3]}",
            )

        detector = self.detector_block(flight)
        probes = self.evidence.get("probes") or {}
        if not all(entry.get("status") == PASSED for entry in probes.values()):
            failed = sorted(name for name, entry in probes.items() if entry.get("status") != PASSED)
            self.refuse(TELEOP_PROBE_FAILED, f"the head-camera probes did not all pass: {failed}")

        finished_at = _utc_now()
        receipt = acceptance_receipt(
            runtime=self.runtime,
            bundle_sha256=declared["sha256"],
            runtime_id=self.runtime_id,
            report=self.report,
            connection={
                **(self.evidence.get("connection") or {}),
                "sha256": _digest(self.ready_file),
            },
            detector=detector,
            probes=probes,
            e2e=e2e,
            teardown=teardown,
            bridge={
                "socket_root": str(self.socket_root),
                "socket_paths": sockets["paths"],
                "socket_path_bytes": sockets["path_bytes"],
                "cleanup_receipt": cleanup["cleanup_receipt"],
                "cleanup": cleanup,
            },
            checks=[dict(item) for item in self.checks],
            refusals=self.refusals,
            acceptance_root=self.acceptance_root,
            run_root=root,
            started_at_utc=started_at,
            finished_at_utc=finished_at,
            elapsed_s=self.clock() - started,
            profile=self.profile,
        )
        receipt["declared"] = {
            key: value for key, value in declared.items() if key != "parameter_names"
        }
        receipt["teardown_receipt"] = {"path": str(teardown_path), "sha256": _digest(teardown_path)}
        receipt["problems"] = validate_receipt(receipt)
        receipt_path = _write(self.acceptance_root, RECEIPT_ARTIFACT, receipt)
        _write(
            root,
            STATE_ARTIFACT,
            {
                "state": REFUSED if receipt["refusals"] else "SUCCEEDED",
                "phase": "teleop-acceptance",
                "receipt": str(receipt_path),
            },
        )
        self.log(
            f"receipt {receipt_path} status={receipt['status']} refusals={len(receipt['refusals'])}"
        )
        return receipt

    # -- the seams -------------------------------------------------------------------------------------

    def declared_identity(self) -> dict:
        """The declared bundle and the frozen runtime it was verified against, both read off disk."""

        return {**dict(self.runtime), **dict(self.bundle)}

    def observe(self) -> dict:
        if self.observer is None:
            return {"processes": [], "nodes": [], "gpu_compute_apps": [], "sim_clock_s": []}
        return dict(self.observer())

    def stack_pids(self, stack) -> list[int]:
        processes = getattr(stack, "processes", None) or []
        return [int(getattr(process, "pid", process)) for process in processes]

    def app_pids(self, app) -> list[int]:
        pid = getattr(app, "pid", None)
        return [] if pid is None else [int(pid)]

    def start_stack_and_detector(self):
        if self.stack_factory is None:
            raise TeleopAcceptanceRefused(
                TELEOP_STACK_START_FAILED, "no stack factory was supplied"
            )
        stack = self.stack_factory(
            urdf_path=self.urdf_path,
            scene_path=self.scene_path,
            plugin_config_path=self.plugin_config_path,
            controller_config_path=self.controller_config_path,
            workspace=self.run_root / "stack",
            session_id=self.session_id(),
            logger=lambda message: self.log(f"stack: {message}"),
        )
        try:
            stack.start()
        except Exception as error:  # noqa: BLE001 - a start failure is a named refusal
            raise TeleopAcceptanceRefused(TELEOP_STACK_START_FAILED, repr(error)) from error
        # once the stack is up this function owns its teardown: a failure below must not leave the
        # production composition running behind a refusal, which is exactly what a leaked child is
        try:
            return stack, self.probe_stack_frames(stack)
        except BaseException:
            self.stop_stack(stack)
            raise

    def probe_stack_frames(self, stack) -> dict:
        if self.detector_flight is None:
            raise TeleopAcceptanceRefused(
                TELEOP_DETECTOR_FAILED, "no head-camera flight was supplied"
            )
        try:
            flight = dict(
                self.detector_flight(
                    session_id=self.session_id(),
                    values=self.values,
                    weights_path=self.weights_path,
                    model_id=self.model_id,
                    device=self.device,
                    frames=self.frames,
                    operating_point=self.operating_point,
                    log=self.log,
                )
            )
        except Exception as error:  # noqa: BLE001 - a detector failure is a named refusal
            raise TeleopAcceptanceRefused(TELEOP_DETECTOR_FAILED, repr(error)) from error
        if not self.check(
            "one_cuda_detector",
            int(flight.get("detector_count", 0)) == 1
            and str(flight.get("runtime_device", "")) == self.device
            and flight.get("allow_cpu_fallback") is False,
            f"the acceptance constructed {flight.get('detector_count')} detector(s) on "
            f"{flight.get('runtime_device')!r} with allow_cpu_fallback="
            f"{flight.get('allow_cpu_fallback')!r}",
            frames=flight.get("frames"),
        ):
            raise TeleopAcceptanceRefused(
                TELEOP_DETECTOR_FAILED, "the acceptance did not prove one CUDA detector"
            )
        if not self.check(
            "head_camera_frames",
            int(flight.get("frame_count", 0)) >= 1,
            f"the detector consumed {flight.get('frame_count')} real frames at "
            f"{flight.get('frame_rate_hz')} Hz",
        ):
            raise TeleopAcceptanceRefused(
                TELEOP_FRAME_PROBE_FAILED, "the head camera published no frame to the detector"
            )
        return flight

    def session_id(self) -> str:
        return f"{self.runtime_id}-acceptance"

    def connection_document(self, flight: Mapping) -> dict:
        from so101_demo.act.head_search_qualification import process_start_ticks

        interval = self.values.get("lock_valid_neck_rad") or [-0.1756, 0.0805]
        return {
            "operation": OPERATION,
            "kind": "head_search_teleop_connection",
            "runtime_id": self.runtime_id,
            "head_search_runtime_id": self.runtime_id,
            "simulation_session_id": self.session_id(),
            "execution_generation": 1,
            "model_id": self.model_id,
            "bundle_sha256": str(self.bundle.get("sha256", "")),
            "source_commit": self.runtime.get("source_commit"),
            "safe_interval_rad": [float(interval[0]), float(interval[1])],
            "bridge_socket_root": str(self.socket_root),
            "head_camera_topic": HEAD_CAMERA_IMAGE_TOPIC,
            "head_camera_frame_rate_hz": flight.get("frame_rate_hz"),
            "owner": {
                "pid": os.getpid(),
                "started_ticks": process_start_ticks(),
                "argv_sha256": hashlib.sha256(" ".join(os.sys.argv).encode("utf-8")).hexdigest(),
            },
        }

    def publish_connection(self, flight: Mapping) -> dict:
        document = self.connection_document(flight)
        self.ready_file.parent.mkdir(parents=True, exist_ok=True)
        self.ready_file.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        _write(self.run_root, CONNECTION_ARTIFACT, document)
        self.log(f"connection descriptor {self.ready_file}")
        return document

    def app_env(self) -> dict:
        environment = dict(os.environ)
        environment.update(self.app_environment)
        environment.setdefault("SO101_UNIFIED_RUNTIME_ID", self.runtime_id)
        environment.setdefault("SO101_UNIFIED_SOCKET_DIR", str(self.socket_root))
        environment.setdefault("SO101_HEAD_CAMERA_CONNECTION", str(self.ready_file))
        environment.setdefault("SO101_UNIFIED_EVIDENCE_ROOT", str(self.acceptance_root))
        environment.setdefault("SO101_UNIFIED_BACKEND", "mujoco_py")
        return environment

    def start_app(self, connection: Mapping) -> object:
        if self.app_factory is None:
            raise TeleopAcceptanceRefused(
                TELEOP_APP_NOT_SERVED, "no unified app factory was supplied"
            )
        try:
            app = self.app_factory(
                command=list(self.app_command),
                environment=self.app_env(),
                port=self.web_port,
                capture_dir=self.acceptance_root / "captures",
                static_dir=self.static_dir,
                stdout_path=self.acceptance_root / "server.log",
            )
        except Exception as error:  # noqa: BLE001 - a start failure is a named refusal
            raise TeleopAcceptanceRefused(TELEOP_APP_NOT_SERVED, repr(error)) from error
        self.log(f"unified app pid {getattr(app, 'pid', None)} on port {self.web_port}")
        return app

    def await_app(self) -> dict:
        if self.app_probe is None:
            raise TeleopAcceptanceRefused(TELEOP_APP_NOT_SERVED, "no app probe was supplied")
        base_url = f"http://127.0.0.1:{self.web_port}"
        deadline = self.clock() + APP_START_TIMEOUT_S
        status = None
        while self.clock() < deadline:
            status = self.app_probe({"action": "status", "base_url": base_url})
            if status.get("ok"):
                break
            self.sleep(1.0)
        if not status or not status.get("ok"):
            raise TeleopAcceptanceRefused(
                TELEOP_APP_NOT_SERVED,
                f"the head-camera status route never answered 200: {status}",
            )
        self.check(
            "served_status_route",
            status.get("status") == 200,
            f"GET /teleop/head-camera/status answered {status.get('status')}",
        )
        body = status.get("body") or {}
        self.check(
            "served_identity",
            body.get("available") is True
            and body.get("operation") == OPERATION
            and body.get("runtime_id") == self.runtime_id
            and str(body.get("model_id") or "") == self.model_id,
            f"the served status repeats operation/runtime/model: {body}",
            body=body,
        )
        return body

    def run_probes(self, status: Mapping) -> dict:
        if self.app_probe is None:
            raise TeleopAcceptanceRefused(TELEOP_PROBE_FAILED, "no app probe was supplied")
        base_url = f"http://127.0.0.1:{self.web_port}"
        interval = list(status.get("safe_interval_rad") or self.connection_interval())
        self.evidence["served_interval"] = interval
        low, high = float(interval[0]), float(interval[1])
        inside = (low + high) / 2.0
        outside = high + max(1.0, (high - low))
        observations = {
            "capture_no_frame": self.app_probe({"action": "capture", "base_url": base_url}),
            "target_sealed_interval": self.app_probe(
                {
                    "action": "target",
                    "base_url": base_url,
                    "payload": {"target_rad": inside, "safe_interval_rad": [low, high]},
                }
            ),
            "target_out_of_range": self.app_probe(
                {"action": "target", "base_url": base_url, "payload": {"target_rad": outside}}
            ),
            "target_bounded": self.app_probe(
                {"action": "target", "base_url": base_url, "payload": {"target_rad": inside}}
            ),
            "stop_stopping": self.app_probe(
                {
                    "action": "stop",
                    "base_url": base_url,
                    "payload": {"neck_velocity_rad_s": 0.0, "sim_time_s": 1.0},
                }
            ),
            "stop_proof": self.stop_proof(self.app_probe, base_url),
            "stop_replay_resets": self.app_probe(
                {
                    "action": "stop",
                    "base_url": base_url,
                    "payload": {"neck_velocity_rad_s": 0.0, "sim_time_s": 1.0},
                }
            ),
        }
        probes = {
            name: self.probe_block(
                name, observation, low=low, high=high, inside=inside, outside=outside
            )
            for name, observation in observations.items()
        }
        return probes

    def stop_proof(self, probe, base_url: str) -> dict:
        """Three consecutive fresh raw samples, each through the installed route."""

        samples = []
        for index in range(2, 2 + STOP_SAMPLES):
            samples.append(
                probe(
                    {
                        "action": "stop",
                        "base_url": base_url,
                        "payload": {"neck_velocity_rad_s": 0.0, "sim_time_s": float(index)},
                    }
                )
            )
        return {"ok": all(item.get("ok") for item in samples), "samples": samples}

    def connection_interval(self) -> list[float]:
        interval = self.values.get("lock_valid_neck_rad") or [-0.1756, 0.0805]
        return [float(interval[0]), float(interval[1])]

    def probe_block(self, name: str, observation: Mapping, *, low, high, inside, outside) -> dict:
        body = observation.get("body") or {}
        # the app's structured-error handler unwraps `HTTPException.detail`, so the refusal arrives as
        # the code mapping itself; a wrapped body is accepted too rather than assumed away
        wrapped = (body.get("detail") or {}) if isinstance(body, Mapping) else {}
        code = (body.get("code") if isinstance(body, Mapping) else None) or (
            wrapped.get("code") if isinstance(wrapped, Mapping) else None
        )
        ok = False
        detail = ""
        if name == "capture_no_frame":
            ok = observation.get("status") == 409 and code == "HEAD_CAPTURE_NO_FRAME"
            detail = f"capture before any frame refused with {code!r}"
        elif name == "target_sealed_interval":
            ok = observation.get("status") == 409 and code == "HEAD_TARGET_INTERVAL_SEALED"
            detail = f"a caller-supplied interval was refused with {code!r}"
        elif name == "target_out_of_range":
            ok = observation.get("status") == 409 and code == "HEAD_TARGET_OUT_OF_RANGE"
            detail = f"the absolute bound refused {outside} with {code!r}"
        elif name == "target_bounded":
            ok = (
                observation.get("ok") is True
                and abs(float(body.get("submitted_rad", 1e9)) - inside) < 1e-9
                and body.get("status") == "SUBMITTED"
            )
            detail = f"the sealed interval accepted {inside} and echoed it"
        elif name == "stop_stopping":
            ok = observation.get("ok") is True and body.get("state") == "STOPPING"
            detail = f"one accepted sample reports {body.get('state')!r}, never STOPPED"
        elif name == "stop_proof":
            last = (observation.get("samples") or [{}])[-1].get("body") or {}
            ok = (
                observation.get("ok") is True
                and last.get("state") == "STOPPED"
                and int(last.get("consecutive_samples", 0)) >= STOP_SAMPLES
            )
            detail = (
                f"three consecutive fresh samples ended {last.get('state')!r} at "
                f"{last.get('consecutive_samples')} samples"
            )
        elif name == "stop_replay_resets":
            ok = observation.get("ok") is True and int(body.get("consecutive_samples", 1)) == 0
            detail = f"a replayed sim_time_s reset the proof to {body.get('consecutive_samples')}"
        self.check(f"probe_{name}", bool(ok), detail)
        return {
            "status": PASSED if ok else FAILED,
            "detail": detail,
            "http_status": observation.get("status"),
            "code": code,
            "response": body,
        }

    def run_e2e(self) -> int | None:
        if self.e2e_runner is None:
            self.refuse(TELEOP_E2E_EVIDENCE_MISSING, "no e2e runner was supplied")
            self.evidence["e2e_rc"] = None
            return None
        result = dict(
            self.e2e_runner(
                base_url=f"http://127.0.0.1:{self.web_port}",
                evidence_root=self.acceptance_root,
                web_dir=self.web_dir,
                stdout_path=self.acceptance_root / "e2e.log",
                stderr_path=self.acceptance_root / "e2e.err.log",
            )
        )
        rc = result.get("rc")
        self.evidence["e2e_rc"] = rc
        self.evidence["e2e_command"] = result.get("command")
        self.check(
            "e2e_case",
            rc == 0,
            f"{result.get('command')} returned rc={rc}",
            rc=rc,
        )
        return rc

    def stop_app(self, app) -> None:
        self.log("stopping the unified app")
        if self.app_factory is None:
            return
        try:
            app.terminate()
        except Exception as error:  # noqa: BLE001 - a stop failure is verified, not asserted
            self.warn(f"the app terminate raised {error!r}")
        try:
            app.wait(timeout=APP_STOP_TIMEOUT_S)
        except Exception:  # noqa: BLE001 - the observation below decides, not this call
            self.warn("the app did not exit within its budget; killing its process group")
            pid = getattr(app, "pid", None)
            if pid is not None:
                try:
                    os.killpg(int(pid), signal.SIGKILL)
                except OSError as error:
                    self.warn(f"the group kill raised {error!r}")
            try:
                app.wait(timeout=APP_STOP_TIMEOUT_S)
            except Exception as error:  # noqa: BLE001 - the teardown proof is what decides
                self.warn(f"the app still did not exit: {error!r}")

    def stop_stack(self, stack) -> None:
        self.log("stopping the production composition")
        try:
            stack.stop()
        except Exception as error:  # noqa: BLE001 - a stop failure is verified, not asserted
            self.warn(f"the stack stop raised {error!r}")

    def detector_block(self, flight: Mapping) -> dict:
        return {
            "count": int(flight.get("detector_count", 0)),
            "teleop_detector_factory_count": self.evidence.get("teleop_detector_factory_count", 0),
            "device": flight.get("runtime_device"),
            "allow_cpu_fallback": flight.get("allow_cpu_fallback"),
            "weights_sha256": flight.get("weights_sha256"),
            "model_id": self.model_id,
            "frame_count": int(flight.get("frame_count", 0)),
            "detections": int(flight.get("detections", 0)),
            "frame_rate_hz": flight.get("frame_rate_hz"),
            "source": flight.get("source")
            or f"the acceptance's own production detector over {HEAD_CAMERA_IMAGE_TOPIC}",
        }


# --- the real seams -----------------------------------------------------------------------------------


def stack_environment(session_id: str, base: Mapping | None = None) -> dict:
    from so101_demo.act.head_search_restarts import stack_environment as build

    return build(session_id, base)


def real_stack_factory(**kwargs):
    """The frozen production composition: the same transport and the same four controllers."""

    from so101_demo.act.head_search_restarts import RestartStack

    kwargs.pop("logger", None)
    return RestartStack(
        urdf_path=kwargs["urdf_path"],
        scene_path=kwargs["scene_path"],
        plugin_config_path=kwargs["plugin_config_path"],
        controller_config_path=kwargs["controller_config_path"],
        workspace=kwargs["workspace"],
        session_id=kwargs["session_id"],
        environment=stack_environment(kwargs["session_id"]),
    )


def real_ownership_probe() -> dict:
    from so101_demo.act.head_search_restarts import probe_owners

    observation = probe_owners()
    return {
        "processes": observation.get("processes") or [],
        "nodes": observation.get("nodes") or [],
        "gpu_compute_apps": observation.get("gpu_compute_apps") or [],
        "sim_clock_s": observation.get("sim_clock_s") or [],
    }


def detector_flight(
    *,
    session_id: str,
    values: Mapping,
    weights_path,
    model_id: str,
    device: str,
    frames: int,
    log,
    operating_point: Mapping | None = None,
    timeout_s: float = 150.0,
    clock=time.monotonic,
    sleep=time.sleep,
) -> dict:
    """One production detector, on CUDA, over the real head-camera frames of the owned stack."""

    import numpy as np
    import rclpy
    from rclpy.node import Node
    from sensor_msgs.msg import Image
    from so101_demo.act.head_search_restarts import TimedHeadDetector

    # the operating point is the frozen candidate's own declaration when it was supplied
    point = dict(operating_point or {}) or {"iou": float(values.get("tracking_iou", 0.5))}
    built = TimedHeadDetector.build(
        weights_path=weights_path,
        model_id=model_id,
        device=device,
        values=values,
        operating_point=point,
    )
    detector = built["runtime"]

    if not rclpy.ok():
        rclpy.init(args=None)
    # a ROS node name allows alphanumerics and underscores only; the session id carries the runtime id,
    # which is hyphenated on purpose
    node = Node("head_teleop_acceptance_" + re.sub(r"[^0-9a-zA-Z_]", "_", str(session_id)))
    frames_seen: list[dict] = []

    def on_image(message) -> None:
        if len(frames_seen) >= int(frames):
            return
        frames_seen.append(
            {
                "stamp_s": float(message.header.stamp.sec)
                + float(message.header.stamp.nanosec) * 1e-9,
                "frame_id": str(message.header.frame_id),
                "received_wall_s": clock(),
                "rgb": np.frombuffer(bytes(message.data), np.uint8).reshape(
                    int(message.height), int(message.width), 3
                ),
            }
        )

    subscription = node.create_subscription(Image, HEAD_CAMERA_IMAGE_TOPIC, on_image, 10)
    del subscription
    deadline = clock() + float(timeout_s)
    while len(frames_seen) < int(frames) and clock() < deadline:
        rclpy.spin_once(node, timeout_sec=0.1)
    if not frames_seen:
        node.destroy_node()
        raise RuntimeError(
            f"{TELEOP_FRAME_PROBE_FAILED}: {HEAD_CAMERA_IMAGE_TOPIC} published no frame"
        )

    detections = 0
    raw_sha = ""
    measured: list[dict] = []
    ages: list[float] = []
    received: list[float] = []
    # the production detector refuses a repeated source stamp, so a duplicated camera stamp is recorded
    # as skipped rather than fed to it and turned into a false detector failure
    last_stamp_ns = 0
    for frame in frames_seen:
        rgb = frame["rgb"]
        raw_sha = hashlib.sha256(rgb.tobytes()).hexdigest()
        stamp_ns = max(1, int(round(float(frame["stamp_s"]) * 1e9)))
        if stamp_ns <= last_stamp_ns:
            continue
        last_stamp_ns = stamp_ns
        found = detector.detect(
            rgb,
            session_id=session_id,
            attempt_id="teleop-acceptance",
            source_stamp_ns=stamp_ns,
            source_frame_id=frame["frame_id"],
        )
        detections += len(found or [])
        ages.append(clock() - float(frame["received_wall_s"]))
        received.append(float(frame["received_wall_s"]))
        measured.append({"stamp_s": frame["stamp_s"], "frame_id": frame["frame_id"]})
    node.destroy_node()
    # the rate is the span between the first and the last measured arrival, never one frame's own age
    span = max(1e-9, received[-1] - received[0]) if len(received) > 1 else 1e-9
    return {
        "detector_count": 1,
        "runtime_device": built.get("runtime_device"),
        "allow_cpu_fallback": False,
        "weights_sha256": built.get("weights_sha256"),
        "model_id": model_id,
        "frame_count": len(frames_seen),
        "measured_frames": len(measured),
        "detections": detections,
        "max_frame_age_s": max(ages) if ages else None,
        "frame_rate_hz": round((len(measured) - 1) / span, 4) if len(measured) > 1 else None,
        "raw_frame_sha256": raw_sha,
        "frames": measured,
        "source": f"the acceptance's own production HeadRgbDetector over {HEAD_CAMERA_IMAGE_TOPIC}",
    }


def http_probe(request: Mapping) -> dict:
    """The installed routes, called over HTTP exactly as the app serves them."""

    action = str(request.get("action"))
    base_url = str(request.get("base_url", ""))
    routes = {
        "status": ("GET", "/teleop/head-camera/status", None),
        "capture": ("POST", "/teleop/head-camera/capture", {}),
        "target": ("POST", "/teleop/head-camera/target", request.get("payload")),
        "stop": ("POST", "/teleop/head-camera/stop", request.get("payload")),
    }
    method, path, payload = routes[action]
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    http_request = urllib.request.Request(  # noqa: S310 - the acceptance'as own loopback URL
        f"{base_url}{path}", data=data, method=method
    )
    if data is not None:
        http_request.add_header("content-type", "application/json")
    try:
        with urllib.request.urlopen(http_request, timeout=10.0) as response:  # noqa: S310
            body = json.loads(response.read().decode("utf-8"))
            status = int(response.status)
    except urllib.error.HTTPError as error:
        raw = error.read().decode("utf-8")
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            body = {"raw": raw}
        status = int(error.code)
    except Exception as error:  # noqa: BLE001 - an unreachable route is a failed probe, not a crash
        return {"ok": False, "status": None, "body": {"error": repr(error)}}
    return {"ok": 200 <= status < 300, "status": status, "body": body}


def app_factory(*, command, environment, port, capture_dir, stdout_path, static_dir=None):
    """The installed unified app as its own process group, so its exit can be proven.

    The installed web bundle is passed explicitly: the app resolves it relative to the module that runs
    it, and the acceptance runs the worktree module first on PYTHONPATH (disclosed), so leaving it to the
    module's own walk would serve 503 for every page while the bundle sat in the frozen install.
    """

    stdout_path = Path(stdout_path)
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(stdout_path, "ab")  # noqa: SIM115 - one handle, closed when the app is reaped
    argv = [*command, "--host", "127.0.0.1", "--port", str(port), "--capture-dir", str(capture_dir)]
    if static_dir is not None:
        argv += ["--static-dir", str(static_dir)]
    return subprocess.Popen(  # noqa: S603 - the command is the frozen install's own entry
        argv,
        stdout=handle,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        env=dict(environment),
    )


def e2e_runner(*, base_url, evidence_root, web_dir, stdout_path, stderr_path):
    """The installed Playwright case, run through Bun with the app's own URL and evidence root."""

    if web_dir is None:
        raise ValueError(f"{TELEOP_INPUTS_INCOMPLETE}: no web directory was declared")
    environment = dict(os.environ)
    environment["SO101_TELEOP_BASE_URL"] = str(base_url)
    environment["SO101_E2E_EVIDENCE_ROOT"] = str(evidence_root)
    # Chrome's own profile singleton is an AF_UNIX socket, so the browser's temporary directory must
    # satisfy the same 103-byte limit the plan imposes on the bridge endpoints (a deep scratch TMPDIR
    # aborts the browser before the first navigation)
    browser_tmp = Path(os.environ.get("SO101_E2E_TMPDIR") or "/tmp") / f"so101-e2e-{os.getpid()}"
    browser_tmp.mkdir(parents=True, exist_ok=True)
    environment["TMPDIR"] = environment["TMP"] = environment["TEMP"] = str(browser_tmp)
    stdout_path = Path(stdout_path)
    stderr_path = Path(stderr_path)
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    with open(stdout_path, "wb") as out, open(stderr_path, "wb") as err:
        completed = subprocess.run(  # noqa: S603 - the frozen web toolchain's own script
            ["bun", "run", "test:e2e", "--", E2E_CASE],
            cwd=str(web_dir),
            stdout=out,
            stderr=err,
            env=environment,
            timeout=E2E_TIMEOUT_S,
            check=False,
        )
    command = f"cd {web_dir} && SO101_TELEOP_BASE_URL={base_url} {E2E_COMMAND}"
    return {"rc": int(completed.returncode), "command": command}


def acceptance_environment(
    *,
    final_run,
    evidence_root,
    runtime_id: str,
    socket_root,
    connection,
    ros_python,
    base: Mapping | None = None,
) -> dict:
    """The plan's own seven declarations for the installed app, verbatim."""

    environment = dict(os.environ if base is None else base)
    environment.update(
        {
            "SO101_UNIFIED_BACKEND": "mujoco_py",
            "SO101_UNIFIED_INSTALL_PREFIX": str(Path(final_run) / "install"),
            "SO101_UNIFIED_EVIDENCE_ROOT": str(evidence_root),
            "SO101_UNIFIED_RUNTIME_ID": str(runtime_id),
            "SO101_UNIFIED_SOCKET_DIR": str(socket_root),
            "SO101_HEAD_CAMERA_CONNECTION": str(connection),
            "SO101_UNIFIED_ROS_PYTHON": str(ros_python),
        }
    )
    return environment


def installed_paths(final_run) -> dict:
    """The frozen install's own composition inputs, each asserted to exist before it is declared."""

    root = Path(final_run)
    share = root / "install" / "so101_demo_py" / "share" / "so101_demo_py"
    teleop = root / "install" / "so101_teleop"
    declared = {
        "scene": share / "assets" / "mujoco" / "act" / "head_search_scene.xml",
        "urdf": share / "assets" / "mujoco" / "act" / "so101.urdf",
        "plugin_config": share / "config" / "mujoco" / "act" / "mujoco_plugins.yaml",
        "controller_config": share / "config" / "mujoco" / "act" / "ros2_controllers.yaml",
        "app": teleop / "lib" / "so101_teleop" / "so101_unified_web_server.py",
        "web_bundle": teleop / "share" / "so101_teleop" / "web" / "index.html",
    }
    missing = [name for name, path in declared.items() if not Path(path).exists()]
    if missing:
        raise ValueError(f"{TELEOP_INPUTS_INCOMPLETE}: the frozen install is missing {missing}")
    return {name: Path(path) for name, path in declared.items()}


def accept_teleop(
    *,
    run_root,
    acceptance_root,
    socket_root,
    ready_file,
    final_run,
    production_config,
    approved_bundle,
    approval_receipt=None,
    qualification_report=None,
    runtime_id,
    profile: str = PROFILE,
    device: str = "cuda",
    frames: int = DEFAULT_FRAME_PROBE,
    web_port: int = DEFAULT_WEB_PORT,
    weights_path=None,
    frozen_candidate=None,
    expected: Mapping | None = None,
    web_dir=None,
    ros_python=None,
    stdout=None,
    stderr=None,
) -> dict:
    """Assemble and run the real acceptance: the one entry point ``serve-teleop`` calls."""

    from so101_demo.act.head_search_restarts import read_runtime_of_record

    # the run root is claimed by the acceptance itself, first thing, so a refused input can never leave
    # a half-created run root behind and two starts can never both believe they won it
    root = Path(run_root)
    acceptance = Path(acceptance_root)
    bundle = verify_bundle(bundle_path=approved_bundle, production_config=production_config)
    runtime = read_runtime_of_record(final_run, production_config=production_config)
    if approval_receipt is not None and not Path(approval_receipt).is_file():
        raise TeleopAcceptanceRefused(
            TELEOP_INPUTS_INCOMPLETE, f"the approval receipt {approval_receipt} is absent"
        )
    for key, value in dict(expected or {}).items():
        if value is None:
            continue
        if str(runtime.get(key)) != str(value):
            raise TeleopAcceptanceRefused(
                TELEOP_RUNTIME_UNVERIFIED,
                f"the frozen runtime's {key} is {runtime.get(key)!r}, the expected value is {value!r}",
            )
    document = _read_json(production_config) or {}
    values = dict(document.get("values") or {})
    operating_point = {}
    if frozen_candidate is not None:
        from so101_demo.act.head_search_restarts import _operating_point

        operating_point = dict(_operating_point(frozen_candidate))
    weights = Path(weights_path or runtime.get("weight_path") or "")
    paths = installed_paths(final_run)
    python = (
        Path(ros_python) if ros_python else Path(os.environ.get("SO101_UNIFIED_ROS_PYTHON") or "")
    )
    return TeleopAcceptance(
        run_root=root,
        acceptance_root=acceptance,
        socket_root=socket_root,
        ready_file=ready_file,
        runtime=runtime,
        bundle=bundle,
        report=read_closed_report(qualification_report),
        values=values,
        runtime_id=runtime_id,
        model_id=str(document.get("runtime_id") or "head-search-runtime"),
        weights_path=weights,
        device=device,
        frames=frames,
        web_port=web_port,
        scene_path=paths["scene"],
        urdf_path=paths["urdf"],
        plugin_config_path=paths["plugin_config"],
        controller_config_path=paths["controller_config"],
        frozen_candidate_path=frozen_candidate,
        operating_point=operating_point,
        app_environment=acceptance_environment(
            final_run=final_run,
            evidence_root=acceptance,
            runtime_id=runtime_id,
            socket_root=socket_root,
            connection=ready_file,
            ros_python=python,
        ),
        app_command=[str(paths["app"])],
        static_dir=paths["web_bundle"].parent,
        web_dir=web_dir,
        profile=profile,
        stack_factory=real_stack_factory,
        detector_flight=detector_flight,
        app_factory=app_factory,
        app_probe=http_probe,
        e2e_runner=e2e_runner,
        observer=real_ownership_probe,
        stdout=stdout,
        stderr=stderr,
    ).run()


__all__ = [
    "APP_START_TIMEOUT_S",
    "BRIDGE_SOCKET_NAMES",
    "CLEANUP_ARTIFACT",
    "CONNECTION_ARTIFACT",
    "E2E_CASE",
    "E2E_COMMAND",
    "E2E_MANIFEST",
    "FAILED",
    "FIT_WARNING",
    "HEAD_CAMERA_IMAGE_TOPIC",
    "KIND",
    "MINIMUM_SCREENSHOTS",
    "OPERATION",
    "PASSED",
    "RECEIPT_ARTIFACT",
    "REFUSED",
    "SOCKET_PATH_LIMIT_BYTES",
    "STATE_ARTIFACT",
    "STOP_SAMPLES",
    "TEARDOWN_ARTIFACT",
    "TELEOP_APP_NOT_SERVED",
    "TELEOP_BUNDLE_MISMATCH",
    "TELEOP_DETECTOR_FAILED",
    "TELEOP_E2E_EVIDENCE_MISSING",
    "TELEOP_E2E_FAILED",
    "TELEOP_FRAME_PROBE_FAILED",
    "TELEOP_GPU_NOT_RELEASED",
    "TELEOP_INPUTS_INCOMPLETE",
    "TELEOP_OWNERSHIP_REFUSED",
    "TELEOP_PROBE_ERROR",
    "TELEOP_PROBE_FAILED",
    "TELEOP_REPORT_NOT_CLOSED",
    "TELEOP_REPORT_NOT_PUBLISHED",
    "TELEOP_RUN_ROOT_EXISTS",
    "TELEOP_RUNTIME_UNVERIFIED",
    "TELEOP_SOCKET_PATH_TOO_LONG",
    "TELEOP_STACK_START_FAILED",
    "TELEOP_TEARDOWN_UNPROVEN",
    "TeleopAcceptance",
    "TeleopAcceptanceRefused",
    "accept_teleop",
    "acceptance_environment",
    "acceptance_receipt",
    "app_factory",
    "bridge_cleanup_receipt",
    "bundle_values_sha256",
    "check_socket_paths",
    "detector_flight",
    "e2e_block",
    "e2e_runner",
    "http_probe",
    "installed_paths",
    "owned_groups",
    "process_group_alive",
    "read_closed_report",
    "read_e2e_evidence",
    "real_ownership_probe",
    "real_stack_factory",
    "socket_paths",
    "stack_environment",
    "teardown_receipt",
    "validate_receipt",
    "verify_bundle",
]
