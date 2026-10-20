#!/usr/bin/env zsh
# Re-run a subset of the so101_demo_py ordinary gate against the INSTALLED package of an existing gate build root (same env as gate_demo_py.zsh).
#   rerun_subset.zsh <gate-id> <workers> <pytest paths...>
set -o pipefail
FG=${0:A:h}
source $FG/load_host.zsh && so101_load_host || exit 2
ID=${1:?gate id}; WORKERS=${2:?workers}; shift 2
R=$EVIDENCE_R
GB=$(cat $R/gates/$ID/build-root.txt) || exit 90
FZ=$DEPS_FREEZE
WT=${FG:h:h}
TEST_PYTHON=$DEMO_PYTHON
test -x $TEST_PYTHON && test -r $GB/install/setup.zsh || exit 90
for f in /opt/ros/jazzy/setup.zsh $GB/install/setup.zsh; do source $f 2>/dev/null || exit 91; done
S=$SCRATCH_ROOT/subset-$ID-$(date -u +%H%M%S)
mkdir -p $S/tmp || exit 92
export TMPDIR=$S/tmp TMP=$S/tmp TEMP=$S/tmp PYTHONNOUSERSITE=1
ipc=$(mktemp -d /tmp/so101-ipc.XXXXXXXX) || exit 94
chmod 0700 $ipc
export SO101_IPC_SOCKET_BASE=$ipc
export ROS_DOMAIN_ID=${DEMO_ROS_DOMAIN_ID:-203} ROS_LOCALHOST_ONLY=1 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
export PYTHONPATH=$FG/pytest-plugin:$FZ/python-deps:$PYTHONPATH:/usr/lib/python3/dist-packages
$TEST_PYTHON -c 'import os,pathlib,tempfile,so101_demo; assert pathlib.Path(tempfile.gettempdir()).resolve()==pathlib.Path(os.environ["TMPDIR"]).resolve(); print(so101_demo.__file__)' || exit 93
cd $WT/src/so101_demo_py || exit 94
$TEST_PYTHON -m pytest "$@" -n $WORKERS -q -p no:cacheprovider -p so101_pytest_worker_temp --junitxml=$S/junit.xml > $S/pytest.log 2>&1
rc=$?
print -r -- $rc > $S/rc
tail -5 $S/pytest.log | cut -c1-220
print "rc=$rc scratch=$S"
exit $rc
