#!/usr/bin/env zsh
# One colcon test invocation group of the fast gate. usage: colcon_part.zsh <run-dir> <main|teleop|jtc>
#   main   : the non-teleop packages, ctest -j1 (controller_manager + hardware_interface_testing left out when
#            FAST_SKIP_ROS2_CONTROL=1), colcon's default package parallelism as in the old gate.
#            joint_state_broadcaster and so101_queued_state_publisher (local queue tests included) always run here.
#   jtc    : joint_trajectory_controller only, ctest -j1 (its gmock suites share a ROS domain and cross-talk when run in
#            parallel), in its own ROS domain ($JTC_ROS_DOMAIN_ID, loopback only). With FAST_SKIP_JTC_UPSTREAM=1 only the
#            local SO-101 test test_state_queue_publication runs; the upstream suites (test_trajectory_controller, ~690
#            tests, test_trajectory, test_tolerances, test_trajectory_actions, test_load_joint_trajectory_controller) are
#            skipped. Otherwise the whole package runs.
#   teleop : so101_teleop only. SERIAL_TELEOP_TESTS first with -j1, then everything else with -j $TELEOP_JOBS.
#   up-<group> : (UPSTREAM_PARALLEL=1, started by upstream_stage.zsh on its own CPUs) the entries of one group of upstream-groups.txt, one after the
#            other, each a ctest -j1 of one package with -R/-E from $UPSTREAM_SPEC, in the ROS domain $UPSTREAM_GROUP_DOMAIN. With UPSTREAM_PARALLEL=1 the
#            main part leaves out controller_manager and hardware_interface_testing, and the jtc part its upstream suites: the groups run them.
# Own TMPDIR, own IPC socket base, own colcon log base. Interpreters and PYTHONPATH come from the host values (hosts/<host>.env).
set -o pipefail
FG=${0:A:h}
source $FG/load_host.zsh && so101_load_host || exit 2
G=${GATE:?set GATE}
GB=${GATE_BUILD:?set GATE_BUILD}
SCR=${GATE_SCRATCH:?set GATE_SCRATCH}
WT=${FG:h:h}
FZ=$DEPS_FREEZE
TESTVENV=$TEST_VENV
run=${1:?run dir}; part=${2:?part}
TELEOP_JOBS=${TELEOP_JOBS:-6}
# Tests that spawn and scan real process groups, or that proved timing-sensitive; they run alone (-j1) before the parallel rest.
# Names are ctest names (first argument of so101_add_pytest_test). Empty the list to run everything in parallel.
# test_expert_validation_e2e_installed_port: its test_fixed_helper_full_protocol runs fixed_helper.py with plain
# subprocess.run (no start_new_session) so the helper sits in the shared ctest process group, and the autouse fixture in
# test/conftest.py of a SIBLING pytest (marker = the shared SO101_IPC_SOCKET_BASE) then killpg()s that group, i.e. the gate.
# Proven with strace + a killpg trap (see README.md "teleop parallel self-kill").
SERIAL_TELEOP_TESTS=(
  test_process_owner_group_cleanup
  test_unified_bridge_cleanup
  test_expert_validation_process_owner
  test_expert_validation_process_owner_integration
  test_expert_validation_retry_owner_reconcile
  test_expert_validation_owner_tree
  test_expert_validation_supervisor
  test_unified_bridge
  test_native_bridge
  test_act_stack_owner
  test_container_child_ownership
  test_expert_validation_e2e_installed_port
)
source $FG/upstream_slot.zsh
test -x /usr/bin/colcon && test -x /usr/bin/python3 && test -x $TESTVENV/bin/python && test -r $GB/install/setup.zsh && test -d $FZ/python-deps && test "$(cat $G/build-root.txt)" = "$GB" || exit 90
test -d $run || exit 91
d=$run/$part
mkdir $d || exit 92
scratch=$(mktemp -d $SCR/${run:t}-$part.XXXXXXXX) || exit 92
mkdir $scratch/tmp || exit 92
print -r -- $scratch > $d/scratch-path.txt
source /opt/ros/jazzy/setup.zsh 2>/dev/null || exit 93
source $GB/install/setup.zsh 2>/dev/null || exit 94
# Domain isolation of the launch tests (run_test_isolated.py) is only active when these are unset.
print -r -- "ROS_DOMAIN_ID_before=${ROS_DOMAIN_ID-<unset>} DISABLE_ROS_ISOLATION_before=${DISABLE_ROS_ISOLATION-<unset>}" > $d/ros-env.txt
unset ROS_DOMAIN_ID DISABLE_ROS_ISOLATION
# ROS isolation of this part (see README.md). ISOLATE_ROS=1 (default): loopback-only discovery for every part;
# teleop gets its own domain; jtc keeps its own (below); main stays UNSET on purpose: mujoco_ros2_control_tests uses
# run_test_isolated.py, which only picks a private domain per launch test while ROS_DOMAIN_ID is unset.
if [[ ${ISOLATE_ROS:-1} == 1 ]]; then
  # The main part (controller_manager, hardware_interface_testing) is NOT restricted to loopback. With
  # ROS_LOCALHOST_ONLY=1 and/or ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST the controller_manager spawner tests that pass
  # --controller-manager-timeout 1.0 (test_spawner_unspawner, test_advanced_spawner: wildcard_entries_*, global_wildcard_*,
  # failed_activation_*) cannot discover /test_controller_manager/list_controllers within 1 s (call_spawner returns 256).
  # Proven with the test binary alone: loopback variants fail 3 tests (~175 s), no restriction passes all (~94 s).
  if [[ $part != main ]]; then
    export ROS_LOCALHOST_ONLY=1 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
  fi
  [[ $part == teleop ]] && export ROS_DOMAIN_ID=${TELEOP_ROS_DOMAIN_ID:-204}
