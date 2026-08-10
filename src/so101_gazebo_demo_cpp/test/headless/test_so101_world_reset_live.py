#!/usr/bin/env python3
"""Run four real SO-101 Gazebo/MoveIt reset states without GUI processes."""

import math
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path


CANONICAL = (0.02, -0.28, 0.181, 0.0, 0.0, 0.0)
HOME_JOINTS = {"1": 0.0, "2": 0.0, "3": 0.0, "4": 0.0, "5": 0.0, "6": 0.0}
SCENARIOS = (
    ("detached", False, False),
    ("gazebo_only", True, False),
    ("moveit_only", False, True),
    ("both_attached", True, True),
)


def run(command, environment, timeout=15, check=True):
    result = subprocess.run(
        command,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        check=False,
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"command failed ({result.returncode}): {' '.join(command)}\n{result.stdout}"
        )
    return result.stdout


def wait_for(description, predicate, timeout=45):
    deadline = time.monotonic() + timeout
    last = ""
    while time.monotonic() < deadline:
        try:
            ok, last = predicate()
            if ok:
                return last
        except (RuntimeError, subprocess.TimeoutExpired) as error:
            last = str(error)
        time.sleep(0.25)
    raise RuntimeError(f"readiness timeout: {description}; last={last}")


def moveit_state(environment):
    output = run(
        ["ros2", "run", "so101_gazebo_demo_cpp", "so101_moveit_scene", "observe"],
        environment,
        timeout=15,
    )
    line = next((line for line in output.splitlines() if "task_object_in_world=" in line), "")
    if not line:
        raise RuntimeError(f"MoveIt query did not emit state: {output}")
    return line


def gazebo_attachment(environment):
    output = run(
        ["timeout", "3", "gz", "topic", "-e", "-t", "/so101/object_attached", "-n", "1"],
        environment,
        timeout=5,
    )
    if re.search(r'data:\s*"?attached"?', output):
        return True, output.strip()
    if re.search(r'data:\s*"?detached"?', output):
        return False, output.strip()
    raise RuntimeError(f"unknown Gazebo attachment evidence: {output}")


def gazebo_pose(environment):
    output = run(["gz", "model", "-m", "plastic_cup", "-p"], environment, timeout=5)
    match = re.search(
        r"Pose \[ XYZ \(m\) \] \[ RPY \(rad\) \]:\s*"
        r"\[\s*([-+0-9.eE]+)\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)\s*\]\s*"
        r"\[\s*([-+0-9.eE]+)\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)\s*\]",
        output,
    )
    if not match:
        raise RuntimeError(f"unable to parse Gazebo pose: {output}")
    return tuple(map(float, match.groups())), output.strip()


def canonical_pose(pose):
    return math.dist(pose[:3], CANONICAL[:3]) <= 0.002 and math.dist(
        pose[3:], CANONICAL[3:]
    ) <= 0.02


def pose_errors(pose):
    return math.dist(pose[:3], CANONICAL[:3]), math.dist(pose[3:], CANONICAL[3:])


def require_moveit(line, attached):
    expected = "true" if attached else "false"
    if f"task_object_attached={expected}" not in line:
        raise RuntimeError(f"wrong MoveIt attachment fact: {line}")
    if attached:
        required = ("task_object_in_world=false", "attached_link=gripper", "touch_links=gripper,jaw")
    else:
        required = (
            "task_object_in_world=true",
            "attached_link=-",
            "touch_links=-",
            "task_object_pose=0.02,-0.28,0.181,0,0,0,1",
            "table_in_world=true",
            "table_pose=0,-0.2,0.1,0,0,0,1",
        )
    required += (
        "pedestal_in_world=true",
        "pedestal_pose=0,0,0.17,0,0,0,1",
    )
    missing = [token for token in required if token not in line]
    if missing:
        raise RuntimeError(f"MoveIt state missing {missing}: {line}")


