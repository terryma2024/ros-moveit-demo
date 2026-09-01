#!/bin/sh
set -eu

repository_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd -P)
dockerfile="$repository_root/src/so101_demo_py/docker/yolo-inference/Dockerfile"
default_image="so101-yolo11n-seg-inference:ros-jazzy-torch2.13.0-cu130-ultralytics8.4.115"

usage() {
  cat >&2 <<'EOF'
Usage:
  scripts/yolo-seg-inference-container.sh build [--image IMAGE] [--refresh-base]
    [--cache-from CACHE_SPEC] [--cache-to CACHE_SPEC]
EOF
  exit 2
}

[ "$#" -gt 0 ] || usage
command=$1
shift

case $command in
  build)
    image=$default_image
    refresh_base=false
    cache_from=
    cache_to=
    while [ "$#" -gt 0 ]; do
      case $1 in
        --image)
          [ "$#" -ge 2 ] || usage
          image=$2
          shift 2
          ;;
        --refresh-base)
          refresh_base=true
          shift
          ;;
        --cache-from)
          [ "$#" -ge 2 ] && [ -n "$2" ] || usage
          cache_from=$2
          shift 2
          ;;
        --cache-to)
          [ "$#" -ge 2 ] && [ -n "$2" ] || usage
          cache_to=$2
          shift 2
          ;;
        *) usage ;;
      esac
    done
    if [ -n "$cache_from" ] || [ -n "$cache_to" ]; then
      set -- buildx build --load
    else
      set -- build
    fi
    [ "$refresh_base" = false ] || set -- "$@" --pull
    set -- "$@" --platform linux/amd64 --provenance=false \
      --file "$dockerfile" --tag "$image"
    [ -z "$cache_from" ] || set -- "$@" --cache-from "$cache_from"
    [ -z "$cache_to" ] || set -- "$@" --cache-to "$cache_to"
    set -- "$@" "$repository_root"
    exec docker "$@"
    ;;
  *) usage ;;
esac
