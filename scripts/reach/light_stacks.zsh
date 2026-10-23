#!/usr/bin/zsh
# N light reachability stacks (reach_light_stack: robot_state_publisher, move_group, scene_setup, fake simulator; no GPU) in the mount-base
# image with the host-built install and source trees bind-mounted read-only. Container restrictions are those of scripts/images/start_mounted.zsh:
# --read-only, --cap-drop ALL, no-new-privileges, --network none, --ipc private, non-root user; a stack's only writable place is its work dir.
#
# usage: light_stacks.zsh start N --image ID --install DIR --source DIR --work-dir DIR --commit HEX40 [--first-domain 181] [--prefix reachlight] [--no-wait]
#        light_stacks.zsh stop N [--prefix reachlight]
# Stack i: container PREFIX<i>, ROS domain FIRST+i, work dir WORK/s<i>. Equivalence with the full stack: scripts/reach/compare_verdicts.py.
set -o pipefail
MODE=$1; COUNT=$2; shift 2 2>/dev/null
IMAGE= INSTALL= SOURCE= WORK= COMMIT= FIRST=181 PREFIX=reachlight WAIT=1
while (( $# )); do
  case $1 in
    --image) IMAGE=$2; shift 2;;
    --install) INSTALL=$2; shift 2;;
    --source) SOURCE=$2; shift 2;;
    --work-dir) WORK=$2; shift 2;;
    --commit) COMMIT=$2; shift 2;;
    --first-domain) FIRST=$2; shift 2;;
    --prefix) PREFIX=$2; shift 2;;
    --no-wait) WAIT=0; shift;;
    *) print -u2 "unknown argument $1"; exit 2;;
  esac
done
[[ $COUNT == <-> ]] && (( COUNT >= 1 && COUNT <= 32 )) || { print -u2 "LIGHT_STACKS_COUNT_INVALID: $COUNT (1..32)"; exit 2; }
case $MODE in
stop)
  for ((i=0;i<COUNT;i++)); do docker rm -f $PREFIX$i >/dev/null 2>&1; done
  exit 0;;
start) ;;
*) print -u2 "usage: light_stacks.zsh start|stop N ..."; exit 2;;
esac
for v in IMAGE INSTALL SOURCE WORK COMMIT; do [[ -n ${(P)v} ]] || { print -u2 "LIGHT_STACKS_ARGUMENT_MISSING: $v"; exit 2; }; done
for tree in $INSTALL $SOURCE; do
  [[ $tree == /* && -d $tree ]] || { print -u2 "MOUNT_TREE_MISSING: $tree"; exit 2; }
done
[[ $WORK == /* ]] || { print -u2 "MOUNT_PATH_NOT_ABSOLUTE: $WORK"; exit 2; }
[[ $FIRST == <-> ]] && (( FIRST >= 0 && FIRST + COUNT - 1 <= 232 )) || { print -u2 "LIGHT_STACKS_DOMAIN_RANGE: $FIRST+$COUNT (ROS domains 0..232)"; exit 2; }
REACHDIR=$SOURCE/scripts/reach
start_one() {
  local i=$1 out=$WORK/s$1 session=lightreach$1
  local cr=$out/container-root
  mkdir -p $cr/tmp $cr/ros-logs $cr/stack || return 2
  docker run --detach --name $PREFIX$i --user 1000:1000 --read-only --cap-drop ALL --security-opt no-new-privileges \
    --network none --ipc private --restart no \
    --env TMPDIR=$cr/tmp --env TMP=$cr/tmp --env TEMP=$cr/tmp \
    --env PYTHONNOUSERSITE=1 --env PYTHONDONTWRITEBYTECODE=1 --env XDG_CACHE_HOME=$cr/tmp/cache --env XDG_CONFIG_HOME=$cr/tmp/config \
    --env MPLCONFIGDIR=$cr/tmp/matplotlib --env ROS_HOME=$cr/tmp/ros-home --env ROS_LOG_DIR=$cr/ros-logs \
    --env ROS_DOMAIN_ID=$((FIRST+i)) --env ROS_LOCALHOST_ONLY=1 --env ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST \
    --env SO101_MUJOCO_SESSION_ID=$session --env SO101_SIMULATION_SESSION_ID=$session --env SO101_TASK_EVIDENCE_ROOT=$cr/stack \
    --env GZ_PARTITION=$session --env SO101_MOUNT_INSTALL=$INSTALL --env SO101_MOUNT_SOURCE=$SOURCE --env SO101_EXPECTED_COMMIT=$COMMIT \
    --env LIGHT_FAKE_SIM=$REACHDIR/fake_sim.py \
    --mount type=bind,src=$out,dst=$out \
    --mount type=bind,src=$INSTALL,dst=$INSTALL,readonly \
    --mount type=bind,src=$SOURCE,dst=$SOURCE,readonly \
    --oom-score-adj 900 --entrypoint /act/bootstrap.bash $IMAGE \
    bash -c "ros2 launch $REACHDIR/light_stack.launch.py > $cr/launch.log 2>&1 & sleep infinity" >/dev/null
}
pids=()
for ((i=0;i<COUNT;i++)); do start_one $i & pids+=($!); done
rc=0; for p in $pids; do wait $p || rc=1; done
(( rc == 0 )) || { print -u2 "LIGHT_STACKS_START_FAILED"; exit 1; }
(( WAIT )) || exit 0
# ready when every stack's scene_setup has finished
deadline=$((SECONDS+240))
for ((i=0;i<COUNT;i++)); do
  until grep -q "scene_setup.*finished cleanly" $WORK/s$i/container-root/launch.log 2>/dev/null; do
    (( SECONDS < deadline )) || { print -u2 "LIGHT_STACK_NOT_READY: $PREFIX$i"; exit 1; }
    sleep 2
  done
done