def joint_state(environment):
    output = run(["ros2", "topic", "echo", "/joint_states", "--once"], environment)

    def sequence(label, next_label):
        match = re.search(rf"{label}:\n((?:- .+\n)+){next_label}:", output)
        if not match:
            raise RuntimeError(f"joint state missing {label}: {output}")
        return [line[2:].strip().strip("'") for line in match.group(1).splitlines()]

    names = sequence("name", "position")
    positions = [float(value) for value in sequence("position", "velocity")]
    velocities = [float(value) for value in sequence("velocity", "effort")]
    if len(names) != 6 or len(positions) != 6 or len(velocities) != 6:
        raise RuntimeError(f"incomplete joint state: {output}")
    return dict(zip(names, positions)), dict(zip(names, velocities)), output


def controllers_active(environment):
    output = run(["ros2", "control", "list_controllers"], environment, timeout=5)
    required = ("joint_state_broadcaster", "arm_controller", "gripper_controller")
    active = all(
        re.search(rf"^{re.escape(name)}\s+.+\bactive\b", output, re.MULTILINE)
        for name in required
    )
    return active, output.strip()


def require_robot_home(environment):
    positions, velocities, output = joint_state(environment)
    for name, target in HOME_JOINTS.items():
        if name not in positions or abs(positions[name] - target) > 0.002:
            raise RuntimeError(f"joint {name} not home: {output}")
        if name not in velocities or abs(velocities[name]) > 0.01:
            raise RuntimeError(f"joint {name} not stationary: {output}")
    return positions, velocities


def disturb_robot(environment):
    arm_goal = (
        "{trajectory: {joint_names: ['1', '2', '3', '4', '5'], points: "
        "[{positions: [0.15, -0.1, 0.1, -0.1, 0.1], "
        "time_from_start: {sec: 2, nanosec: 0}}]}}"
    )
    gripper_goal = (
        "{trajectory: {joint_names: ['6'], points: "
        "[{positions: [1.2], time_from_start: {sec: 1, nanosec: 0}}]}}"
    )
    run(["ros2", "action", "send_goal", "/arm_controller/follow_joint_trajectory",
         "control_msgs/action/FollowJointTrajectory", arm_goal], environment, timeout=12)
    run(["ros2", "action", "send_goal", "/gripper_controller/follow_joint_trajectory",
         "control_msgs/action/FollowJointTrajectory", gripper_goal], environment, timeout=12)


def terminate(processes):
    def group_alive(process):
        try:
            os.killpg(process.pid, 0)
            return True
        except ProcessLookupError:
            return False

    for process in reversed(processes):
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    deadline = time.monotonic() + 8
    while any(group_alive(process) for process in processes) and time.monotonic() < deadline:
        time.sleep(0.1)
    for process in reversed(processes):
        if group_alive(process):
            os.killpg(process.pid, signal.SIGKILL)
        if process.poll() is None:
            process.wait(timeout=3)


