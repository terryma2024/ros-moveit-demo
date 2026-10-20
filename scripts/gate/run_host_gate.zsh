#!/usr/bin/env zsh
# Host gate: build, so101_demo_py pytest and colcon test of the worktree this script lives in. Run it from the worktree under test.
# Split layout: build/install/log/test-run/demo-run trees in $BUILD_ROOT/gates/<id>, results in the evidence gate dir $EVIDENCE_R/gates/<id>
# with a build-root.txt pointer. Host values (paths, interpreters, workers, staged mode, memory scope) come from hosts/<host>.env. See README.md.
#   run_host_gate.zsh [--host H] [--gate-suffix S] [--demo-workers N] [--no-isolation] [--full] [--serial] [--teleop-jobs N] [--plan]
#                     [--no-rerun-known-flakes]
#     --host H         host config hosts/H.env; default: the host whose HOST_NAMES contains `hostname`; an unknown host is refused
#     --full           run controller_manager / hardware_interface_testing tests even if the skip rule allows skipping
#     --serial         demo pytest and colcon test one after the other, colcon parts one after the other, so101_teleop with ctest -j1
#                      (the ros2_control skip rule still applies; add --full)
#     --teleop-jobs N  ctest -j for the parallel part of so101_teleop (default 6)
#     --gate-suffix S  gate dir gates/<commit12>.S instead of gates/<commit12>
#     --demo-workers N demo pytest xdist workers (default: DEMO_WORKERS of the host config)
#     --no-isolation   do not set per-stage ROS domains / loopback-only
#     --plan           print the skip decisions (ros2_control and joint_trajectory_controller) and exit; creates nothing
#     --no-rerun-known-flakes
#                      after a failed gate, do not do the one allowed rerun of failures listed in known-flakes.txt (default: rerun)
# One new gate directory per commit under gates/<commit12>; refuses if it exists. The worktree and scripts/gate must be clean.
set -o pipefail
zmodload zsh/datetime
FG=${0:A:h}
WT=${FG:h:h}
orig_args=("$@")
FULL=0; SERIAL=0; PLAN=0; TELEOP_JOBS=6; SUFFIX=; DEMO_WORKERS_ARG=; DEMO_WORKERS_SET=0; ISOLATE=1; HOST_ARG=; RERUN=1
while (( $# )); do
  case $1 in
    --host) shift; HOST_ARG=${1:-} ;;
    --full) FULL=1 ;;
    --serial) SERIAL=1 ;;
    --plan) PLAN=1 ;;
    --gate-suffix) shift; SUFFIX=${1:-} ;;
    --demo-workers) shift; DEMO_WORKERS_ARG=${1:-}; DEMO_WORKERS_SET=1 ;;
    --no-isolation) ISOLATE=0 ;;
    --teleop-jobs) shift; TELEOP_JOBS=${1:-} ;;
    --rerun-known-flakes) RERUN=1 ;;
    --no-rerun-known-flakes) RERUN=0 ;;
    -h|--help) sed -n '2,/^set -o/p' $0 | sed '$d'; exit 0 ;;
    *) print -u2 "unknown argument: $1"; exit 2 ;;
  esac
  shift
done
source $FG/load_host.zsh && so101_load_host $HOST_ARG || exit 2
ROOT=$EVIDENCE_ROOT
R=$EVIDENCE_R
(( DEMO_WORKERS_SET )) && DEMO_WORKERS=$DEMO_WORKERS_ARG
STAGED=${GATE_STAGED:-0}
[[ $TELEOP_JOBS == <1-> ]] || { print -u2 "--teleop-jobs needs a positive integer"; exit 2; }
(( SERIAL )) && TELEOP_JOBS=1
[[ $DEMO_WORKERS == <1-> ]] || { print -u2 "--demo-workers needs a positive integer"; exit 2; }
[[ -z $SUFFIX || $SUFFIX =~ ^[A-Za-z0-9_-]+$ ]] || { print -u2 -- "--gate-suffix: [A-Za-z0-9_-] only"; exit 2; }

BUILD=$FG/gate_build.zsh; DEMO=$FG/gate_demo_py.zsh
for f in $BUILD $DEMO $FG/colcon_stage.zsh $FG/colcon_part.zsh $FG/ros2_control_decision.zsh $FG/jtc_decision.zsh $FG/rc_record.py $FG/rerun_known_flakes.zsh $FG/known_flakes.py; do test -r $f || exit 90; done
test -r $FG/pytest-plugin/so101_pytest_worker_temp.py || exit 91
cd $WT || exit 92

