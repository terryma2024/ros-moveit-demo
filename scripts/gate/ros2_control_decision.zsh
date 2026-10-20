#!/usr/bin/env zsh
# Decide whether the tests of controller_manager and hardware_interface_testing may be skipped. Read only.
# usage: ros2_control_decision.zsh <out-json|/dev/stdout> <full 0|1>   prints "skip" or "run" on stdout.
set -o pipefail
FG=${0:A:h}
source $FG/load_host.zsh && so101_load_host || exit 2
R=$EVIDENCE_R
WT=${FG:h:h}
out=${1:?out}; full=${2:-0}
tree=$(git -C $WT rev-parse HEAD:third_party/ros2_control) || exit 80
dirty=$(git -C $WT status --porcelain --untracked-files=all -- third_party/ros2_control | wc -l) || exit 81
apt=$(dpkg-query -W -f='${Package} ${Version}\n' 'ros-jazzy-*' | sort | sha256sum | cut -c1-64) || exit 82
test -n "$tree" && test -n "$apt" || exit 83
python3 -I $FG/rc_record.py decide --gates $R/gates --seed $R/gates/ros2-control-tests-baseline.json \
  --tree $tree --dirty $dirty --apt $apt --full $full --out $out
