#!/usr/bin/env zsh
# Build the inference and shard campaign images from the worktree this script lives in.
# usage: build_images.zsh [--host H] [--roles 'inference shard'] [--pin-shard-deps ID]
#   Host values (evidence root, build dependencies) come from scripts/gate/hosts/<host>.env. Roles: inference, shard-deps, shard.
#   The default builds inference and shard. shard-deps (the networked apt and pip base) is built on its own; the shard build starts
#   from the image that scripts/images/base-image-ids.json pins (--pin-shard-deps supplies the ID while that file has none).
set -o pipefail
FG=${0:A:h}
HOST_ARG=
ROLES=(inference shard)
PIN=()
while (( $# )); do
  case $1 in
    --host) HOST_ARG=${2:?--host needs a name}; shift 2;;
    --roles) ROLES=(${=2:?--roles needs a list}); shift 2;;
    --pin-shard-deps) PIN=(--pin-shard-deps ${2:?--pin-shard-deps needs an image ID}); shift 2;;
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