fi
# An upstream group has its own domain (not loopback-only for controller_manager, whose spawner tests need it; see above), set in its branch below.
print -r -- "ROS_DOMAIN_ID_effective=${ROS_DOMAIN_ID-<unset>} ROS_LOCALHOST_ONLY=${ROS_LOCALHOST_ONLY-<unset>} ROS_AUTOMATIC_DISCOVERY_RANGE=${ROS_AUTOMATIC_DISCOVERY_RANGE-<unset>}" >> $d/ros-env.txt
export TMPDIR=$scratch/tmp TMP=$scratch/tmp TEMP=$scratch/tmp PYTHONNOUSERSITE=1 MUJOCO_GL=egl
ipc=$(mktemp -d /tmp/so101-ipc.XXXXXXXX) || exit 95
chmod 0700 $ipc; export SO101_IPC_SOCKET_BASE=$ipc
print -r -- $ipc > $d/ipc-base.txt
export PYTHONPATH=$FG/pytest-plugin:$FZ/python-deps:$TESTVENV/lib/python3.12/site-packages:$PYTHONPATH
export PATH=$TESTVENV/bin:$PATH
for py in /usr/bin/python3 $TESTVENV/bin/python; do
  $py -c 'import os,pathlib,sys,tempfile; a=pathlib.Path(tempfile.gettempdir()).resolve(); e=pathlib.Path(os.environ["TMPDIR"]).resolve(); print(sys.executable,a); assert a==e' >> $d/tempfile-proof.log 2>&1 || { cat $d/tempfile-proof.log; exit 96; }
done
cat $d/tempfile-proof.log
cd $WT || exit 97

