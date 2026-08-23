"""Adapt Teleop's stable workflow argv to the unified MuJoCo runner."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
from pathlib import Path

from ament_index_python.packages import get_package_share_directory

from ..backends.mujoco.teleop_runtime import current_evidence
from .pick_place import main as production_main


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="teleop_workflow")
    parser.add_argument("--mode", choices=("execute",), required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--session-id", required=True)
    return parser


def _safe(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value)[:80] or "session"


def evidence_root_for(session_id: str, checkpoint: Path) -> Path:
    base = Path(os.environ.get("SO101_TELEOP_EVIDENCE_BASE", "/tmp/so101-teleop-evidence"))
    if not base.is_absolute():
        raise ValueError("SO101_TELEOP_EVIDENCE_BASE must be absolute")
    return base / _safe(session_id) / _safe(checkpoint.stem)


def _rpy_from_xyzw(values: list[float]) -> tuple[float, float, float]:
    x, y, z, w = (float(value) for value in values)
    roll = math.atan2(2.0 * (w * x + y * z), 1.0 - 2.0 * (x * x + y * y))
    pitch = math.asin(max(-1.0, min(1.0, 2.0 * (w * y - z * x))))
    yaw = math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))
    return roll, pitch, yaw


def owner_result(evidence_root: Path) -> dict:
    manifest_path = evidence_root / "live-runtime-manifest.json"
    release_path = evidence_root / "release-retreat.json"
    manifest = json.loads(manifest_path.read_text())
    release = json.loads(release_path.read_text())
    final = release["final_evidence"]
    released = release["released_evidence"]
    evaluation = release["final_evaluation"]
    roll, pitch, yaw = _rpy_from_xyzw(final["cup_orientation_world_xyzw"])
    x, y, z = (float(value) for value in final["cup_position_world_m"])
    scene = release["planning_scene_readback"]
    attached = scene.get("attached_object_ids", [])
    world_counts = scene.get("world_primitive_counts", {})
    return {
        "status": manifest["status"],
        "trace": " -> ".join(manifest["completed_phases"]),
        "evidence_manifest": str(manifest_path),
        "physical_outcome": {
            "release_epoch_id": (
                f"{manifest['simulation_session_id']}:release:"
                f"{int(released['publisher_sequence'])}"
            ),
            "first_sequence": int(released["publisher_sequence"]),
            "last_sequence": int(final["publisher_sequence"]),
            "sample_count": int(evaluation["sample_count"]),
            "duration_s": float(evaluation["duration_s"]),
            "metrics": {
                str(name): float(value)
                for name, value in evaluation.get("metrics", {}).items()
            },
            "final_pose": {
                "frame_id": "world",
                "tcp_frame": "plastic_cup",
                "x_m": x,
                "y_m": y,
                "z_m": z,
                "roll_rad": roll,
                "pitch_rad": pitch,
                "yaw_rad": yaw,
            },
            "intended_support_contact": bool(final.get("table_contact")),
            "gripper_contact": bool(
                int(final.get("left_contact_count", 0))
                or int(final.get("right_contact_count", 0))
            ),
            "gazebo_attached": None,
            "moveit_attached": bool(attached),
            "world_object_synchronized": (
                not attached and int(world_counts.get("plastic_cup", 0)) > 0
            ),
            "primary_failure": evaluation.get("failure_code"),
        },
    }


def evidence_failure_code(evidence_root: Path) -> str | None:
    """Map lossless phase-evidence failures to a qualification-invalid code."""

    try:
        manifest = json.loads((evidence_root / "live-runtime-manifest.json").read_text())
        phase = str(manifest["failed_phase"])
        result = json.loads((evidence_root / f"{phase.replace('_', '-')}.json").read_text())
        index_path = result.get("dynamic_raw_index")
        if index_path:
            index = json.loads(Path(str(index_path)).read_text())
            if index.get("outcome_class") == "INVALID_EVIDENCE":
                return "TELEOP_WORKFLOW_EVIDENCE_INVALID"
        if "EvidenceInvalid" in str(result.get("error", "")):
            return "TELEOP_WORKFLOW_EVIDENCE_INVALID"
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
        return None
    return None


def production_arguments(
    *, session_id: str, reset_epoch: int, checkpoint: Path, package_share: Path
) -> list[str]:
    return [
        "--backend",
        "mujoco",
        "--mode",
        "execute",
        "--execute",
        "--session-id",
        session_id,
        "--expected-reset-epoch",
        str(reset_epoch),
        "--evidence-root",
        str(evidence_root_for(session_id, checkpoint)),
        "--motion-policy",
        str(package_share / "config/policies/light_cup_wall_pick/v1/mujoco.yaml"),
        "--contact-policy",
        str(package_share / "config/mujoco/contact_calibration.yaml"),
    ]


def main(arguments: list[str] | None = None) -> int:
    options = build_parser().parse_args(arguments)
    try:
        evidence = current_evidence(options.session_id)
    except Exception as error:
        print("status=ERROR")
        print("current_state=ERROR")
        print("failure=STALE_OR_MISMATCHED_MUJOCO_EVIDENCE")
        print(f"failure_message={error}")
        return 1
    share = Path(get_package_share_directory("so101_demo_py"))
    result = production_main(
        production_arguments(
            session_id=options.session_id,
            reset_epoch=evidence.reset_epoch,
            checkpoint=options.checkpoint,
            package_share=share,
        )
    )
    if result != 0:
        failure_code = evidence_failure_code(evidence_root_for(options.session_id, options.checkpoint))
        if failure_code is not None:
            print(f"failure={failure_code}")
        return result
    try:
        print(json.dumps(owner_result(evidence_root_for(options.session_id, options.checkpoint))))
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        print("failure=TELEOP_WORKFLOW_EVIDENCE_INVALID")
        print(f"failure_message={error}")
        return 1
    return 0
