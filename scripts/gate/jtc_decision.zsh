#!/usr/bin/env zsh
# Decide whether the UPSTREAM joint_trajectory_controller suite may be skipped. Read only.
# usage: jtc_decision.zsh <out-json|/dev/stdout> <full 0|1>   prints "skip" or "run" on stdout.
# Same rule as ros2_control_decision.zsh, with its own record (gates/*/jtc-tests.json, seed gates/jtc-tests-baseline.json,
# which does not exist, so the first gate always runs it) keyed on the tree object of third_party/ros2_controllers and
# the installed ros-jazzy-* package set. The local test (test_state_queue_publication) is never skipped.
set -o pipefail
FG=${0:A:h}
source $FG/load_host.zsh && so101_load_host || exit 2
R=$EVIDENCE_R
WT=${FG:h:h}
out=${1:?out}; full=${2:-0}
tree=$(git -C $WT rev-parse HEAD:third_party/ros2_controllers) || exit 80
dirty=$(git -C $WT status --porcelain --untracked-files=all -- third_party/ros2_controllers | wc -l) || exit 81
apt=$(dpkg-query -W -f='${Package} ${Version}\n' 'ros-jazzy-*' | sort | sha256sum | cut -c1-64) || exit 82
test -n "$tree" && test -n "$apt" || exit 83
python3 -I $FG/rc_record.py decide --gates $R/gates --seed $R/gates/jtc-tests-baseline.json \
  --record-name jtc-tests.json --label third_party/ros2_controllers --packages joint_trajectory_controller \
  --tree $tree --dirty $dirty --apt $apt --full $full --out $out
