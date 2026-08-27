"""Shared CLI owner for MuJoCo and Gazebo reset transactions."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from pathlib import Path

from ament_index_python.packages import get_package_share_directory

from ..backends.mujoco.client import FreeJointResetOverride
from ..backends.mujoco.teleop_runtime import CUP_START, transactional_reset
from ..ports.reset import TransactionalResetReceipt
from .scene_setup import execute_scene_operation


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="teleop_reset")
    parser.add_argument("--backend", choices=("mujoco", "gazebo"), default="mujoco")
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--keyframe", default="task_start")
    parser.add_argument(
        "--cup-position-world-m",
        type=float,
        nargs=3,
        metavar=("X", "Y", "Z"),
    )
    parser.add_argument("--evidence-file", type=Path)
    return parser


def _atomic_json(path: Path, document: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def execute_gazebo_reset(session_id: str) -> TransactionalResetReceipt:
    from ..control.trajectory.reset_control import run_gazebo_reset

    share = Path(get_package_share_directory("so101_demo_py"))
    return run_gazebo_reset(share, session_id)


def execute_mujoco_reset(
    session_id: str,
    *,
    keyframe: str,
    cup_position_world_m: tuple[float, float, float] | None = None,
):
    """Reset physical state, then restore MoveIt's canonical scene shadow."""

    if cup_position_world_m is None:
        receipt = transactional_reset(session_id, keyframe=keyframe)
    else:
        override = FreeJointResetOverride(
            name="plastic_cup",
            position_world_m=cup_position_world_m,
        )
        receipt = transactional_reset(
            session_id,
            keyframe=keyframe,
            expected_object_position=cup_position_world_m,
            free_joint_overrides=(override,),
        )
    scene_receipt = execute_scene_operation("mujoco", "setup")
    if not scene_receipt.success:
        raise RuntimeError(
            "planning scene synchronization failed: "
            f"{scene_receipt.failure_code or scene_receipt.phase}"
        )
    return receipt, scene_receipt


def main(arguments: list[str] | None = None) -> int:
    options = build_parser().parse_args(arguments)
    requested_position = (
        tuple(options.cup_position_world_m)
        if options.cup_position_world_m is not None
        else CUP_START
    )
    if options.backend == "mujoco":
        try:
            if options.cup_position_world_m is None:
                receipt, scene_receipt = execute_mujoco_reset(
                    options.session_id, keyframe=options.keyframe
                )
            else:
                receipt, scene_receipt = execute_mujoco_reset(
                    options.session_id,
                    keyframe=options.keyframe,
                    cup_position_world_m=requested_position,
                )
        except Exception as error:
            document: dict[str, object] = {
                "backend": "mujoco",
                "success": False,
                "phase": "TRANSACTION",
                "failure_code": "TRANSACTIONAL_RESET_FAILED",
                "requested_object_position_world_m": requested_position,
                "evidence": {"message": str(error)},
            }
            print(json.dumps(document, sort_keys=True), flush=True)
            return 1
        document = {
            "backend": "mujoco",
            "success": True,
            "phase": "VERIFY_FINAL",
            "failure_code": None,
            "status": "SUCCEEDED",
            "simulation_session_id": receipt.simulation_session_id,
            "preserve_session": True,
            "old_epoch": receipt.old_epoch,
            "new_epoch": receipt.new_epoch,
            "simulation_step": receipt.simulation_step,
            "keyframe": receipt.keyframe,
            "requested_object_position_world_m": requested_position,
            "planning_scene": asdict(scene_receipt),
        }
    else:
        receipt = execute_gazebo_reset(options.session_id)
        document = asdict(receipt)
    if options.evidence_file is not None:
        _atomic_json(options.evidence_file, document)
    print(json.dumps(document, sort_keys=True), flush=True)
    return 0 if bool(document["success"]) else 1
