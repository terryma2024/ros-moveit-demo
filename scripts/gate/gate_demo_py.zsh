#!/usr/bin/env zsh
# so101_demo_py ordinary gate: grounded-sam interpreter ($DEMO_PYTHON), xdist $DEMO_WORKERS, the INSTALLED package of the build root (no shim),
# TMPDIR proven inside the registered evidence root (GATE_SCRATCH). env: GATE (evidence dir, holds build-root.txt), GATE_BUILD, GATE_SCRATCH,
# host values from hosts/<host>.env. Optional GATE_DEMO_TARGETS (pytest paths, default "test"; used by rerun_known_flakes.zsh).
set -o pipefail
FG=${0:A:h}
source $FG/load_host.zsh && so101_load_host || exit 2
G=${GATE:?set GATE}
GB=${GATE_BUILD:?set GATE_BUILD}
SCR=${GATE_SCRATCH:?set GATE_SCRATCH}
FZ=$DEPS_FREEZE
WT=${FG:h:h}
TEST_PYTHON=$DEMO_PYTHON
test -x $TEST_PYTHON && test -r $GB/install/setup.zsh && test -d $FZ/python-deps && test "$(cat $G/build-root.txt)" = "$GB" || exit 90
for f in /opt/ros/jazzy/setup.zsh $GB/install/setup.zsh; do source $f 2>/dev/null || exit 91; done
run=$(mktemp -d $GB/demo-run.XXXXXXXX) || exit 92
scratch=$(mktemp -d $SCR/demo-run.XXXXXXXX) || exit 92
mkdir $scratch/tmp || exit 92
print -r -- $scratch > $run/scratch-path.txt
export TMPDIR=$scratch/tmp TMP=$scratch/tmp TEMP=$scratch/tmp PYTHONNOUSERSITE=1
# Headless EGL as in the build and colcon stages (without it the MuJoCo camera tests fail with a gladLoadGL error).
export MUJOCO_GL=egl
# Per-host glibc malloc settings of this stage only (empty value = not set).
[[ -n ${DEMO_MALLOC_ARENA_MAX:-} ]] && export MALLOC_ARENA_MAX=$DEMO_MALLOC_ARENA_MAX
[[ -n ${DEMO_MALLOC_TRIM_THRESHOLD:-} ]] && export MALLOC_TRIM_THRESHOLD_=$DEMO_MALLOC_TRIM_THRESHOLD
[[ -n ${DEMO_MALLOC_MMAP_THRESHOLD:-} ]] && export MALLOC_MMAP_THRESHOLD_=$DEMO_MALLOC_MMAP_THRESHOLD
ipc=$(mktemp -d /tmp/so101-ipc.XXXXXXXX) || exit 94
chmod 0700 $ipc
export SO101_IPC_SOCKET_BASE=$ipc
# Own ROS domain + loopback-only discovery for this stage (tests calling rclpy.init(domain_id=..) keep their explicit domain).
unset DISABLE_ROS_ISOLATION
if [[ ${ISOLATE_ROS:-1} == 1 ]]; then
  export ROS_DOMAIN_ID=${DEMO_ROS_DOMAIN_ID:-203} ROS_LOCALHOST_ONLY=1 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
fi
print -r -- "workers=${DEMO_WORKERS:-16} ROS_DOMAIN_ID=${ROS_DOMAIN_ID-<unset>} ROS_LOCALHOST_ONLY=${ROS_LOCALHOST_ONLY-<unset>} ROS_AUTOMATIC_DISCOVERY_RANGE=${ROS_AUTOMATIC_DISCOVERY_RANGE-<unset>}" > $run/ros-env.txt
export PYTHONPATH=$FG/pytest-plugin:${GATE_EXTRA_PYTHONPATH:+$GATE_EXTRA_PYTHONPATH:}$FZ/python-deps:$PYTHONPATH:/usr/lib/python3/dist-packages
$TEST_PYTHON -c 'import os,pathlib,sys,tempfile,pytest,xdist,pydantic,so101_demo,so101_teleop; a=pathlib.Path(tempfile.gettempdir()).resolve(); assert a==pathlib.Path(os.environ["TMPDIR"]).resolve(); print("python=",sys.executable,"pytest=",pytest.__version__,"xdist=",xdist.__version__,"pydantic=",pydantic.__version__,"demo=",so101_demo.__file__,"teleop=",so101_teleop.__file__,"temp=",a,"cpu=",os.cpu_count())' > $run/tempfile-proof.log 2>&1 || { cat $run/tempfile-proof.log; exit 93; }
cat $run/tempfile-proof.log
grep -q "$GB/install" $run/tempfile-proof.log || { echo "NOT THE INSTALLED PACKAGE"; exit 95; }
cd $WT/src/so101_demo_py
workers=${DEMO_WORKERS:-16}
[[ $workers == <1-> ]] || exit 97
start=$SECONDS
# --dist only when the host config sets it (xdist default is "load").
argv=($TEST_PYTHON -m pytest ${(Q)${(z)GATE_DEMO_TARGETS:-test}} -n $workers ${DEMO_DIST:+--dist} ${DEMO_DIST} -q -p no:cacheprovider -p so101_pytest_worker_temp --junitxml=$run/junit.xml)
print -r -- "${(q)argv}" > $run/command.txt
$argv > $run/pytest.log 2>&1
rc=$?
print -r -- $rc > $run/actual.rc; print -r -- $(( SECONDS - start )) > $run/elapsed-seconds.txt
sed 's/\x1b\[[0-9;]*m//g' $run/pytest.log | tail -${TAILN:-6} | cut -c1-220
print "RUN=$run rc=$rc workers=$workers elapsed=$(( SECONDS - start ))s"
exit $rc