def main():
    environment = os.environ.copy()
    environment["ROS_DOMAIN_ID"] = str(100 + os.getpid() % 100)
    environment["GZ_PARTITION"] = f"so101_reset_{uuid.uuid4().hex}"
    processes = []
    log_dir = Path(tempfile.mkdtemp(prefix="so101-reset-live-"))
    succeeded = False
    try:
            for name, command in (
                (
                    "gazebo",
                    [
                        "ros2", "launch", "so101_gazebo_demo_cpp", "so101_gazebo.launch.py",
                        "headless:=true",
                    ],
                ),
                (
                    "moveit",
                    [
                        "ros2", "launch", "so101_gazebo_demo_cpp",
                        "so101_move_group_headless.launch.py",
                    ],
                ),
            ):
                log = (log_dir / f"{name}.log").open("w", encoding="utf-8")
                processes.append(
                    subprocess.Popen(
                        command,
                        env=environment,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        start_new_session=True,
                        text=True,
                    )
                )

            wait_for(
                "Gazebo set_pose and durable attachment topics",
                lambda: (
                    "/world/so101_pick_place/set_pose"
                    in run(["gz", "service", "-l"], environment, timeout=3)
                    and "/so101/object_attached"
                    in run(["gz", "topic", "-l"], environment, timeout=3),
                    "Gazebo interfaces",
                ),
            )
            wait_for(
                "move_group node",
                lambda: (
                    "/move_group" in run(["ros2", "node", "list"], environment, timeout=3),
                    "ROS nodes",
                ),
            )
            wait_for(
                "all SO-101 controllers active",
                lambda: controllers_active(environment),
            )
            wait_for(
                "complete six-joint state",
                lambda: (
                    set(joint_state(environment)[0]) == set(HOME_JOINTS),
                    joint_state(environment)[2],
                ),
            )

            for name, seed_gazebo, seed_moveit in SCENARIOS:
                run(
                    ["ros2", "run", "so101_gazebo_demo_cpp", "reset_so101_world"],
                    environment,
                    timeout=25,
                )
                if name == "detached":
                    disturb_robot(environment)
                if seed_gazebo:
                    run(
                        [
                            "gz", "topic", "-t", "/so101/attach_object", "-m",
                            "gz.msgs.Empty", "-p", "unused: true",
                        ],
                        environment,
                    )
                    wait_for(
                        f"{name} Gazebo attach",
                        lambda: (
                            gazebo_attachment(environment)[0],
                            gazebo_attachment(environment)[1],
                        ),
                        timeout=8,
                    )
                if seed_moveit:
                    output = run(
                        [
                            "ros2",
                            "run",
                            "so101_gazebo_demo_cpp",
                            "so101_moveit_scene",
                            "attach",
                        ],
                        environment,
                        timeout=20,
                    )
                    line = next(line for line in output.splitlines() if "task_object_in_world=" in line)
                    require_moveit(line, True)

                gazebo_before, gazebo_before_text = gazebo_attachment(environment)
                moveit_before = moveit_state(environment)
                if gazebo_before != seed_gazebo:
                    raise RuntimeError(f"{name}: wrong Gazebo seed: {gazebo_before_text}")
                require_moveit(moveit_before, seed_moveit)
                pose_before, _ = gazebo_pose(environment)
                print(
                    f"BEFORE {name}: gazebo_attached={str(gazebo_before).lower()} "
                    f"gazebo_pose={pose_before} moveit={moveit_before}"
                )

                reset_output = run(
                    ["ros2", "run", "so101_gazebo_demo_cpp", "reset_so101_world"],
                    environment,
                    timeout=25,
                )
                expected_success = (
                    "Gazebo, MoveIt, arm, and gripper converged to canonical SO-101 reset facts"
                )
                if expected_success not in reset_output:
                    raise RuntimeError(f"{name}: reset success contract missing: {reset_output}")
                home_positions, home_velocities = require_robot_home(environment)
                gazebo_after, gazebo_after_text = gazebo_attachment(environment)
                pose_after, pose_after_text = gazebo_pose(environment)
                moveit_after = moveit_state(environment)
                if gazebo_after or not canonical_pose(pose_after):
                    raise RuntimeError(
                        f"{name}: Gazebo did not reset: {gazebo_after_text}\n{pose_after_text}"
                    )
                require_moveit(moveit_after, False)
                position_error, orientation_error = pose_errors(pose_after)
                print(
                    f"AFTER {name}: gazebo_attached=false gazebo_pose={pose_after} "
                    f"position_error={position_error:.9f} "
                    f"orientation_error={orientation_error:.9f} moveit={moveit_after}"
                )
                print(
                    f"PASS {name}: before(gazebo={str(seed_gazebo).lower()},"
                    f"moveit={str(seed_moveit).lower()}) -> detached canonical; "
                    f"joints={home_positions} velocities={home_velocities}; "
                    f"reset={reset_output.strip().splitlines()[-1]}"
                )
            succeeded = True
    except Exception:
        print(f"FAIL logs preserved at {log_dir}", file=sys.stderr)
        for log_file in sorted(log_dir.glob("*.log")):
            print(f"--- {log_file.name} tail ---", file=sys.stderr)
            print("\n".join(log_file.read_text(errors="replace").splitlines()[-80:]),
                  file=sys.stderr)
        raise
    finally:
        terminate(processes)
        if succeeded:
            shutil.rmtree(log_dir)
    print("PASS: all SO-101 reset launch process groups cleaned")


if __name__ == "__main__":
    main()
