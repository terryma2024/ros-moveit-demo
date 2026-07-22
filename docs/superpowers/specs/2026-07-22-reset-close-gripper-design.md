# Reset Script Close-Gripper Design

## Goal

Extend `src/panda_gazebo_demo/scripts/reset_coke.sh` so a reset leaves the Coke at its
configured pose, the Panda arm at the ready pose, and the gripper closed.

## Behavior

After the arm trajectory succeeds, the script sends a
`control_msgs/action/GripperCommand` goal to `/panda_hand_controller/gripper_cmd` with
`position: 0.0` and `max_effort: 0.0`. The action name and timeout remain overridable by
environment variables. A missing action server, rejected command, timeout, or non-successful
action result causes the script to return a non-zero status.

## Verification

A shell regression test runs the reset script with fake `gz` and `ros2` commands. It verifies
that both arm and gripper goals are sent, that the gripper goal commands position `0.0`, and
that the gripper goal follows the arm goal. The test is registered with CTest.
