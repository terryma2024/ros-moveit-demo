#!/usr/bin/env python3
# flake8: noqa: Q000
"""Drive and audit bounded SO-101 micro-lift retries on an existing stack."""

import argparse
import dataclasses
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import threading
import time
import uuid

import pytest


@dataclasses.dataclass(frozen=True)
class RetryExpectation:
    attempts: int
    reclose_offsets_rad: tuple[float, ...]
    preload_offset_rad: float = -0.006
    expect_attachment: bool = False


def run_state_machine(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["ros2", "run", "so101_gazebo_demo", "pick_place_state_machine", *args],
        check=False,
        text=True,
        capture_output=True,
        timeout=180,
    )


def load_sidecar(checkpoint: pathlib.Path) -> dict[str, object]:
    return json.loads(pathlib.Path(f"{checkpoint}.physical-grasp.json").read_text())


def wait_for_retry_phase(
    checkpoint: pathlib.Path, attempt: int, phase: str
) -> dict[str, object]:
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        try:
            record = load_sidecar(checkpoint)
        except (FileNotFoundError, json.JSONDecodeError):
            time.sleep(0.01)
            continue
        retry = record["retry"]
        if retry["attempt_index"] == attempt and retry["phase"] == phase:
            return record
        time.sleep(0.01)
    raise AssertionError(
        f"retry phase not observed: attempt={attempt} phase={phase}"
    )


def assert_retry_records(
    records: list[dict[str, object]],
    expected: RetryExpectation,
    q6_contact: float,
) -> None:
    assert len(records) == expected.attempts
    retry_records = [record["retry"] for record in records]
    assert [
        retry["current_reclose_target_q6"] - q6_contact
        for retry in retry_records[1:]
    ] == pytest.approx(expected.reclose_offsets_rad, abs=1e-9)
    assert [
        retry["micro_lift_preload_target_q6"] - q6_contact
        for retry in retry_records
    ] == pytest.approx(
        [expected.preload_offset_rad] * expected.attempts, abs=1e-9
    )


def run(command: list[str], timeout: float = 10.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command, check=False, text=True, capture_output=True, timeout=timeout
    )


def save_command(
    evidence_dir: pathlib.Path, label: str, command: list[str], timeout: float = 10.0
) -> subprocess.CompletedProcess[str]:
    result = run(command, timeout)
    payload = {
        "command": command,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "time_ns": time.time_ns(),
    }
    (evidence_dir / f"{label}.json").write_text(json.dumps(payload, indent=2))
    return result


def command_gripper(evidence_dir: pathlib.Path, label: str, q6: float) -> None:
    goal = (
        "{trajectory: {joint_names: ['6'], points: "
        f"[{{positions: [{q6:.15g}], time_from_start: {{sec: 0, nanosec: 300000000}}}}]}}}}"
    )
    result = save_command(
        evidence_dir,
        label,
        [
            "ros2",
            "action",
            "send_goal",
            "/gripper_controller/follow_joint_trajectory",
            "control_msgs/action/FollowJointTrajectory",
            goal,
        ],
        8.0,
    )
    if result.returncode != 0:
        raise AssertionError(f"gripper mutation failed: {label}")


def pin_cup_pose(
    evidence_dir: pathlib.Path, label: str, pose: dict[str, float]
) -> None:
    request = (
        "name: 'plastic_cup', position: {"
        f"x: {pose['x']}, y: {pose['y']}, z: {pose['z']}"
        "}, orientation: {"
        f"x: {pose['qx']}, y: {pose['qy']}, z: {pose['qz']}, w: {pose['qw']}"
        "}"
    )
    result = save_command(
        evidence_dir,
        label,
        [
            "gz",
            "service",
            "-s",
            "/world/so101_pick_place/set_pose",
            "--reqtype",
            "gz.msgs.Pose",
            "--reptype",
            "gz.msgs.Boolean",
            "--timeout",
            "1000",
            "--req",
            request,
        ],
        3.0,
    )
    if result.returncode != 0:
        raise AssertionError(f"Gazebo pose mutation failed: {label}")


def snapshot_streams(evidence_dir: pathlib.Path, label: str) -> None:
    commands = {
        "pose": ["gz", "model", "-m", "plastic_cup", "-p"],
        "contact": [
            "timeout",
            "2",
            "gz",
            "topic",
            "-e",
            "-t",
            "/so101/gripper_contact",
            "-n",
            "1",
        ],
        "q6": ["ros2", "topic", "echo", "/joint_states", "--once"],
    }
    for stream, command in commands.items():
        save_command(evidence_dir, f"{label}-{stream}", command, 5.0)