# colcon strips leading blanks from --ctest-args values (type=str.lstrip), so a leading blank keeps ctest options
# from being read as colcon options.
# colcon_test <tag> <package> -- <ctest args...>
colcon_test() {
  local tag=$1 pkg=$2; shift 3
  local ca=() a
  for a in "$@"; do ca+=(" $a"); done
  local t0=$SECONDS
  # setsid -w: own session/process group, so a stray group signal from a test cannot reach the gate (it fails tests instead).
  /usr/bin/setsid -w /usr/bin/colcon --log-base $d/colcon-log-$tag test --base-paths src third_party --packages-select $pkg \
    --build-base $GB/build --install-base $GB/install --event-handlers console_direct+ \
    --ctest-args $ca > $d/colcon-test-$tag.log 2>&1
  local crc=$?
  print -r -- $crc > $d/colcon-test-$tag.rc; print -r -- $(( SECONDS - t0 )) > $d/colcon-test-$tag.elapsed
  return $crc
}

start=$SECONDS
rc=0
if [[ $part == main ]]; then
  PKGS=(joint_state_broadcaster so101_queued_state_publisher hardware_interface_testing controller_manager so101_clock_test_hardware so101_clock_regression mujoco_3d_lidar mujoco_ros2_control mujoco_ros2_control_demos mujoco_ros2_control_msgs mujoco_ros2_control_plugins mujoco_ros2_control_tests so101_mujoco_support so101_quik)
  if [[ ${NO_OVERLAY:-0} == 1 ]]; then   # --legacy-build: the overlay packages were not built
    PKGS=(${PKGS:#(joint_state_broadcaster|so101_queued_state_publisher)})
  fi
  if [[ ${FAST_SKIP_ROS2_CONTROL:-0} == 1 ]]; then
    PKGS=(${PKGS:#(controller_manager|hardware_interface_testing)})
    print -r -- "skipped_packages=controller_manager hardware_interface_testing" > $d/skipped.txt
  fi
  if [[ ${UPSTREAM_PARALLEL:-0} == 1 ]]; then   # the upstream groups run these two (when they run at all)
    PKGS=(${PKGS:#(controller_manager|hardware_interface_testing)})
    print -r -- "upstream_parallel: controller_manager hardware_interface_testing run in the upstream groups" >> $d/skipped.txt
  fi
  print -r -- "${(j: :)PKGS}" > $d/packages.txt
  # --pytest-args as in the old gate: they reach colcon's own pytest verb only; ctest-registered tests ignore them.
  /usr/bin/colcon --log-base $d/colcon-log-main test --base-paths src third_party --packages-select $PKGS \
    --build-base $GB/build --install-base $GB/install --event-handlers console_direct+ \
    --ctest-args " -j1" --pytest-args -n 8 -p so101_pytest_worker_temp > $d/colcon-test-main.log 2>&1
  rc=$?
  print -r -- $rc > $d/colcon-test-main.rc; print -r -- $(( SECONDS - start )) > $d/colcon-test-main.elapsed
  cp -- $d/colcon-test-main.log $d/colcon-test.log
elif [[ $part == jtc && ${NO_OVERLAY:-0} == 1 ]]; then
  print -r -- "NO_OVERLAY=1 (--legacy-build): joint_trajectory_controller was not built, nothing to test" > $d/skipped.txt
  : > $d/colcon-test.log
elif [[ $part == jtc && ${UPSTREAM_PARALLEL:-0} == 1 && ${FAST_SKIP_JTC_UPSTREAM:-0} == 0 ]]; then
  print -r -- "UPSTREAM_PARALLEL=1: joint_trajectory_controller runs in the upstream groups" > $d/skipped.txt
  : > $d/colcon-test.log
elif [[ $part == jtc ]]; then
  # Unique domain outside the live (181, 216-222), demo (100-163) and launch-test (1-100) ranges, loopback only.
  export ROS_DOMAIN_ID=${JTC_ROS_DOMAIN_ID:-229} ROS_LOCALHOST_ONLY=1 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
  print -r -- "ROS_DOMAIN_ID=$ROS_DOMAIN_ID ROS_LOCALHOST_ONLY=$ROS_LOCALHOST_ONLY FAST_SKIP_JTC_UPSTREAM=${FAST_SKIP_JTC_UPSTREAM:-0}" > $d/packages.txt
  if [[ ${FAST_SKIP_JTC_UPSTREAM:-0} == 1 ]]; then
    print -r -- "skipped=upstream joint_trajectory_controller suites; ran=test_state_queue_publication (local)" > $d/skipped.txt
    colcon_test local joint_trajectory_controller -- -j1 -R '^test_state_queue_publication$' --no-tests=error; rc=$?; jtc_tag=local
  else
    colcon_test all joint_trajectory_controller -- -j1 --no-tests=error; rc=$?; jtc_tag=all
  fi
  cp -- $d/colcon-test-$jtc_tag.log $d/colcon-test.log
  print -r -- $rc > $d/colcon-test-jtc.rc; print -r -- $(( SECONDS - start )) > $d/colcon-test-jtc.elapsed
elif [[ $part == teleop ]]; then
  print -r -- "so101_teleop jobs=$TELEOP_JOBS serial_first=${(j:,:)SERIAL_TELEOP_TESTS}" > $d/packages.txt
  serial_rx="^(${(j:|:)SERIAL_TELEOP_TESTS})\$"
  for n in $SERIAL_TELEOP_TESTS; do
    grep -q -- "so101_add_pytest_test($n " $WT/src/so101_teleop/CMakeLists.txt || { print "SERIAL_TELEOP_TESTS names an unregistered test: $n"; exit 98; }
  done
  if (( TELEOP_JOBS <= 1 )); then
    colcon_test all so101_teleop -- -j1; rc=$?
  elif (( ${#SERIAL_TELEOP_TESTS} == 0 )); then
    colcon_test parallel so101_teleop -- -j$TELEOP_JOBS; rc=$?
  else
    colcon_test serial so101_teleop -- -j1 -R $serial_rx --no-tests=error; rc_a=$?
    colcon_test parallel so101_teleop -- -j$TELEOP_JOBS -E $serial_rx; rc_b=$?
    rc=$(( rc_a || rc_b ))
  fi
  # one combined log, phases in order
  : > $d/colcon-test.log
  for f in $d/colcon-test-serial.log $d/colcon-test-parallel.log $d/colcon-test-all.log; do
    test -f $f && cat -- $f >> $d/colcon-test.log
  done
  print -r -- $rc > $d/colcon-test-teleop.rc; print -r -- $(( SECONDS - start )) > $d/colcon-test-teleop.elapsed
elif [[ $part == up-* ]]; then
  spec=${UPSTREAM_SPEC:?set UPSTREAM_SPEC}
  export ROS_DOMAIN_ID=${UPSTREAM_GROUP_DOMAIN:?set UPSTREAM_GROUP_DOMAIN}
  : > $d/colcon-test.log
  entry=0
  while IFS=$'\t' read -r group pkg mode regex; do
    ca=(-j1 --no-tests=error)
    [[ $mode == R ]] && ca+=(-R $regex)
    [[ $mode == E ]] && ca+=(-E $regex)
    # joint_trajectory_controller was loopback-only in its own part; controller_manager must not be (see above).
    if [[ $pkg == joint_trajectory_controller ]]; then export ROS_LOCALHOST_ONLY=1 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST; else unset ROS_LOCALHOST_ONLY ROS_AUTOMATIC_DISCOVERY_RANGE; fi
    upstream_slot $run $pkg
    print -r -- "$group $pkg ctest ${ca[*]} ROS_DOMAIN_ID=$ROS_DOMAIN_ID start=$EPOCHSECONDS" >> $d/packages.txt
    (( entry++ )); tag=$pkg-$entry
    colcon_test $tag $pkg -- $ca; r=$?
    cat -- $d/colcon-test-$tag.log >> $d/colcon-test.log
    (( r != 0 )) && rc=1
  done < $spec
  print -r -- $rc > $d/colcon-test-upstream.rc; print -r -- $(( SECONDS - start )) > $d/colcon-test-upstream.elapsed
else
  exit 99
fi
print "PART=$part rc=$rc elapsed=$(( SECONDS - start ))s dir=$d"
exit $rc
