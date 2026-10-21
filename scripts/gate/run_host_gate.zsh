#!/usr/bin/env zsh
# Host gate: build, so101_demo_py pytest and colcon test of the worktree this script lives in. Run it from the worktree under test.
# Split layout: build/install/log/test-run/demo-run trees in $BUILD_ROOT/gates/<id>, results in the evidence gate dir $EVIDENCE_R/gates/<id>
# with a build-root.txt pointer. Host values (paths, interpreters, workers, staged mode, memory scope) come from hosts/<host>.env. See README.md.
#   run_host_gate.zsh [--host H] [--gate-suffix S] [--demo-workers N] [--no-isolation] [--full] [--serial] [--teleop-jobs N] [--plan]
#                     [--no-rerun-known-flakes] [--upstream-parallel|--no-upstream-parallel] [--upstream-sets-reference FILE]
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
#     --upstream-parallel / --no-upstream-parallel
#                      run the upstream ros2_control / joint_trajectory_controller tests (when the decisions say run) in groups on their own CPUs
#                      beside the demo and the other colcon parts, instead of switching the whole gate to serial; default: GATE_UPSTREAM_PARALLEL of
#                      the host config (0). See README.md "Parallel upstream tests".
#     --upstream-sets-reference FILE
#                      compare the executed upstream test sets (upstream_groups.py sets) with those of a serial gate; a difference fails the gate
# One new gate directory per commit under gates/<commit12>; refuses if it exists. The worktree and scripts/gate must be clean.
set -o pipefail
zmodload zsh/datetime
FG=${0:A:h}
WT=${FG:h:h}
orig_args=("$@")
FULL=0; SERIAL=0; PLAN=0; TELEOP_JOBS=6; SUFFIX=; DEMO_WORKERS_ARG=; DEMO_WORKERS_SET=0; ISOLATE=1; HOST_ARG=; RERUN=1; UP_ARG=; SETS_REF=
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
    --upstream-parallel) UP_ARG=1 ;;
    --no-upstream-parallel) UP_ARG=0 ;;
    --upstream-sets-reference) shift; SETS_REF=${1:-} ;;
    -h|--help) sed -n '2,/^set -o/p' $0 | sed '$d'; exit 0 ;;
    *) print -u2 "unknown argument: $1"; exit 2 ;;
  esac
  shift
done
source $FG/load_host.zsh && so101_load_host $HOST_ARG || exit 2
ROOT=$EVIDENCE_ROOT
R=$EVIDENCE_R
(( DEMO_WORKERS_SET )) && DEMO_WORKERS=$DEMO_WORKERS_ARG
UPSTREAM_PARALLEL_REQUESTED=${UP_ARG:-${GATE_UPSTREAM_PARALLEL:-0}}
[[ $UPSTREAM_PARALLEL_REQUESTED == [01] ]] || { print -u2 "GATE_UPSTREAM_PARALLEL must be 0 or 1"; exit 2; }
[[ -z $SETS_REF || -r $SETS_REF ]] || { print -u2 "--upstream-sets-reference: cannot read $SETS_REF"; exit 2; }
STAGED=${GATE_STAGED:-0}
[[ $TELEOP_JOBS == <1-> ]] || { print -u2 "--teleop-jobs needs a positive integer"; exit 2; }
(( SERIAL )) && TELEOP_JOBS=1
[[ $DEMO_WORKERS == <1-> ]] || { print -u2 "--demo-workers needs a positive integer"; exit 2; }
[[ -z $SUFFIX || $SUFFIX =~ ^[A-Za-z0-9_-]+$ ]] || { print -u2 -- "--gate-suffix: [A-Za-z0-9_-] only"; exit 2; }