if (( PLAN )); then
  print "host=$GATE_HOST build_script=$BUILD"
  print -r -- "--- ros2_control (controller_manager, hardware_interface_testing) ---"
  zsh $FG/ros2_control_decision.zsh /dev/stdout $FULL; plan_rc=$?
  print -r -- "--- joint_trajectory_controller upstream suite ---"
  zsh $FG/jtc_decision.zsh /dev/stdout $FULL || plan_rc=$?
  exit $plan_rc
fi

# Host switches that wrap the gate: reset SIGINT (a gate started with & inherits SIGINT=ignored, which makes every launch-supervisor
# test wait out its 20 s SIGINT timeout) and run inside a memory-limited systemd scope. Each re-exec happens once.
pre=()
if [[ ${GATE_RESET_SIGINT:-0} == 1 && -z ${GATE_SIGINT_RESET_DONE:-} ]]; then
  export GATE_SIGINT_RESET_DONE=1
  pre+=(/usr/bin/python3 -I $FG/sigdfl.py)
fi
if [[ ${GATE_SCOPE:-0} == 1 && -z ${GATE_IN_SCOPE:-} ]]; then
  export GATE_IN_SCOPE=1
  pre+=(systemd-run --user --scope -p MemoryHigh=${GATE_SCOPE_MEMORY_HIGH:?GATE_SCOPE_MEMORY_HIGH} -p MemoryMax=${GATE_SCOPE_MEMORY_MAX:?GATE_SCOPE_MEMORY_MAX})
