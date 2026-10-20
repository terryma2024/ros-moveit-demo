#!/usr/bin/env zsh
# The ONE allowed rerun after a failed gate. Refuses (exit 3) when any failure is not listed in known-flakes.txt.
# usage: rerun_known_flakes.zsh <gate dir name, e.g. 895da5a66c75.f2> [--host <name>]
# Reruns only the failed stage against the existing build root: the demo stage with just the failed test ids (one worker),
# the colcon stage in full. Results go to <gate>/rerun/. Exit 0 when every rerun passed, 1 when one failed again, 3 when
# a failure is not a known flake or known-flakes.txt is malformed.
set -o pipefail
FG=${0:A:h}
ID=${1:?gate dir name}; shift
HOST_ARG=
while (( $# )); do
  case $1 in
    --host) shift; HOST_ARG=${1:-} ;;
    *) print -u2 "unknown argument: $1"; exit 2 ;;
  esac
  shift
done
source $FG/load_host.zsh && so101_load_host $HOST_ARG || exit 2
G=$EVIDENCE_R/gates/$ID
test -d $G && test -r $G/build-root.txt || { print -u2 "no gate directory $G"; exit 2; }
GB=$(cat $G/build-root.txt)
# The stage settings of the gate run (written by run_host_gate.zsh); a variable already in the environment wins.
if [[ -r $G/stage-env.txt ]]; then
  while IFS= read -r line; do
    [[ -z $line ]] && continue
    [[ -v ${line%%=*} ]] || export "$line"
  done < $G/stage-env.txt
fi
export GATE=$G GATE_BUILD=$GB GATE_SCRATCH=$SCRATCH_ROOT/rerun-$ID
mkdir -p $GATE_SCRATCH $G/rerun
known=(${(f)"$(python3 -I $FG/known_flakes.py $FG/known-flakes.txt)"}) || { print -u2 "known-flakes.txt is malformed"; exit 3; }
ok() { local f; for f in "$@"; do local hit=0 k; for k in $known; do [[ $f == *$k* ]] && hit=1; done; (( hit )) || { print "NOT a known flake: $f"; return 1 }; done }
rc=0
if [[ $(cat $G/stage-demo.rc) != 0 ]]; then
  J=$(ls -dt $GB/demo-run.* | head -1)/junit.xml
  ids=(${(f)"$(python3 -I - $J <<'PY'
import sys,xml.etree.ElementTree as ET
for c in ET.parse(sys.argv[1]).getroot().iter('testcase'):
    if any(f.tag in('failure','error') for f in c):
        print(c.get('classname').replace('.','/')+'.py::'+c.get('name'))
PY
)"})
  print -r -- $ids > $G/rerun/demo-failed.txt
  (( $#ids )) || { print "demo stage failed without a failed test case in junit.xml"; exit 3; }
  ok $ids || exit 3
  print "rerun demo: $#ids tests"
  # test ids carry module paths as classnames (test.act.x -> test/act/x.py); keep only the part pytest can take
  GATE_DEMO_TARGETS="${(j: :)${(q)ids}}" DEMO_WORKERS=1 zsh $FG/gate_demo_py.zsh > $G/rerun/demo.console 2>&1; r=$?
  print $r > $G/rerun/demo.rc; tail -2 $G/rerun/demo.console | cut -c1-200; (( r )) && rc=1
fi
if [[ $(cat $G/stage-colcon.rc) != 0 ]]; then
  failed=(${(f)"$(grep -l '<failure\|<error' $(find $GB/build -name '*.xml' -path '*test_results*') 2>/dev/null)"})
  (( $#failed )) || { print "colcon stage failed without a failed result file"; exit 3; }
  ok ${failed:t} || exit 3
  print "rerun colcon (failed: ${failed:t})"
  zsh $FG/colcon_stage.zsh > $G/rerun/colcon.console 2>&1; r=$?
  print $r > $G/rerun/colcon.rc; tail -2 $G/rerun/colcon.console | cut -c1-200; (( r )) && rc=1
fi
zsh $FG/collect_results.zsh $G $GB > $G/rerun/collect-results.txt 2>&1
print "rerun_rc=$rc" | tee $G/rerun/result.txt
exit $rc
