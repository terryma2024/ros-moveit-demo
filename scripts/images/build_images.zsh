#!/usr/bin/env zsh
# Build the inference and shard campaign images from the worktree this script lives in.
# usage: build_images.zsh [--host H]    Host values (evidence root, build dependencies) come from scripts/gate/hosts/<host>.env.
set -o pipefail
FG=${0:A:h}
HOST_ARG=
[[ ${1:-} == --host ]] && HOST_ARG=${2:?--host needs a name}
source ${FG:h}/gate/load_host.zsh && so101_load_host $HOST_ARG || exit 2
R=$EVIDENCE_R
WT=${FG:h:h}
cd $WT || exit 2
for role in inference shard; do
  head_before=$(git -C $WT rev-parse HEAD)
  out=$(/usr/bin/python3 $FG/prepare-image-build.py --role $role) || { print "prepare $role failed"; exit 1; }
  print -r -- "$out"
  dir=$(cat $R/current-$role-image-build-path.txt)
  [[ -n $(git -C $WT status --short -- src scripts third_party) ]] && { print "dirty after prepare"; exit 2; }
  [[ $(git -C $WT rev-parse HEAD) == $head_before ]] || { print "HEAD changed"; exit 3; }
  print "build $role in $dir"
  /usr/bin/python3 $dir/build.py || { print "build $role failed"; exit 4; }
  docker image inspect "$(cat $dir/$role.iid)" > $dir/$role-image-inspect.json || exit 5
  print "$role iid $(cat $dir/$role.iid) head $head_before"
done
