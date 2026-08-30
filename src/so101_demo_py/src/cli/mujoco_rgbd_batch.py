"""Public visible macOS RESET_WORLD RGB-D batch runner."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path


def _absolute_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise argparse.ArgumentTypeError("must be an absolute path")
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="so101_mujoco_rgbd_batch")
    parser.add_argument("--points", type=Path, required=True)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--evidence-root", type=_absolute_path, required=True)
    parser.add_argument("--dynamic-policy", type=Path)
    parser.add_argument("--attach-existing-stack", action="store_true")
    parser.add_argument("--mujoco-pid", type=int)
    parser.add_argument("--include-teleop", action="store_true")
    parser.set_defaults(headless=False)
    return parser


def result_exit_code(result) -> int:
    from ..application.task_batch import BatchStatus

    return 0 if result.status is BatchStatus.SUCCEEDED else 1


def _wait_for_task_station(
    timeout_s: float = 240.0,
    *,
    runner=None,
    monotonic=time.monotonic,
    sleep=time.sleep,
) -> None:
    from ..application.qualification_stack import ros2_command

    del sleep
    command_runner = subprocess.run if runner is None else runner
    deadline = monotonic() + timeout_s

    def run_stage(name: str, command: list[str], *, maximum_s: float | None = None):
        remaining = deadline - monotonic()
        if remaining <= 0.0:
            raise TimeoutError(f"task station readiness timed out at {name}")
        process_timeout = remaining if maximum_s is None else min(remaining, maximum_s)
        try:
            completed = command_runner(
                command,
                capture_output=True,
                text=True,
                timeout=max(1.0, process_timeout),
            )
        except subprocess.TimeoutExpired as error:
            output = str(error.stdout or error.stderr or "").strip()[-1000:]
            raise TimeoutError(
                f"task station readiness timed out at {name}: {output}"
            ) from error
        if completed.returncode != 0:
            output = "\n".join(
                part.strip()
                for part in (completed.stdout, completed.stderr)
                if part and part.strip()
            )[-1000:]
            raise TimeoutError(
                f"task station readiness failed at {name} "
                f"(exit {completed.returncode}): {output}"
            )
        return completed

    remaining = max(1.0, deadline - monotonic())
    run_stage(
        "controllers_and_moveit",
        ros2_command(
            "run",
            "so101_demo_py",
            "motion_stack_ready",
            "--timeout-s",
            f"{remaining:.3f}",
        ),
    )
    joint_timeout = max(1, min(15, int(deadline - monotonic())))
    joint_state = run_stage(
        "joint_states",
        ros2_command(
            "topic",
            "echo",
            "--once",
            "--timeout",
            str(joint_timeout),
            "--no-daemon",
            "/joint_states",
        ),
        maximum_s=float(joint_timeout + 10),
    )
    if "name:" not in joint_state.stdout:
        raise TimeoutError(
            "task station readiness failed at joint_states: sample had no joint names"
        )
    run_stage(
        "planning_scene",
        ros2_command(
            "run",
            "so101_demo_py",
            "scene_setup",
            "--backend",
            "mujoco",
            "observe",
        ),
        maximum_s=45.0,
    )


def main(arguments: list[str] | None = None) -> int:
    options = build_parser().parse_args(arguments)
    if options.attach_existing_stack and not options.mujoco_pid:
        print(
            json.dumps(
                {
                    "status": "ERROR",
                    "failure": "ATTACHED_MUJOCO_PID_REQUIRED",
                }
            )
        )
        return 1
    if not options.points.is_file():
        print(json.dumps({"status": "ERROR", "failure": "POINTS_FILE_MISSING"}))
        return 1

    from ament_index_python.packages import get_package_share_directory

    from ..application.task_batch import BatchRequest, run_task_batch
    from ..backends.mujoco.lifecycle import resume_physics
    from ..core.dynamic_pick_policy import load_dynamic_pick_template
    from ..runtime.task_artifacts import TaskArtifactRegistry
    from ..runtime.task_batch_runtime import (
        OwnedPointProcesses,
        RosGraphProbe,
        RosTaskBatchRuntime,
    )
    from ..runtime.task_point_config import load_task_point_list
    from ..runtime.task_stack import (
        PersistentTaskStack,
        default_task_station_config,
    )
    from ..runtime.viewer_capture import MacViewerCapture

    share = Path(get_package_share_directory("so101_demo_py"))
    policy = options.dynamic_policy or (
        share / "config/policies/dynamic_cup_pick/v1/mujoco.yaml"
    )
    owned_stack = None
    result = None
    try:
        template = load_dynamic_pick_template(policy, expected_backend="mujoco")
        points = load_task_point_list(options.points, template.workspace_bounds_m)
        registry = TaskArtifactRegistry(options.evidence_root)
        if options.attach_existing_stack:
            mujoco_pid = options.mujoco_pid
        else:
            owned_stack = PersistentTaskStack()
            owned_stack.start(
                default_task_station_config(
                    options.session_id,
                    options.evidence_root,
                    include_teleop=options.include_teleop,
                )
            )
            _wait_for_task_station()
            mujoco_pid = owned_stack.wait_for_descendant("ros2_control_node", 120.0)
        viewer = MacViewerCapture.from_package(int(mujoco_pid), share)
        runtime = RosTaskBatchRuntime(
            OwnedPointProcesses(),
            RosGraphProbe(),
            session_id=options.session_id,
            points_file=options.points,
            policy_file=policy,
            evidence_root=options.evidence_root,
            viewer_capture=viewer,
            resume=lambda: resume_physics(None),
        )
        result = run_task_batch(
            BatchRequest(
                options.batch_id,
                options.session_id,
                points.points,
                options.evidence_root,
            ),
            runtime,
            registry,
        )
        document = {
            "status": result.status.value,
            "batch_id": result.batch_id,
            "manifest": str(result.manifest_path),
            "point_statuses": [point.status.value for point in result.points],
        }
    except Exception as error:
        document = {
            "status": "ERROR",
            "failure": "MUJOCO_RGBD_BATCH_FAILED",
            "message": str(error),
        }
    finally:
        if owned_stack is not None:
            try:
                owned_stack.shutdown()
            except Exception as error:
                document = {
                    "status": "ERROR",
                    "failure": "TASK_STACK_CLEANUP_FAILED",
                    "message": str(error),
                }
                result = None
    print(json.dumps(document, sort_keys=True), flush=True)
    return 1 if result is None else result_exit_code(result)


if __name__ == "__main__":
    raise SystemExit(main())
