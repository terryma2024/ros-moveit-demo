"""Validate final dynamic, MuJoCo, and Planning Scene E2E evidence."""

from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile
import time
from collections.abc import Callable

import yaml

from so101_demo.application.e2e_acceptance import (
    AcceptanceReport,
    FINAL_MAX_ANGULAR_SPEED_RAD_S,
    FINAL_MAX_LINEAR_SPEED_M_S,
    FINAL_MAX_UPRIGHT_TILT_RAD,
    FINAL_SUPPORT_HEIGHT_RANGE_M,
    validate_e2e_evidence,
)
from so101_demo.ros.e2e_acceptance_readback import collect_final_readback
from so101_demo.runtime.workflow_events import EventEmitter, normalize_failure_code


def _positive_finite(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed <= 0.0:
        raise argparse.ArgumentTypeError("must be finite and positive")
    return parsed


def _nonnegative_integer(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be non-negative")
    return parsed


def _run_root(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute() or path.is_symlink() or not path.is_dir():
        raise argparse.ArgumentTypeError(
            "must be an existing absolute non-symlink directory"
        )
    return path.resolve(strict=True)


def _read_document(path: Path) -> dict[str, object]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"required evidence file is missing: {path.name}")
    document = json.loads(path.read_text(encoding="utf-8"))
    if type(document) is not dict:
        raise ValueError(f"evidence file is not an object: {path.name}")
    return document


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_document(path: Path, document: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode()
    temporary_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as stream:
            temporary_path = stream.name
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            try:
                Path(temporary_path).unlink()
            except OSError:
                pass


def _policy_document(dynamic: dict[str, object]) -> dict[str, object]:
    path_value = dynamic.get("policy_path")
    if type(path_value) is not str:
        raise ValueError("dynamic policy path is missing")
    path = Path(path_value)
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise ValueError("dynamic policy path is invalid")
    digest = _sha256(path)
    if digest != dynamic.get("policy_sha256"):
        raise ValueError("dynamic policy digest mismatch")
    policy = yaml.safe_load(path.read_bytes())
    if type(policy) is not dict or policy.get("backend") != "mujoco":
        raise ValueError("dynamic MuJoCo policy is invalid")
    planning = policy.get("planning")
    safety = policy.get("safety")
    if type(planning) is not dict or type(safety) is not dict:
        raise ValueError("dynamic policy thresholds are missing")
    manifest_path = path.with_name("manifest.yaml")
    manifest = yaml.safe_load(manifest_path.read_bytes())
    qualification = manifest["variants"]["mujoco"]["qualification_status"]
    return {
        "qualification_status": qualification,
        "sha256": digest,
        "terminal_position_tolerance_m": planning["position_tolerance_m"],
        "terminal_orientation_tolerance_rad": max(
            planning["orientation_tolerance_rad"]
        ),
        "final_pose_position_tolerance_m": safety["scene_position_tolerance_m"],
        "final_pose_orientation_tolerance_rad": safety[
            "scene_orientation_tolerance_rad"
        ],
        "support_height_range_m": list(FINAL_SUPPORT_HEIGHT_RANGE_M),
        "max_upright_tilt_rad": FINAL_MAX_UPRIGHT_TILT_RAD,
        "max_linear_speed_m_s": FINAL_MAX_LINEAR_SPEED_M_S,
        "max_angular_speed_rad_s": FINAL_MAX_ANGULAR_SPEED_RAD_S,
        "max_readback_skew_ns": round(safety["maximum_source_age_s"] * 1.0e9),
    }


def _perception_document(run_root: Path) -> dict[str, object]:
    candidates = (
        run_root / "perception" / "result.json",
        run_root / "perception" / "summary.json",
    )
    existing = [path for path in candidates if path.is_file() and not path.is_symlink()]
    if len(existing) != 1:
        raise ValueError("exactly one perception result is required")
    return _read_document(existing[0])


def _failure_report(code: str) -> AcceptanceReport:
    return AcceptanceReport(
        accepted=False,
        failures=(code,),
        physical_outcome={"stable": False},
        planning_scene_outcome={"pose_matches_mujoco": False},
    )


def main(
    arguments: list[str] | None = None,
    *,
    _collect: Callable[..., dict[str, object]] = collect_final_readback,
) -> int:
    parser = argparse.ArgumentParser(prog="e2e_acceptance")
    parser.add_argument("--run-root", required=True, type=_run_root)
    parser.add_argument("--workflow-id", required=True)
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument(
        "--expected-reset-epoch",
        required=True,
        type=_nonnegative_integer,
    )
    parser.add_argument("--timeout-s", type=_positive_finite, default=10.0)
    parser.add_argument("--emit-workflow-events", action="store_true")
    options = parser.parse_args(arguments)
    identifiers = (options.workflow_id, options.request_id, options.session_id)
    if any(
        re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", value) is None
        for value in identifiers
    ):
        parser.error("workflow, request, and session IDs must use safe characters")
    if not options.emit_workflow_events:
        parser.error("--emit-workflow-events is required for E2E acceptance")

    emitter = EventEmitter(
        options.workflow_id,
        "e2e_validator",
        sys.stdout.write,
        time.time_ns,
    )
    result_path = options.run_root / "acceptance" / "result.json"
    try:
        dynamic = _read_document(
            options.run_root / "dynamic" / "dynamic-execute-manifest.json"
        )
        perception = _perception_document(options.run_root)
        policy = _policy_document(dynamic)
        with redirect_stdout(sys.stderr):
            readback = _collect(
                session_id=options.session_id,
                reset_epoch=options.expected_reset_epoch,
                timeout_s=options.timeout_s,
            )
        input_document = {
            "expected_identity": {
                "workflow_id": options.workflow_id,
                "request_id": options.request_id,
                "simulation_session_id": options.session_id,
                "reset_epoch": options.expected_reset_epoch,
            },
            "dynamic": dynamic,
            "perception": perception,
            "mujoco_final": readback.get("mujoco_final"),
            "planning_scene_final": readback.get("planning_scene_final"),
            "policy": policy,
        }
        report = validate_e2e_evidence(input_document)
        acceptance_root = options.run_root / "acceptance"
        _write_document(acceptance_root / "mujoco-final.json", readback["mujoco_final"])
        _write_document(
            acceptance_root / "planning-scene-final.json",
            readback["planning_scene_final"],
        )
    except (KeyError, OSError, TypeError, ValueError, TimeoutError):
        report = _failure_report("E2E_EVIDENCE_REJECTED")
    try:
        _write_document(result_path, report.to_document())
    except OSError:
        emitter.emit(
            "E2E_REJECTED",
            payload={"result_path": str(result_path)},
            failure_code="E2E_VALIDATION_INTERNAL_ERROR",
        )
        return 1
    print(json.dumps(report.to_document(), sort_keys=True), file=sys.stderr, flush=True)
    if report.accepted:
        emitter.emit("E2E_ACCEPTED", payload={"result_path": str(result_path)})
        return 0
    failure_code = normalize_failure_code(
        "E2E_REJECTED",
        report.failures[0] if report.failures else None,
    )
    emitter.emit(
        "E2E_REJECTED",
        payload={"result_path": str(result_path)},
        failure_code=failure_code,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
