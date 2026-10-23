#!/usr/bin/zsh
# Start a headless execution stack in the mount-base image with the host-built install tree (and the source snapshot) bind-mounted
# read-only at the path they were built at. Container restrictions are the ones of the image-based start: --read-only, --cap-drop ALL,
# no-new-privileges, --network none, --ipc private, a non-root user.
#
# usage: start_mounted.zsh --image ID --install DIR --source DIR --out-dir DIR --gpu UUID --name NAME --domain-id N --commit HEX40 [--session-id S] [-- COMMAND...]
#   Without a COMMAND the act execution stack is launched headless. Writes under OUT/container-root (tmp, ros-logs, stack, launch.log).
# The entry script of the image refuses to start unless both trees carry a BUILD-COMMIT record equal to --commit.
# Design: docs/superpowers/specs/2026-10-21-so101-mount-build-images-design.md
set -o pipefail
IMAGE= INSTALL= SOURCE= OUT= GPU= NAME= DOMAIN= COMMIT= SESSION=mountedstack
while (( $# )); do
  case $1 in
    --image) IMAGE=$2; shift 2;;
    --install) INSTALL=$2; shift 2;;
    --source) SOURCE=$2; shift 2;;
    --out-dir) OUT=$2; shift 2;;
    --gpu) GPU=$2; shift 2;;
    --name) NAME=$2; shift 2;;
    --domain-id) DOMAIN=$2; shift 2;;
    --commit) COMMIT=$2; shift 2;;
    --session-id) SESSION=$2; shift 2;;
    --) shift; break;;
    *) print -u2 "unknown argument $1"; exit 2;;
  esac
done
for v in IMAGE INSTALL SOURCE OUT GPU NAME DOMAIN COMMIT; do [[ -n ${(P)v} ]] || { print -u2 "MOUNT_ARGUMENT_MISSING: $v"; exit 2; }; done
for tree in $INSTALL $SOURCE $OUT; do
  [[ $tree == /* ]] || { print -u2 "MOUNT_PATH_NOT_ABSOLUTE: $tree"; exit 2; }
  [[ -d $tree ]] || { print -u2 "MOUNT_TREE_MISSING: $tree"; exit 2; }
done
CR=$OUT/container-root
mkdir -p $CR/tmp $CR/ros-logs $CR/stack || exit 2
if (( $# )); then
  CMD=("$@")
else
  CMD=(bash -c "ros2 launch so101_demo_py so101_mujoco_act_execution_stack.launch.py headless:=true sensor_rendering:=true act_profile:=true session_id:=$SESSION task_evidence_root:=$CR/stack > $CR/launch.log 2>&1 & sleep infinity")
fi
exec docker run --detach --name $NAME --user 1000:1000 --read-only --cap-drop ALL --security-opt no-new-privileges \
  --network none --ipc private --restart no --gpus device=$GPU \
  --env NVIDIA_DRIVER_CAPABILITIES=compute,utility,graphics --env TMPDIR=$CR/tmp --env TMP=$CR/tmp --env TEMP=$CR/tmp \
  --env PYTHONNOUSERSITE=1 --env PYTHONDONTWRITEBYTECODE=1 --env XDG_CACHE_HOME=$CR/tmp/cache --env XDG_CONFIG_HOME=$CR/tmp/config \
  --env MPLCONFIGDIR=$CR/tmp/matplotlib --env ROS_HOME=$CR/tmp/ros-home --env ROS_LOG_DIR=$CR/ros-logs \
  --env ROS_DOMAIN_ID=$DOMAIN --env MUJOCO_GL=egl --env ROS_LOCALHOST_ONLY=1 --env ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST \
  --env SO101_MUJOCO_SESSION_ID=$SESSION --env SO101_SIMULATION_SESSION_ID=$SESSION --env SO101_TASK_EVIDENCE_ROOT=$CR/stack \
  --env GZ_PARTITION=$SESSION --env SO101_MOUNT_INSTALL=$INSTALL --env SO101_MOUNT_SOURCE=$SOURCE --env SO101_EXPECTED_COMMIT=$COMMIT \
  --mount type=bind,src=$OUT,dst=$OUT \
  --mount type=bind,src=$INSTALL,dst=$INSTALL,readonly \
  --mount type=bind,src=$SOURCE,dst=$SOURCE,readonly \
  --oom-score-adj 900 --entrypoint /act/bootstrap.bash $IMAGE $CMD
