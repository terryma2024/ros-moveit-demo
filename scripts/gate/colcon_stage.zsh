#!/usr/bin/env zsh
# Colcon test stage of the Host gate: the "main", "teleop" and "jtc" (joint_trajectory_controller, -j1, own ROS domain) parts run concurrently (each with its own
# TMPDIR, IPC base and colcon log base), then one `colcon test-result` over the whole build base.
# Run dir and build/install base under GATE_BUILD (build root), TMPDIR scratch under GATE_SCRATCH.
# env: GATE (evidence dir, required), GATE_BUILD (required), GATE_SCRATCH (required), FAST_SKIP_ROS2_CONTROL=0|1, FAST_SKIP_JTC_UPSTREAM=0|1, TELEOP_JOBS=<n>, PARTS_SEQUENTIAL=0|1,
#      UPSTREAM_PARALLEL=0|1 with GATE_TEST_RUN (see upstream_stage.zsh)
set -o pipefail
FG=${0:A:h}
source $FG/load_host.zsh && so101_load_host || exit 2
G=${GATE:?set GATE}
GB=${GATE_BUILD:?set GATE_BUILD}
: ${GATE_SCRATCH:?set GATE_SCRATCH}
test -x /usr/bin/colcon && test -r $GB/install/setup.zsh && test "$(cat $G/build-root.txt)" = "$GB" || exit 90
zmodload zsh/zselect
# GATE_TEST_RUN: the run dir made by run_host_gate.zsh when the upstream groups write into it too (UPSTREAM_PARALLEL=1).
if [[ -n ${GATE_TEST_RUN:-} ]]; then run=$GATE_TEST_RUN; test -d $run || exit 93; else run=$(mktemp -d $GB/test-run.XXXXXXXX) || exit 93; fi
print -r -- "UPSTREAM_PARALLEL=${UPSTREAM_PARALLEL:-0} FAST_SKIP_ROS2_CONTROL=${FAST_SKIP_ROS2_CONTROL:-0} FAST_SKIP_JTC_UPSTREAM=${FAST_SKIP_JTC_UPSTREAM:-0} TELEOP_JOBS=${TELEOP_JOBS:-6} TELEOP_XDIST=${TELEOP_XDIST:-0} PARTS_SEQUENTIAL=${PARTS_SEQUENTIAL:-0}" > $run/stage-config.txt
start=$SECONDS
if [[ ${PARTS_SEQUENTIAL:-0} == 1 ]]; then
  zsh $FG/colcon_part.zsh $run main > $run/part-main.console 2>&1; rc_main=$?
  zsh $FG/colcon_part.zsh $run teleop > $run/part-teleop.console 2>&1; rc_teleop=$?
  zsh $FG/colcon_part.zsh $run jtc > $run/part-jtc.console 2>&1; rc_jtc=$?
else
  zsh $FG/colcon_part.zsh $run main > $run/part-main.console 2>&1 &
  pid_main=$!
  zsh $FG/colcon_part.zsh $run teleop > $run/part-teleop.console 2>&1 &
  pid_teleop=$!
  zsh $FG/colcon_part.zsh $run jtc > $run/part-jtc.console 2>&1 &
  pid_jtc=$!
  wait $pid_main; rc_main=$?
  wait $pid_teleop; rc_teleop=$?
  wait $pid_jtc; rc_jtc=$?
fi
rc_up=0
if [[ ${UPSTREAM_PARALLEL:-0} == 1 ]]; then   # upstream_stage.zsh runs beside this stage; its results are part of this one
  until test -e $run/upstream.done; do zselect -t 100; done
  rc_up=$(cat $run/upstream.rc)
fi
rc=$(( rc_main || rc_teleop || rc_jtc || rc_up ))
print -r -- $rc > $run/colcon-test.rc; print -r -- $(( SECONDS - start )) > $run/colcon-test.elapsed
print -r -- "main_rc=$rc_main teleop_rc=$rc_teleop jtc_rc=$rc_jtc upstream_rc=$rc_up" > $run/parts.rc.txt
# Combined log for tooling that greps test-run.*/colcon-test.log (the parts keep their own logs).
: > $run/colcon-test.log
for f in $run/main/colcon-test.log $run/teleop/colcon-test.log $run/jtc/colcon-test.log $run/up-*/colcon-test.log(N); do
  test -f $f && cat -- $f >> $run/colcon-test.log
done
source /opt/ros/jazzy/setup.zsh 2>/dev/null
/usr/bin/colcon test-result --test-result-base $GB/build --all --verbose > $run/test-result.log 2>&1
rr=$?
print -r -- $rr > $run/test-result.rc
# colcon reads only the newest Test.xml per package; add the older ctest phases (so101_teleop serial + parallel). Reporting only:
# the exit status below is unchanged.
/usr/bin/python3 -I $FG/ctest_extra_phases.py $GB/build $run/test-result.log > $run/test-result-extra-phases.log 2>&1
print -r -- "extra_phases_rc=$?" >> $run/test-result-extra-phases.log
cat $run/test-result-extra-phases.log >> $run/test-result.log
tail -5 $run/test-result.log
print "RUN=$run main_rc=$rc_main teleop_rc=$rc_teleop jtc_rc=$rc_jtc upstream_rc=$rc_up test_result_rc=$rr elapsed=$(( SECONDS - start ))s"
exit $(( rc || rr ))
