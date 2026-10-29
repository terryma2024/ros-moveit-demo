#!/usr/bin/zsh
# One task_reachability CLI call (native IK) inside a running light stack container (light_stacks.zsh).
# usage: reach_call.zsh <work dir of the stack> <container name> <ros domain> <install dir> <points json> <evidence json> <session id>
# The points file is copied into <work>/calls (the only writable place the container has); evidence, stdout, stderr and rc are copied back
# next to the requested evidence file (EVIDENCE, EVIDENCE.stdout, EVIDENCE.stderr, EVIDENCE.rc).
set -o pipefail
OUT=$1; NAME=$2; DOMAIN=$3; INSTALL=$4; POINTS=$5; EVIDENCE=$6; SESSION=$7
LOCAL=$OUT/calls; mkdir -p $LOCAL
base=${EVIDENCE:t}
cp $POINTS $LOCAL/$base.points.json || exit 2
# R3-a: REACH_TEACHER_POLICY names a schema 6 Teacher execution policy (a path the container sees, e.g. under the installed config/act);
# each point is then checked against its per-episode targets. Unset: the call is what it always was.
TEACHER=(); [[ -n ${REACH_TEACHER_POLICY:-} ]] && TEACHER=(--teacher-execution-policy $REACH_TEACHER_POLICY)
docker exec --user 1000:1000 -e ROS_DOMAIN_ID=$DOMAIN -e ROS_LOCALHOST_ONLY=1 -e ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST \
  -e TMPDIR=$OUT/container-root/tmp -e ROS_LOG_DIR=$OUT/container-root/ros-logs -e ROS_HOME=$OUT/container-root/tmp/ros-home \
  -e PYTHONNOUSERSITE=1 -e PYTHONDONTWRITEBYTECODE=1 $NAME /act/bootstrap.bash $INSTALL/so101_demo_py/lib/so101_demo_py/task_reachability \
  --points $LOCAL/$base.points.json --policy $INSTALL/so101_demo_py/share/so101_demo_py/config/policies/dynamic_cup_pick/mujoco.yaml --session-id $SESSION \
  --evidence-file $LOCAL/$base --ik-backend native $TEACHER > $LOCAL/$base.stdout 2> $LOCAL/$base.stderr
rc=$?
for ext in "" .stdout .stderr; do [[ -e $LOCAL/$base$ext ]] && cp $LOCAL/$base$ext $EVIDENCE$ext; done
echo $rc > $EVIDENCE.rc
exit $rc
