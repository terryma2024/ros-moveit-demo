#!/usr/bin/env zsh
# Upstream ros2_control / joint_trajectory_controller tests of the parallel gate (GATE_UPSTREAM_PARALLEL=1). usage: upstream_stage.zsh <run-dir>
# Every group of upstream-groups.txt runs on its own CPUs (taskset -c, the fastest whole cores first) with its own ROS domain, concurrently with the
# demo stage and the other colcon parts, which are kept to the remaining CPUs. Before anything runs, the groups are checked against `ctest -N` of each
# package: every test belongs to exactly one group. Results are the same ctest/gtest files as in the serial gate, in <run-dir>/up-<group>/.
# env: GATE, GATE_BUILD, GATE_SCRATCH (as colcon_part.zsh); FAST_SKIP_ROS2_CONTROL, FAST_SKIP_JTC_UPSTREAM (which packages take part);
#      UPSTREAM_CPUS (file written by `upstream_groups.py cpus`); UPSTREAM_DOMAIN_BASE (first ROS domain of the groups, default 223);
#      GATE_PART_SCRIPT (the part script, default colcon_part.zsh) and GATE_TASKSET (default /usr/bin/taskset): seams for the fixture test.
# Writes <run-dir>/upstream.rc and upstream.elapsed, and upstream.done last (colcon_stage.zsh waits for it).
set -o pipefail
FG=${0:A:h}
source $FG/load_host.zsh && so101_load_host || exit 2
zmodload zsh/datetime
run=${1:?run dir}
GB=${GATE_BUILD:?set GATE_BUILD}
cpus=${UPSTREAM_CPUS:?set UPSTREAM_CPUS}
part_script=${GATE_PART_SCRIPT:-$FG/colcon_part.zsh}
base=${UPSTREAM_DOMAIN_BASE:-223}
start=$EPOCHSECONDS
finish() { print -r -- $1 > $run/upstream.rc; print -r -- $(( EPOCHSECONDS - start )) > $run/upstream.elapsed; : > $run/upstream.done; exit $1; }
packages=()
[[ ${FAST_SKIP_ROS2_CONTROL:-0} == 1 ]] || packages+=(controller_manager hardware_interface_testing)
[[ ${FAST_SKIP_JTC_UPSTREAM:-0} == 1 ]] || packages+=(joint_trajectory_controller)
(( ${#packages} )) || finish 0
mkdir -p $run/upstream-lists $run/upstream-spec || finish 92
for p in $packages; do
  (cd $GB/build/$p && ctest -N) > $run/upstream-lists/$p.txt 2>&1 || { print "ctest -N failed for $p"; finish 90; }
done
python3 -I $FG/upstream_groups.py spec --groups $FG/upstream-groups.txt --package-lists $run/upstream-lists --packages ${(j:,:)packages} > $run/upstream-spec/all.tsv || finish 91
groups=($(python3 -I -c 'import json,sys; print(*json.load(open(sys.argv[1]))["groups"])' $cpus)) || finish 91
i=0; pids=(); names=()
for g in $groups; do
  grep "^$g"$'\t' $run/upstream-spec/all.tsv > $run/upstream-spec/$g.tsv
  [[ -s $run/upstream-spec/$g.tsv ]] || continue
  c=$(python3 -I -c 'import json,sys; print(json.load(open(sys.argv[1]))["groups"][sys.argv[2]])' $cpus $g)
  print -r -- "group=$g cpus=$c domain=$(( base + i ))" >> $run/upstream-groups.txt
  UPSTREAM_GROUP_DOMAIN=$(( base + i )) UPSTREAM_SPEC=$run/upstream-spec/$g.tsv \
    ${GATE_TASKSET:-/usr/bin/taskset} -c $c zsh $part_script $run up-$g > $run/part-up-$g.console 2>&1 &
  pids+=($!); names+=($g); (( i++ ))
done
rc=0
for n in {1..${#pids}}; do
  wait $pids[$n]; r=$?
  print -r -- "$names[$n] rc=$r" >> $run/upstream-parts.rc.txt
  (( r != 0 )) && rc=1
done
finish $rc
