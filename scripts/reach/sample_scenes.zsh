#!/usr/bin/zsh
# Scene sampling with N light reachability stacks (default 16): start the stacks, run act_scene_sample with one --reach-command per stack,
# stop the stacks. Everything after `--` goes to act_scene_sample unchanged (--state, --rollout-points, --lists, --scenes-output-dir, ...).
#
# usage: sample_scenes.zsh --image ID --install DIR --source DIR --work-dir DIR --commit HEX40 [--stacks 16] [--first-domain 181] -- ARGS...
# Per-point verdicts match the full execution stack except on borderline points (scripts/reach/compare_verdicts.py).
set -o pipefail
IMAGE= INSTALL= SOURCE= WORK= COMMIT= STACKS=16 FIRST=181
while (( $# )); do
  case $1 in
    --image) IMAGE=$2; shift 2;;
    --install) INSTALL=$2; shift 2;;
    --source) SOURCE=$2; shift 2;;
    --work-dir) WORK=$2; shift 2;;
    --commit) COMMIT=$2; shift 2;;
    --stacks) STACKS=$2; shift 2;;
    --first-domain) FIRST=$2; shift 2;;
    --) shift; break;;
    *) print -u2 "unknown argument $1"; exit 2;;
  esac
done
HERE=${0:A:h}
zsh $HERE/light_stacks.zsh start $STACKS --image "$IMAGE" --install "$INSTALL" --source "$SOURCE" --work-dir "$WORK" --commit "$COMMIT" --first-domain $FIRST || { zsh $HERE/light_stacks.zsh stop $STACKS; exit 1; }
cmds=()
for ((i=0;i<STACKS;i++)); do cmds+=(--reach-command "zsh $HERE/reach_call.zsh $WORK/s$i reachlight$i $((FIRST+i)) $INSTALL"); done
python3 -B -m so101_demo.cli.act_scene_sample "$@" $cmds
rc=$?
zsh $HERE/light_stacks.zsh stop $STACKS
exit $rc
