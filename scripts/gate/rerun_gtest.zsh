#!/usr/bin/env zsh
# run one gtest binary of a gate build root N times: rerun_gtest.zsh <gate-id> <package> <binary> <n> [--gtest_filter=...]
set -o pipefail
FG=${0:A:h}
source $FG/load_host.zsh && so101_load_host || exit 2
ID=${1:?id}; PKG=${2:?pkg}; BIN=${3:?bin}; N=${4:?n}; shift 4
GB=$BUILD_ROOT/gates/$ID
for f in /opt/ros/jazzy/setup.zsh $GB/install/setup.zsh; do source $f 2>/dev/null || exit 91; done
export ROS_DOMAIN_ID=203 ROS_LOCALHOST_ONLY=1
fails=0
for i in {1..$N}; do
  $GB/build/$PKG/$BIN "$@" > /tmp/so101-debug-gtest-$ID-$i.log 2>&1 || fails=$((fails+1))
done
print "runs=$N failures=$fails"
exit $(( fails > 0 ))