fi
(( ${#pre} )) && exec $pre zsh ${0:A} --host $GATE_HOST "${orig_args[@]}"

# Clean worktree is required; no particular HEAD is (ledger-only commits on top are normal).
test -z "$(git status --short)" || { print "worktree dirty"; exit 93; }
head=$(git rev-parse HEAD) || exit 94
export GATE=$R/gates/${head[1,12]}${SUFFIX:+.$SUFFIX}
test ! -e $GATE || { print "gate directory exists: $GATE"; exit 95; }
# Results in $GATE (evidence); build/install/log/test-run/demo-run trees in $GATE_BUILD; per-run TMPDIR scratch in $GATE_SCRATCH
# (AGENTS.md: pytest/colcon-test scratch stays under the durable evidence root). $GATE/build-root.txt is the pointer templates read.
export GATE_BUILD=$BUILD_ROOT/gates/${GATE:t}
export GATE_SCRATCH=$SCRATCH_ROOT/gate-${GATE:t}
test ! -e $GATE_BUILD || { print "build root exists: $GATE_BUILD"; exit 95; }
test ! -e $GATE_SCRATCH || { print "gate scratch exists: $GATE_SCRATCH"; exit 95; }
mkdir -p $GATE $GATE_BUILD $GATE_SCRATCH || exit 96
print -r -- $GATE_BUILD > $GATE/build-root.txt
print -r -- $head > $GATE/head.txt
git submodule status > $GATE/submodule.txt
# The gate tools are part of the code under test: record their commit and diff stat; scripts/gate must be clean.
tools_commit=$(python3 -I $FG/rc_record.py tools --repo $WT --out $GATE/gate-tools.txt) || { print "scripts/gate is not clean (see $GATE/gate-tools.txt)"; exit 98; }
print -r -- "gate_tools_commit=$tools_commit"
print -r -- "logical_cpus=$(nproc) demo_pytest_workers=$DEMO_WORKERS teleop_jobs=$TELEOP_JOBS full=$FULL serial=$SERIAL fast_gate=4 isolate_ros=$ISOLATE gate_suffix=${SUFFIX:--}" > $GATE/cpu.txt
print -r -- "host=$GATE_HOST staged=$STAGED scope=${GATE_SCOPE:-0} in_scope=${GATE_IN_SCOPE:-0} memory_high=${GATE_SCOPE_MEMORY_HIGH:--} memory_max=${GATE_SCOPE_MEMORY_MAX:--} mem_sampler=${GATE_MEM_SAMPLER:-0} reset_sigint=${GATE_RESET_SIGINT:-0} demo_dist=${DEMO_DIST:--} rerun_known_flakes=$RERUN worktree=$WT evidence_r=$R build_root=$BUILD_ROOT" > $GATE/gate-host.txt
free -g > $GATE/memory.txt; uptime > $GATE/load.txt; df -h $DISK_PATH > $GATE/df.txt
if [[ ${GATE_MEM_SAMPLER:-0} == 1 ]]; then
  /usr/bin/python3 -I ${FG:h}/run_tools/memory_sampler.py $GATE/memory-sampler.log &
  mem_sampler_pid=$!
  trap 'kill $mem_sampler_pid 2>/dev/null' EXIT
fi
print -r -- "ROS_DOMAIN_ID=${ROS_DOMAIN_ID-<unset>} DISABLE_ROS_ISOLATION=${DISABLE_ROS_ISOLATION-<unset>}" > $GATE/ros-env-before.txt
# The domain isolation of the colcon launch tests is only active with these unset (checked in run_test_isolated.py).
unset ROS_DOMAIN_ID DISABLE_ROS_ISOLATION ROS_LOCALHOST_ONLY ROS_AUTOMATIC_DISCOVERY_RANGE
export ISOLATE_ROS=$ISOLATE DEMO_WORKERS
export DEMO_ROS_DOMAIN_ID=${DEMO_ROS_DOMAIN_ID:-203} TELEOP_ROS_DOMAIN_ID=${TELEOP_ROS_DOMAIN_ID:-204} JTC_ROS_DOMAIN_ID=${JTC_ROS_DOMAIN_ID:-229}
print -r -- "isolate_ros=$ISOLATE demo_domain=$DEMO_ROS_DOMAIN_ID teleop_domain=$TELEOP_ROS_DOMAIN_ID jtc_domain=$JTC_ROS_DOMAIN_ID main_domain=unset(launch-test coordinator)" > $GATE/ros-domains.txt
print "GATE=$GATE host=$GATE_HOST"

# --- skip decision (read only) ---
decision=$(zsh $FG/ros2_control_decision.zsh $GATE/ros2-control-decision.json $FULL) || { print "ros2_control decision failed"; exit 97; }
print -r -- "ros2_control_tests=$decision"
if [[ $decision == skip ]]; then export FAST_SKIP_ROS2_CONTROL=1; else export FAST_SKIP_ROS2_CONTROL=0; fi
export NO_OVERLAY=0
jtc_decision=$(zsh $FG/jtc_decision.zsh $GATE/jtc-decision.json $FULL) || { print "jtc decision failed"; exit 97; }
if [[ $jtc_decision == skip ]]; then export FAST_SKIP_JTC_UPSTREAM=1; else export FAST_SKIP_JTC_UPSTREAM=0; fi
print -r -- "jtc_upstream_tests=$jtc_decision build_script=$BUILD"
# The upstream ros2_control / joint_trajectory_controller suites are timing sensitive and flake under the concurrent mode (gate b13874eaabd5: 11 and 22
# failures that pass serially). When either decision is "run", the gate switches to serial automatically (stages one after the other, teleop ctest -j1).
if [[ $decision == run || $jtc_decision == run ]] && (( ! SERIAL )); then
  SERIAL=1; TELEOP_JOBS=1
  print -r -- "auto_serial=1 (ros2_control=$decision jtc_upstream=$jtc_decision)"
fi
export TELEOP_JOBS
(( SERIAL )) && export PARTS_SEQUENTIAL=1 || export PARTS_SEQUENTIAL=0
# The settings of the stages, kept so that rerun_known_flakes.zsh can rerun a stage with the same environment.
for v in ISOLATE_ROS DEMO_WORKERS DEMO_ROS_DOMAIN_ID TELEOP_ROS_DOMAIN_ID JTC_ROS_DOMAIN_ID FAST_SKIP_ROS2_CONTROL FAST_SKIP_JTC_UPSTREAM NO_OVERLAY TELEOP_JOBS PARTS_SEQUENTIAL; do
  print -r -- "$v=${(P)v}"
done > $GATE/stage-env.txt

t_all=$EPOCHSECONDS
# --- build ---
t0=$EPOCHSECONDS
zsh $BUILD; build_rc=$?
build_wall=$(( EPOCHSECONDS - t0 ))
print -r -- "build_rc=$build_rc elapsed=$(cat $GATE/build.elapsed 2>/dev/null)" | tee $GATE/stage-build.txt
if (( build_rc != 0 )); then print -r -- "build_rc=$build_rc" > $GATE/gates-result.txt; exit 1; fi

# --- test stages ---
run_stage() {  # run_stage <name> <command...>
  local name=$1; shift
  local s0=$EPOCHSECONDS
  print -r -- $s0 > $GATE/stage-$name.start
  "$@" > $GATE/stage-$name.console 2>&1
  local src=$?
  print -r -- $src > $GATE/stage-$name.rc
  print -r -- $(( EPOCHSECONDS - s0 )) > $GATE/stage-$name.wall
  return $src
}
t_tests=$EPOCHSECONDS
# Sequential stages when --serial, or when the host config says GATE_STAGED=1 (demo first, then colcon with its parts concurrent).
if (( SERIAL || STAGED )); then
  run_stage demo zsh $DEMO; demo_rc=$?
  run_stage colcon zsh $FG/colcon_stage.zsh; colcon_rc=$?
else
  run_stage demo zsh $DEMO &
  pid_demo=$!
  run_stage colcon zsh $FG/colcon_stage.zsh &
  pid_colcon=$!
  wait $pid_demo; demo_rc=$?
  wait $pid_colcon; colcon_rc=$?
fi
tests_wall=$(( EPOCHSECONDS - t_tests ))
print -r -- "demo_rc=$demo_rc" | tee $GATE/stage-demo.txt
print -r -- "colcon_rc=$colcon_rc" | tee $GATE/stage-colcon.txt
cd $WT

# --- record for the skip rule of later gates ---
python3 -I $FG/rc_record.py finish --decision $GATE/ros2-control-decision.json --gate $GATE --build-base $GATE_BUILD/build --colcon-rc $colcon_rc --tools-commit $tools_commit --out $GATE/ros2-control-tests.json
if [[ -r $GATE/jtc-decision.json ]]; then
  python3 -I $FG/rc_record.py finish --decision $GATE/jtc-decision.json --gate $GATE --build-base $GATE_BUILD/build --colcon-rc $colcon_rc --packages joint_trajectory_controller --tools-commit $tools_commit --out $GATE/jtc-tests.json
fi

zsh $FG/collect_results.zsh $GATE $GATE_BUILD > $GATE/collect-results.txt 2>&1; print -r -- "collect_results_rc=$?" >> $GATE/collect-results.txt
cc_hits=-; cc_miss=-; cc_state=absent; grep -q '^ccache=/' $GATE/ccache-config.txt 2>/dev/null && cc_state=on
[[ -r $GATE/ccache-delta.txt ]] && { cc_hits=${$(grep -o 'ccache_hits=[0-9]*' $GATE/ccache-delta.txt)#*=}; cc_miss=${$(grep -o 'ccache_misses=[0-9]*' $GATE/ccache-delta.txt)#*=}; }
demo_wall=$(cat $GATE/stage-demo.wall 2>/dev/null)
colcon_wall=$(cat $GATE/stage-colcon.wall 2>/dev/null)
skipped=""; [[ $decision == skip ]] && skipped="controller_manager,hardware_interface_testing"
[[ $jtc_decision == skip ]] && skipped="${skipped:+$skipped,}joint_trajectory_controller(upstream)"
print -r -- "build_rc=$build_rc demo_rc=$demo_rc colcon_rc=$colcon_rc head_after=$(git rev-parse HEAD) dirty_after=$(git status --short | wc -l)" > $GATE/gates-result.txt
print -r -- "fast_gate build_s=$build_wall demo_s=$demo_wall colcon_s=$colcon_wall tests_wall_s=$tests_wall total_s=$(( EPOCHSECONDS - t_all )) concurrent_stages=$(( 1 - SERIAL )) ros2_control_tests=$decision jtc_upstream_tests=$jtc_decision legacy_build=0 skipped_packages=${skipped:--} teleop_jobs=$TELEOP_JOBS full=$FULL serial=$SERIAL demo_workers=$DEMO_WORKERS concurrent=$(( 1 - SERIAL )) ccache_hits=$cc_hits ccache_misses=$cc_miss build_ccache=$cc_state gate_suffix=${SUFFIX:--}" > $GATE/fast-gate-timing.txt
cat $GATE/gates-result.txt $GATE/fast-gate-timing.txt

# --- the one allowed rerun of failures that are listed in known-flakes.txt ---
first_rc=$(( demo_rc || colcon_rc ))
final_rc=$first_rc
rerun_state=not_needed; rerun_rc=-
if (( first_rc != 0 )); then
  if (( RERUN )); then
    zsh $FG/rerun_known_flakes.zsh ${GATE:t} --host $GATE_HOST > $GATE/rerun-known-flakes.console 2>&1; rerun_rc=$?
    tail -3 $GATE/rerun-known-flakes.console
    case $rerun_rc in
      0) rerun_state=passed; final_rc=0 ;;
      3) rerun_state=refused ;;
      *) rerun_state=failed_again ;;
    esac
  else
    rerun_state=off
  fi
fi
print -r -- "first_run_rc=$first_rc known_flake_rerun=$rerun_state rerun_rc=$rerun_rc final_rc=$final_rc" > $GATE/gate-verdict.txt
cat $GATE/gate-verdict.txt
exit $final_rc
