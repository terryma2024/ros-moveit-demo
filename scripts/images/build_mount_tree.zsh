#!/usr/bin/zsh
# Build the install tree and the source snapshot that a container mounts read-only (docs/superpowers/specs/2026-10-21-so101-mount-build-images-design.md).
#
# usage: build_mount_tree.zsh --commit HEX [--host H | --build-root DIR]   (run from the worktree to build)
#   Writes $BUILD_ROOT/mount/<commit12>/{install,source,build,log}. The worktree must be clean and its HEAD must be the commit, checked at the start
#   and again after the build. Only when both checks and the build pass is BUILD-COMMIT written, last, into install/ and source/; both trees are
#   then made read-only (0555 directories). A failed run leaves no BUILD-COMMIT, so the container entry refuses the tree.
#   MOUNT_BUILD_COMMAND replaces the colcon build (tests); it runs in the worktree with MOUNT_ROOT, MOUNT_INSTALL, MOUNT_BUILD and MOUNT_LOG set.
set -o pipefail
FG=${0:A:h}
COMMIT= HOST_ARG= BUILD_ROOT_ARG=
while (( $# )); do
  case $1 in
    --commit) COMMIT=$2; shift 2;;
    --host) HOST_ARG=$2; shift 2;;
    --build-root) BUILD_ROOT_ARG=$2; shift 2;;
    *) print -u2 "unknown argument $1"; exit 2;;
  esac
done
[[ $COMMIT =~ ^[0-9a-f]{40}$ ]] || { print -u2 "MOUNT_BUILD_COMMIT_INVALID: need the 40-hex commit"; exit 2; }
if [[ -n $BUILD_ROOT_ARG ]]; then BUILD_ROOT=$BUILD_ROOT_ARG; else source ${FG:h}/gate/load_host.zsh && so101_load_host $HOST_ARG || exit 2; fi
WT=$PWD
check_worktree() {
  [[ -z $(git -C $WT status --porcelain) ]] || { print -u2 "MOUNT_BUILD_WORKTREE_DIRTY ($1)"; return 3; }
  [[ $(git -C $WT rev-parse HEAD) == $COMMIT ]] || { print -u2 "MOUNT_BUILD_HEAD_MISMATCH ($1)"; return 3; }
}
check_worktree start || exit 3
ROOT=$BUILD_ROOT/mount/${COMMIT[1,12]}
[[ ! -e $ROOT ]] || { print -u2 "MOUNT_BUILD_ROOT_EXISTS: $ROOT"; exit 2; }
mkdir -p $ROOT/install $ROOT/source $ROOT/build $ROOT/log || exit 2
export MOUNT_ROOT=$ROOT MOUNT_INSTALL=$ROOT/install MOUNT_BUILD=$ROOT/build MOUNT_LOG=$ROOT/log
export PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 MUJOCO_GL=egl
if [[ -n ${MOUNT_BUILD_COMMAND:-} ]]; then
  (cd $WT && eval $MOUNT_BUILD_COMMAND) || { print -u2 "MOUNT_BUILD_FAILED"; exit 4; }
else
  source /opt/ros/jazzy/setup.zsh 2>/dev/null || { print -u2 "MOUNT_BUILD_FAILED: ROS is not installed"; exit 4; }
  LODE=${DEPS_FREEZE:?DEPS_FREEZE not set}/build-deps/lodepng
  CC_ARGS=()   # ccache is allowed (when the two hosts differ, compare ccache and compiler versions first)
  if command -v ccache >/dev/null 2>&1 && [[ -n ${GATE_CCACHE_DIR:-} ]]; then
    export CCACHE_DIR=$GATE_CCACHE_DIR CCACHE_BASEDIR=$ROOT CCACHE_NOHASHDIR=1
    CC_ARGS=(-DCMAKE_C_COMPILER_LAUNCHER=ccache -DCMAKE_CXX_COMPILER_LAUNCHER=ccache)
  fi
  /usr/bin/colcon --log-base $MOUNT_LOG build --base-paths src third_party --build-base $MOUNT_BUILD --install-base $MOUNT_INSTALL \
    --allow-overriding joint_trajectory_controller joint_state_broadcaster controller_manager hardware_interface_testing mujoco_ros2_control mujoco_ros2_control_plugins mujoco_ros2_control_msgs mujoco_3d_lidar mujoco_ros2_control_demos mujoco_ros2_control_tests so101_mujoco_support so101_demo_py so101_teleop \
    --packages-select joint_trajectory_controller joint_state_broadcaster so101_queued_state_publisher controller_manager hardware_interface_testing so101_clock_test_hardware so101_clock_regression mujoco_3d_lidar mujoco_ros2_control mujoco_ros2_control_demos mujoco_ros2_control_msgs mujoco_ros2_control_plugins mujoco_ros2_control_tests so101_mujoco_support so101_quik so101_teleop so101_demo_py \
    --parallel-workers 4 --cmake-args -DCMAKE_BUILD_TYPE=RelWithDebInfo -DBUILD_TESTING=ON -DFETCHCONTENT_SOURCE_DIR_LODEPNG=$LODE -DFETCHCONTENT_FULLY_DISCONNECTED=ON $CC_ARGS \
    > $MOUNT_LOG/colcon.log 2>&1 || { print -u2 "MOUNT_BUILD_FAILED: see $MOUNT_LOG/colcon.log"; exit 4; }
fi
git -C $WT archive --format=tar $COMMIT | tar -x -C $ROOT/source || { print -u2 "MOUNT_BUILD_FAILED: source snapshot"; exit 4; }
check_worktree end || exit 3
# The commit records come last, and only now.
for tree in $ROOT/install $ROOT/source; do print -r -- $COMMIT > $tree/BUILD-COMMIT; done
chmod -R a-w,a+rX $ROOT/install $ROOT/source
print "mount tree ready: $ROOT ($COMMIT)"
