#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
temporary_directory="$(mktemp -d)"
trap 'rm -rf "${temporary_directory}"' EXIT

python3 - "${script_dir}/../../launch/panda_gazebo.launch.py" <<'PY'
import ast
import pathlib
import sys

module = ast.parse(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8'))
runtime_defaults = None
for node in ast.walk(module):
    if not isinstance(node, ast.Assign):
        continue
    if any(
        isinstance(target, ast.Name) and target.id == 'runtime_defaults'
        for target in node.targets
    ):
        runtime_defaults = ast.literal_eval(node.value)
        break
assert runtime_defaults is not None
assert runtime_defaults.get('motion_start_joint_tolerance') == '0.010'
PY

expect_failure() {
  if "$@" >/dev/null 2>&1; then
    printf 'Expected command to fail: %q' "$1" >&2
    printf ' %q' "${@:2}" >&2
    printf '\n' >&2
    return 1
  fi
}

cat >"${temporary_directory}/gazebo.txt" <<'EOF'
Pose [ XYZ (m) ] [ RPY (rad) ]: [ 0.300000 0.000000 0.836000 ] [ 0 0 0 ]
EOF
cat >"${temporary_directory}/attachment.txt" <<'EOF'
data: "detached"
EOF
cat >"${temporary_directory}/joints.txt" <<'EOF'
name:
- panda_joint1
- panda_finger_joint1
- panda_finger_joint2
position:
- 0.0
- 0.04
- 0.04
velocity:
- 0.0
- 0.0
- 0.0
effort:
- 0.0
- 0.0
- 0.0
EOF
cat >"${temporary_directory}/scene.txt" <<'EOF'
scene=moveit_msgs.srv.GetPlanningScene_Response(scene=moveit_msgs.msg.PlanningScene(world=moveit_msgs.msg.PlanningSceneWorld(collision_objects=[moveit_msgs.msg.CollisionObject(pose=geometry_msgs.msg.Pose(position=geometry_msgs.msg.Point(x=0.3, y=0.0, z=0.836), orientation=geometry_msgs.msg.Quaternion(x=0.0, y=0.0, z=0.0, w=1.0)), id='coke')]), robot_state=moveit_msgs.msg.RobotState(attached_collision_objects=[])))
EOF

python3 "${script_dir}/capture_resume_snapshot.py" \
  "${temporary_directory}/gazebo.txt" \
  "${temporary_directory}/attachment.txt" \
  "${temporary_directory}/joints.txt" \
  "${temporary_directory}/scene.txt" \
  "${temporary_directory}/before.json"
cp "${temporary_directory}/before.json" "${temporary_directory}/after.json"
python3 "${script_dir}/assert_resume_snapshot_unchanged.py" \
  "${temporary_directory}/before.json" "${temporary_directory}/after.json"

python3 - "${temporary_directory}/after.json" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
snapshot = json.loads(path.read_text(encoding='utf-8'))
snapshot['gazebo_coke_pose'][0] += 0.01
path.write_text(json.dumps(snapshot), encoding='utf-8')
PY
expect_failure python3 "${script_dir}/assert_resume_snapshot_unchanged.py" \
  "${temporary_directory}/before.json" "${temporary_directory}/after.json"

cat >"${temporary_directory}/attachment_attached.txt" <<'EOF'
data: "attached"
EOF
cat >"${temporary_directory}/scene_attached.txt" <<'EOF'
scene=moveit_msgs.srv.GetPlanningScene_Response(scene=moveit_msgs.msg.PlanningScene(robot_state=moveit_msgs.msg.RobotState(attached_collision_objects=[moveit_msgs.msg.AttachedCollisionObject(object=moveit_msgs.msg.CollisionObject(pose=geometry_msgs.msg.Pose(position=geometry_msgs.msg.Point(x=0.0, y=0.0, z=0.066), orientation=geometry_msgs.msg.Quaternion(x=0.0, y=0.0, z=0.0, w=1.0)), id='coke'))]), world=moveit_msgs.msg.PlanningSceneWorld(collision_objects=[])))
EOF
cat >"${temporary_directory}/tcp.txt" <<'EOF'
FAULT_FIXTURE_EXECUTED_TCP_POSE x=0.300000000 y=0.000000000 z=0.900000000 qx=1.000000000 qy=0.000000000 qz=0.000000000 qw=0.000000000
EOF
python3 "${script_dir}/capture_resume_snapshot.py" \
  "${temporary_directory}/gazebo.txt" \
  "${temporary_directory}/attachment_attached.txt" \
  "${temporary_directory}/joints.txt" \
  "${temporary_directory}/scene_attached.txt" \
  "${temporary_directory}/attached.json" \
  "${temporary_directory}/tcp.txt"
python3 - "${temporary_directory}/attached.json" <<'PY'
import json
import pathlib
import sys

snapshot = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8'))
assert snapshot['gazebo_attached']
assert snapshot['moveit_coke_attached']
assert not snapshot['moveit_coke_in_world']
assert snapshot['tcp_pose'] == [0.3, 0.0, 0.9, 1.0, 0.0, 0.0, 0.0]
PY

cat >"${temporary_directory}/tcp_rpy.txt" <<'EOF'
EXECUTED_END_TCP_POSE state=MOVE_ABOVE_OBJECT x=0.300000000 y=0.000000000 z=0.987000000 roll=3.141592654 pitch=0.000000000 yaw=0.000000000
EXECUTED_END_TCP_POSE state=ATTACH_MOVEIT x=0.300000000 y=0.000000000 z=0.870000000 roll=3.141592654 pitch=0.000000000 yaw=0.000000000
EOF
python3 "${script_dir}/capture_resume_snapshot.py" \
  "${temporary_directory}/gazebo.txt" \
  "${temporary_directory}/attachment_attached.txt" \
  "${temporary_directory}/joints.txt" \
  "${temporary_directory}/scene_attached.txt" \
  "${temporary_directory}/attached_rpy.json" \
  "${temporary_directory}/tcp_rpy.txt"
python3 - "${temporary_directory}/attached_rpy.json" <<'PY'
import json
import math
import pathlib
import sys

snapshot = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8'))
assert snapshot['tcp_pose'][:3] == [0.3, 0.0, 0.87]
assert math.isclose(abs(snapshot['tcp_pose'][3]), 1.0, abs_tol=1e-9)
PY

cat >"${temporary_directory}/checkpoint.json" <<'EOF'
{
  "schema_version": 3,
  "sequence": 7,
  "phase": "FORWARD",
  "last_completed_state": "MOVE_ABOVE_OBJECT",
  "next_state": "DESCEND",
  "expected": {
    "joint_positions": {},
    "moveit_world_object_poses": {"coke": {}},
    "required_world_objects": ["coke", "table"]
  }
}
EOF
cp "${temporary_directory}/checkpoint.json" "${temporary_directory}/checkpoint.after.json"
cat >"${temporary_directory}/plan.log" <<'EOF'
CHECKPOINT_PHASE=FORWARD CHECKPOINT_SEQUENCE=7 NEXT_STATE=DESCEND resume_load=1
TARGET_TCP_POSE state=DESCEND next_state=CLOSE_GRIPPER x=0.3 y=0 z=0.87 roll=3.141593 pitch=0 yaw=0
START_TCP_POSE state=DESCEND next_state=CLOSE_GRIPPER x=0.3 y=0 z=0.987 roll=3.141593 pitch=0 yaw=0
PLANNED_END_TCP_POSE state=DESCEND next_state=CLOSE_GRIPPER x=0.3 y=0 z=0.87 roll=3.141593 pitch=0 yaw=0
CARTESIAN_FRACTION state=DESCEND value=1.0
TRAJECTORY_POINTS state=DESCEND value=20
MAX_JOINT_JUMP state=DESCEND value=0.02
TRAJECTORY_DURATION state=DESCEND value=1.0
Run completed: status=PLAN_ONLY_COMPLETE current_state=DESCEND next_state=CLOSE_GRIPPER transitions=0
EOF
python3 "${script_dir}/assert_plan_only_resume.py" \
  "${temporary_directory}/plan.log" DESCEND FORWARD \
  "${temporary_directory}/checkpoint.json" \
  "${temporary_directory}/checkpoint.after.json"
cp "${temporary_directory}/plan.log" "${temporary_directory}/plan_second.log"
python3 "${script_dir}/assert_plan_only_tcp_unchanged.py" \
  "${temporary_directory}/plan.log" \
  "${temporary_directory}/plan_second.log" DESCEND

cat >"${temporary_directory}/named_plan.log" <<'EOF'
CHECKPOINT_PHASE=FORWARD CHECKPOINT_SEQUENCE=7 NEXT_STATE=RETREAT resume_load=1
NAMED_JOINT_TARGET state=RETREAT target=ready
START_TCP_POSE state=RETREAT next_state=DONE x=0.3 y=0.2 z=0.87 roll=3.141593 pitch=0 yaw=0
PLANNED_END_TCP_POSE state=RETREAT next_state=DONE x=0.307 y=0 z=1.262 roll=3.141593 pitch=0 yaw=0
TRAJECTORY_POINTS state=RETREAT value=69
Run completed: status=PLAN_ONLY_COMPLETE current_state=RETREAT next_state=DONE transitions=0
EOF
cp "${temporary_directory}/checkpoint.json" \
  "${temporary_directory}/named_checkpoint.json"
python3 - "${temporary_directory}/named_checkpoint.json" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
checkpoint = json.loads(path.read_text(encoding='utf-8'))
checkpoint['next_state'] = 'RETREAT'
path.write_text(json.dumps(checkpoint), encoding='utf-8')
PY
cp "${temporary_directory}/named_checkpoint.json" \
  "${temporary_directory}/named_checkpoint.after.json"
python3 "${script_dir}/assert_plan_only_resume.py" \
  "${temporary_directory}/named_plan.log" RETREAT FORWARD \
  "${temporary_directory}/named_checkpoint.json" \
  "${temporary_directory}/named_checkpoint.after.json"

sed 's/MAX_JOINT_JUMP state=DESCEND value=0.02/MAX_JOINT_JUMP state=DESCEND value=0.21/' \
  "${temporary_directory}/plan.log" >"${temporary_directory}/invalid_jump.log"
expect_failure python3 "${script_dir}/assert_plan_only_resume.py" \
  "${temporary_directory}/invalid_jump.log" DESCEND FORWARD \
  "${temporary_directory}/checkpoint.json" \
  "${temporary_directory}/checkpoint.after.json"

sed 's/PLANNED_END_TCP_POSE state=DESCEND next_state=CLOSE_GRIPPER x=0.3 y=0 z=0.87/PLANNED_END_TCP_POSE state=DESCEND next_state=CLOSE_GRIPPER x=0.3 y=0 z=0.80/' \
  "${temporary_directory}/plan.log" >"${temporary_directory}/wrong_endpoint.log"
expect_failure python3 "${script_dir}/assert_plan_only_resume.py" \
  "${temporary_directory}/wrong_endpoint.log" DESCEND FORWARD \
  "${temporary_directory}/checkpoint.json" \
  "${temporary_directory}/checkpoint.after.json"

sed 's/PLANNED_END_TCP_POSE state=DESCEND next_state=CLOSE_GRIPPER x=0.3 y=0 z=0.87 roll=3.141593/PLANNED_END_TCP_POSE state=DESCEND next_state=CLOSE_GRIPPER x=0.3 y=0 z=0.87 roll=1.0/' \
  "${temporary_directory}/plan.log" >"${temporary_directory}/wrong_orientation.log"
expect_failure python3 "${script_dir}/assert_plan_only_resume.py" \
  "${temporary_directory}/wrong_orientation.log" DESCEND FORWARD \
  "${temporary_directory}/checkpoint.json" \
  "${temporary_directory}/checkpoint.after.json"

sed 's/TARGET_TCP_POSE state=DESCEND/TARGET_TCP_POSE state=DESCEND x=nan/' \
  "${temporary_directory}/plan.log" >"${temporary_directory}/invalid_pose.log"
expect_failure python3 "${script_dir}/assert_plan_only_resume.py" \
  "${temporary_directory}/invalid_pose.log" DESCEND FORWARD \
  "${temporary_directory}/checkpoint.json" \
  "${temporary_directory}/checkpoint.after.json"

sed 's/START_TCP_POSE state=DESCEND next_state=CLOSE_GRIPPER x=0.3/START_TCP_POSE state=DESCEND next_state=CLOSE_GRIPPER x=0.32/' \
  "${temporary_directory}/plan_second.log" \
  >"${temporary_directory}/moved_tcp.log"
expect_failure python3 "${script_dir}/assert_plan_only_tcp_unchanged.py" \
  "${temporary_directory}/plan.log" \
  "${temporary_directory}/moved_tcp.log" DESCEND

cp "${temporary_directory}/plan.log" "${temporary_directory}/invalid.log"
printf '%s\n' 'EXECUTED_END_TCP_POSE state=DESCEND' >>"${temporary_directory}/invalid.log"
expect_failure python3 "${script_dir}/assert_plan_only_resume.py" \
  "${temporary_directory}/invalid.log" DESCEND FORWARD \
  "${temporary_directory}/checkpoint.json" \
  "${temporary_directory}/checkpoint.after.json"

python3 - "${temporary_directory}/checkpoint.after.json" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
checkpoint = json.loads(path.read_text(encoding='utf-8'))
checkpoint['sequence'] += 1
path.write_text(json.dumps(checkpoint), encoding='utf-8')
PY
expect_failure python3 "${script_dir}/assert_plan_only_resume.py" \
  "${temporary_directory}/plan.log" DESCEND FORWARD \
  "${temporary_directory}/checkpoint.json" \
  "${temporary_directory}/checkpoint.after.json"

cp "${temporary_directory}/checkpoint.json" \
  "${temporary_directory}/recovery_checkpoint.json"
python3 "${script_dir}/seed_recovery_checkpoint.py" \
  "${temporary_directory}/recovery_checkpoint.json" \
  "${temporary_directory}/attached.json" ATTACH_MOVEIT
python3 - "${temporary_directory}/recovery_checkpoint.json" <<'PY'
import json
import pathlib
import sys

checkpoint = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8'))
assert checkpoint['phase'] == 'RECOVERY'
assert checkpoint['failed_state'] == 'ATTACH_MOVEIT'
assert checkpoint['next_state'] == 'RECOVER_RETREAT'
assert checkpoint['original_failure']['code'] == 'HEADLESS_RECOVERY_TRIGGER'
assert checkpoint['expected']['tcp_pose_world']['z'] == 0.9
assert checkpoint['expected']['gazebo_coke_attached']
assert checkpoint['expected']['moveit_coke_attached']
assert 'coke' not in checkpoint['expected']['moveit_world_object_poses']
PY

printf 'PASS: plan-only resume helper assertions\n'