BUILD=$FG/gate_build.zsh; DEMO=$FG/gate_demo_py.zsh
for f in $BUILD $DEMO $FG/colcon_stage.zsh $FG/colcon_part.zsh $FG/ros2_control_decision.zsh $FG/jtc_decision.zsh $FG/rc_record.py $FG/rerun_known_flakes.zsh $FG/known_flakes.py; do test -r $f || exit 90; done
for f in $FG/upstream_groups.py $FG/upstream-groups.txt $FG/upstream_stage.zsh $FG/upstream_slot.zsh; do test -r $f || exit 90; done
test -r $FG/pytest-plugin/so101_pytest_worker_temp.py || exit 91
cd $WT || exit 92

if (( PLAN )); then
  print "host=$GATE_HOST build_script=$BUILD"
  print -r -- "--- ros2_control (controller_manager, hardware_interface_testing) ---"
  zsh $FG/ros2_control_decision.zsh /dev/stdout $FULL; plan_rc=$?
  print -r -- "--- joint_trajectory_controller upstream suite ---"
  zsh $FG/jtc_decision.zsh /dev/stdout $FULL || plan_rc=$?
  print -r -- "--- upstream groups (GATE_UPSTREAM_PARALLEL=$UPSTREAM_PARALLEL_REQUESTED, share ${GATE_UPSTREAM_CPU_SHARE:-unset}) ---"
  [[ -n ${GATE_UPSTREAM_CPU_SHARE:-} ]] && python3 -I $FG/upstream_groups.py cpus --groups $FG/upstream-groups.txt --share $GATE_UPSTREAM_CPU_SHARE
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
# With the upstream groups (GATE_UPSTREAM_PARALLEL=1) the upstream suites get CPUs of their own instead, and nothing else is switched to serial.
UPSTREAM_PARALLEL=0
if [[ $decision == run || $jtc_decision == run ]] && (( ! SERIAL )); then
  if [[ $UPSTREAM_PARALLEL_REQUESTED == 1 ]]; then
    UPSTREAM_PARALLEL=1
    print -r -- "upstream_parallel=1 (ros2_control=$decision jtc_upstream=$jtc_decision)"
  else
    SERIAL=1; TELEOP_JOBS=1
    print -r -- "auto_serial=1 (ros2_control=$decision jtc_upstream=$jtc_decision)"
  fi
fi
export UPSTREAM_PARALLEL
export TELEOP_JOBS
(( SERIAL )) && export PARTS_SEQUENTIAL=1 || export PARTS_SEQUENTIAL=0
# The settings of the stages, kept so that rerun_known_flakes.zsh can rerun a stage with the same environment.
for v in ISOLATE_ROS DEMO_WORKERS DEMO_ROS_DOMAIN_ID TELEOP_ROS_DOMAIN_ID JTC_ROS_DOMAIN_ID FAST_SKIP_ROS2_CONTROL FAST_SKIP_JTC_UPSTREAM NO_OVERLAY TELEOP_JOBS PARTS_SEQUENTIAL UPSTREAM_PARALLEL; do
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
pin=(); up_pkgs=()
[[ $FAST_SKIP_ROS2_CONTROL == 1 ]] || up_pkgs+=(controller_manager hardware_interface_testing)
[[ $FAST_SKIP_JTC_UPSTREAM == 1 ]] || up_pkgs+=(joint_trajectory_controller)
if (( UPSTREAM_PARALLEL )); then
  # The upstream groups get whole fastest cores each; every other stage is kept to the remaining CPUs so that nothing else runs on theirs.
  GATE_UPSTREAM_CPU_SHARE=${GATE_UPSTREAM_CPU_SHARE:?GATE_UPSTREAM_CPU_SHARE (host config) is needed for GATE_UPSTREAM_PARALLEL=1}
  python3 -I $FG/upstream_groups.py cpus --groups $FG/upstream-groups.txt --share $GATE_UPSTREAM_CPU_SHARE --packages ${(j:,:)up_pkgs} > $GATE/upstream-cpus.json || { print "upstream cpus failed"; exit 99; }
  rest_cpus=$(python3 -I -c 'import json,sys; print(json.load(open(sys.argv[1]))["rest"])' $GATE/upstream-cpus.json)
  pin=(/usr/bin/taskset -c $rest_cpus)
  export UPSTREAM_CPUS=$GATE/upstream-cpus.json GATE_TEST_RUN=$(mktemp -d $GATE_BUILD/test-run.XXXXXXXX)
  cat $GATE/upstream-cpus.json
  {
    run_stage upstream zsh $FG/upstream_stage.zsh $GATE_TEST_RUN
    # a crashed upstream stage must not leave colcon_stage waiting for upstream.done
    test -e $GATE_TEST_RUN/upstream.done || { print -r -- 99 > $GATE_TEST_RUN/upstream.rc; : > $GATE_TEST_RUN/upstream.done; }
  } &
  pid_up=$!
