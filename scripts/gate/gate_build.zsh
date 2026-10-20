#!/usr/bin/env zsh
# Build stage of the Host gate: fresh base, full closure, all colcon packages of the worktree + third_party, tests ON.
# Lossless queued-state overlay third_party/ros2_controllers, ccache, and the split layout of AGENTS.md:
#   build/install/log trees go to the BUILD ROOT $GATE_BUILD = $BUILD_ROOT/gates/<id>;
#   result files (build.log, build.rc, build.elapsed, ccache statistics) and the build TMPDIR stay in the EVIDENCE gate dir $GATE.
# env: GATE (evidence gate dir, required), GATE_BUILD (build root, required), host values from hosts/<host>.env
set -o pipefail
FG=${0:A:h}
source $FG/load_host.zsh && so101_load_host || exit 2
G=${GATE:?set GATE}
GB=${GATE_BUILD:?set GATE_BUILD}
WT=${FG:h:h}
LODE=$DEPS_FREEZE/build-deps/lodepng
test -r /opt/ros/jazzy/setup.zsh && test -x /usr/bin/colcon && test -r $LODE/lodepng.h || exit 90
test ! -e $GB/build && test ! -e $GB/install || exit 89
source /opt/ros/jazzy/setup.zsh 2>/dev/null || exit 91
cd $WT || exit 92
git status --short > $G/build-git-status.txt; git rev-parse HEAD > $G/build-git-head.txt
mkdir -p $G/tmp $GB; export TMPDIR=$G/tmp TMP=$G/tmp TEMP=$G/tmp PYTHONNOUSERSITE=1 MUJOCO_GL=egl
CC_ARGS=()
if command -v ccache >/dev/null 2>&1; then
  export CCACHE_DIR=$GATE_CCACHE_DIR CCACHE_MAXSIZE=${CCACHE_MAXSIZE:-20G} CCACHE_BASEDIR=$GB CCACHE_NOHASHDIR=1
  mkdir -p $CCACHE_DIR
  ccache -s > $G/ccache-stats-before.txt 2>&1; ccache --print-stats > $G/ccache-raw-before.txt 2>&1
  CC_ARGS=(-DCMAKE_C_COMPILER_LAUNCHER=ccache -DCMAKE_CXX_COMPILER_LAUNCHER=ccache)
  print -r -- "ccache=$(command -v ccache) CCACHE_DIR=$CCACHE_DIR CCACHE_MAXSIZE=$CCACHE_MAXSIZE CCACHE_BASEDIR=$CCACHE_BASEDIR" > $G/ccache-config.txt
else
  print "NOTE: ccache not found on PATH - building without it"; print -r -- "ccache=absent" > $G/ccache-config.txt
fi
start=$SECONDS
/usr/bin/colcon --log-base $GB/log build --base-paths src third_party --build-base $GB/build --install-base $GB/install \
  --allow-overriding joint_trajectory_controller joint_state_broadcaster controller_manager hardware_interface_testing mujoco_ros2_control mujoco_ros2_control_plugins mujoco_ros2_control_msgs mujoco_3d_lidar mujoco_ros2_control_demos mujoco_ros2_control_tests so101_mujoco_support so101_demo_py so101_teleop \
  --packages-select joint_trajectory_controller joint_state_broadcaster so101_queued_state_publisher controller_manager hardware_interface_testing so101_clock_test_hardware so101_clock_regression mujoco_3d_lidar mujoco_ros2_control mujoco_ros2_control_demos mujoco_ros2_control_msgs mujoco_ros2_control_plugins mujoco_ros2_control_tests so101_mujoco_support so101_quik so101_teleop so101_demo_py --parallel-workers 4 --cmake-args -DCMAKE_BUILD_TYPE=RelWithDebInfo -DBUILD_TESTING=ON -DFETCHCONTENT_SOURCE_DIR_LODEPNG=$LODE -DFETCHCONTENT_FULLY_DISCONNECTED=ON $CC_ARGS \
  --event-handlers console_direct+ > $G/build.log 2>&1
rc=$?
print -r -- $rc > $G/build.rc; print -r -- $(( SECONDS - start )) > $G/build.elapsed
if (( ${#CC_ARGS} )); then
  ccache -s > $G/ccache-stats-after.txt 2>&1; ccache --print-stats > $G/ccache-raw-after.txt 2>&1
  python3 -I - $G <<'PY' > $G/ccache-delta.txt
import sys
def rd(p):
    d = {}
    for l in open(p):
        k, _, v = l.partition('\t')
        try: d[k] = int(v)
        except ValueError: pass
    return d
a = rd(sys.argv[1] + '/ccache-raw-before.txt'); b = rd(sys.argv[1] + '/ccache-raw-after.txt')
dl = lambda k: b.get(k, 0) - a.get(k, 0)
h = dl('direct_cache_hit') + dl('preprocessed_cache_hit'); m = dl('cache_miss')
print(f"ccache_hits={h} ccache_misses={m} ccache_hit_rate={h / (h + m) if h + m else 0:.3f}")
PY
fi
exit $rc
