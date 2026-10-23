#!/usr/bin/env zsh
# Build the so101-mount-base image (dependencies only; the project code is mounted at run time) from the worktree this script lives in.
# usage: build_images.zsh [--host H] [--no-cache]
#   Host values (evidence root, proxy) come from scripts/gate/hosts/<host>.env. The only role is mount-base.
set -o pipefail
FG=${0:A:h}
HOST_ARG=
ROLES=(mount-base)
PIN=()
while (( $# )); do
  case $1 in
    --host) HOST_ARG=${2:?--host needs a name}; shift 2;;
    --no-cache) PIN+=(--no-cache); shift;;
    *) print "unknown argument $1"; exit 2;;
  esac
done
source ${FG:h}/gate/load_host.zsh && so101_load_host $HOST_ARG || exit 2
R=$EVIDENCE_R
WT=${FG:h:h}
cd $WT || exit 2
for role in $ROLES; do
  head_before=$(git -C $WT rev-parse HEAD)
  out=$(/usr/bin/python3 $FG/prepare-image-build.py --role $role $PIN) || { print "prepare $role failed"; exit 1; }
  print -r -- "$out"
  dir=$(cat $R/current-$role-image-build-path.txt)
  [[ -n $(git -C $WT status --short -- src scripts third_party) ]] && { print "dirty after prepare"; exit 2; }
  [[ $(git -C $WT rev-parse HEAD) == $head_before ]] || { print "HEAD changed"; exit 3; }
  print "build $role in $dir"
  /usr/bin/python3 $dir/build.py || { print "build $role failed"; exit 4; }
  docker image inspect "$(cat $dir/$role.iid)" > $dir/$role-image-inspect.json || exit 5
  print "$role iid $(cat $dir/$role.iid) head $head_before"
done