def expectation(case: str, attempts: int) -> RetryExpectation:
    if case == "contact-present":
        offsets = (0.0,) * max(0, attempts - 1)
    elif case == "contact-missing":
        offsets = tuple(-0.001 * index for index in range(1, attempts))
    elif case in ("mixed", "exhaustion"):
        offsets = tuple(-0.001 * ((index + 1) // 2) for index in range(1, attempts))
    else:
        offsets = ()
    return RetryExpectation(attempts, offsets)


def record_ownership(evidence_dir: pathlib.Path, session_id: str) -> None:
    facts = {
        "worktree": str(pathlib.Path.cwd().resolve()),
        "pid": os.getpid(),
        "ppid": os.getppid(),
        "ros_domain_id": os.environ.get("ROS_DOMAIN_ID", ""),
        "gz_partition": os.environ.get("GZ_PARTITION", ""),
        "simulation_session_id": session_id,
        "tmux": run(["tmux", "ls"]).stdout,
        "processes": run(["ps", "-eo", "pid,ppid,lstart,args"]).stdout,
    }
    (evidence_dir / "ownership.json").write_text(json.dumps(facts, indent=2))


def monitor_and_mutate(
    checkpoint: pathlib.Path,
    evidence_dir: pathlib.Path,
    case: str,
    expected_attempts: int,
    expected_reclose_q6: float,
    records: list[dict[str, object]],
    errors: list[BaseException],
    done: threading.Event,
) -> None:
    seen: set[tuple[int, str]] = set()
    recorded_attempts: set[int] = set()
    try:
        while not done.is_set():
            try:
                record = load_sidecar(checkpoint)
            except (FileNotFoundError, json.JSONDecodeError):
                time.sleep(0.01)
                continue
            retry = record["retry"]
            attempt = int(retry["attempt_index"])
            phase = str(retry["phase"])
            key = (attempt, phase)
            if key in seen:
                time.sleep(0.01)
                continue
            seen.add(key)
            path = evidence_dir / f"attempt-{attempt:02d}-{phase}.json"
            path.write_text(json.dumps(record, indent=2))
            snapshot_streams(evidence_dir, f"attempt-{attempt:02d}-{phase}")
            if phase == "LIFT_PENDING" and attempt not in recorded_attempts:
                records.append(record)
                recorded_attempts.add(attempt)
                if case == "contact-missing" or (
                    case in ("mixed", "exhaustion") and attempt % 2 == 1
                ):
                    command_gripper(
                        evidence_dir,
                        f"attempt-{attempt:02d}-remove-contact",
                        expected_reclose_q6 + 0.25,
                    )
                elif case != "nonretryable":
                    before = record.get("before_lift")
                    if before:
                        pin_cup_pose(
                            evidence_dir,
                            f"attempt-{attempt:02d}-pin-cup",
                            before["task_object_pose_world"],
                        )
            if attempt >= expected_attempts and phase in ("COMPLETE", "VERIFY_PENDING"):
                return
            time.sleep(0.01)
    except BaseException as error:  # propagated to the main thread
        errors.append(error)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=pathlib.Path, required=True)
    parser.add_argument("--evidence-dir", type=pathlib.Path, required=True)
    parser.add_argument(
        "--case",
        choices=(
            "contact-present",
            "contact-missing",
            "mixed",
            "exhaustion",
            "nonretryable",
        ),
        required=True,
    )
    parser.add_argument("--expected-attempts", type=int, required=True)
    parser.add_argument("--expected-reclose-q6", type=float, required=True)
    parser.add_argument("--expected-preload-q6", type=float, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.evidence_dir.mkdir(parents=True, exist_ok=False)
    session_id = f"micro-lift-{args.case}-{uuid.uuid4()}"
    record_ownership(args.evidence_dir, session_id)
    records: list[dict[str, object]] = []
    errors: list[BaseException] = []
    done = threading.Event()
    monitor = threading.Thread(
        target=monitor_and_mutate,
        args=(
            args.checkpoint,
            args.evidence_dir,
            args.case,
            args.expected_attempts,
            args.expected_reclose_q6,
            records,
            errors,
            done,
        ),
        daemon=True,
    )
    monitor.start()
    result = run_state_machine(
        "--mode",
        "execute",
        "--checkpoint",
        str(args.checkpoint),
        "--session-id",
        session_id,
    )
    done.set()
    monitor.join(timeout=5.0)
    (args.evidence_dir / "state-machine.json").write_text(
        json.dumps(
            {
                "args": result.args,
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            },
            indent=2,
        )
    )
    if errors:
        raise errors[0]
    sidecar = pathlib.Path(f"{args.checkpoint}.physical-grasp.json")
    if sidecar.exists():
        shutil.copy2(sidecar, args.evidence_dir / "final-sidecar.json")
    if args.checkpoint.exists():
        shutil.copy2(args.checkpoint, args.evidence_dir / "final-checkpoint.json")
        digest = hashlib.sha256(args.checkpoint.read_bytes()).hexdigest()
        (args.evidence_dir / "checkpoint.sha256").write_text(f"{digest}\n")
    if args.case == "nonretryable":
        assert not records
    else:
        expected = expectation(args.case, args.expected_attempts)
        q6_contact = args.expected_preload_q6 - expected.preload_offset_rad
        assert_retry_records(records, expected, q6_contact)
        assert records[-1]["retry"]["current_reclose_target_q6"] == pytest.approx(
            args.expected_reclose_q6, abs=1e-9
        )
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