fi
# Sequential stages when --serial, or when the host config says GATE_STAGED=1 (demo first, then colcon with its parts concurrent); the upstream groups, if any, run beside both.
if (( SERIAL || STAGED )); then
  run_stage demo $pin zsh $DEMO; demo_rc=$?
  run_stage colcon $pin zsh $FG/colcon_stage.zsh; colcon_rc=$?
else
  run_stage demo $pin zsh $DEMO &
  pid_demo=$!
  run_stage colcon $pin zsh $FG/colcon_stage.zsh &
  pid_colcon=$!
  wait $pid_demo; demo_rc=$?
  wait $pid_colcon; colcon_rc=$?
fi
upstream_rc=-
if (( UPSTREAM_PARALLEL )); then
  wait $pid_up
  upstream_rc=$(cat $GATE_TEST_RUN/upstream.rc)
fi
tests_wall=$(( EPOCHSECONDS - t_tests ))
print -r -- "demo_rc=$demo_rc" | tee $GATE/stage-demo.txt
print -r -- "colcon_rc=$colcon_rc" | tee $GATE/stage-colcon.txt
cd $WT

# --- the executed upstream test sets, and their comparison with a serial gate's (the parallel mode must run exactly the same tests) ---
sets_rc=0
if (( ${#up_pkgs} )); then
  python3 -I $FG/upstream_groups.py sets --build-base $GATE_BUILD/build --packages ${(j:,:)up_pkgs} --out $GATE/upstream-sets.json || sets_rc=1
  if [[ -n $SETS_REF ]]; then
    python3 -I $FG/upstream_groups.py compare $SETS_REF $GATE/upstream-sets.json > $GATE/upstream-sets-compare.txt 2>&1 || sets_rc=1
    print -r -- "upstream_sets_vs_reference rc=$sets_rc ($SETS_REF)"; head -5 $GATE/upstream-sets-compare.txt
  fi
fi

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
print -r -- "fast_gate build_s=$build_wall demo_s=$demo_wall colcon_s=$colcon_wall tests_wall_s=$tests_wall total_s=$(( EPOCHSECONDS - t_all )) concurrent_stages=$(( 1 - SERIAL )) ros2_control_tests=$decision jtc_upstream_tests=$jtc_decision legacy_build=0 skipped_packages=${skipped:--} teleop_jobs=$TELEOP_JOBS full=$FULL serial=$SERIAL demo_workers=$DEMO_WORKERS concurrent=$(( 1 - SERIAL )) upstream_parallel=$UPSTREAM_PARALLEL upstream_rc=$upstream_rc upstream_sets_rc=$sets_rc ccache_hits=$cc_hits ccache_misses=$cc_miss build_ccache=$cc_state gate_suffix=${SUFFIX:--}" > $GATE/fast-gate-timing.txt
cat $GATE/gates-result.txt $GATE/fast-gate-timing.txt

# --- the one allowed rerun of failures that are listed in known-flakes.txt ---
first_rc=$(( demo_rc || colcon_rc || sets_rc ))
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
