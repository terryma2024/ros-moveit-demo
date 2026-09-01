#!/bin/sh
set -eu

repository_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd -P)
dockerfile="$repository_root/src/so101_demo_py/docker/yolo-training/Dockerfile"
default_image="so101-yolo11n-seg-train:torch2.13.0-cu130-ultralytics8.4.115"

usage() {
  cat >&2 <<'EOF'
Usage:
  scripts/yolo-seg-training-container.sh build [--image IMAGE] [--refresh-base]
    [--cache-from CACHE_SPEC] [--cache-to CACHE_SPEC]
  scripts/yolo-seg-training-container.sh train --dataset DATASET_YAML \
    --model YOLO11N_SEG_PT --output NEW_OUTPUT_ROOT [options]

Train options:
  --image IMAGE       Built image tag (default is the repository-pinned tag)
  --run-name NAME     Ultralytics run name (default: train)
  --epochs COUNT      Positive smoke or training override
  --fraction VALUE    Training data fraction in (0, 1]
EOF
  exit 2
}

absolute_file() {
  file=$1
  [ -f "$file" ] || {
    printf 'required file does not exist: %s\n' "$file" >&2
    exit 2
  }
  directory=$(CDPATH= cd -- "$(dirname -- "$file")" && pwd -P)
  printf '%s/%s\n' "$directory" "$(basename -- "$file")"
}

reject_unsupported_mount_path() {
  case $1 in
    *,* | *:*)
      printf 'Docker bind-mount path must not contain comma or colon: %s\n' "$1" >&2
      exit 2
      ;;
  esac
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
  train)
    image=$default_image
    dataset=
    model=
    output=
    run_name=train
    epochs=
    fraction=
    while [ "$#" -gt 0 ]; do
      case $1 in
        --image | --dataset | --model | --output | --run-name | --epochs | --fraction)
          [ "$#" -ge 2 ] || usage
          option=$1
          value=$2
          shift 2
          case $option in
            --image) image=$value ;;
            --dataset) dataset=$value ;;
            --model) model=$value ;;
            --output) output=$value ;;
            --run-name) run_name=$value ;;
            --epochs) epochs=$value ;;
            --fraction) fraction=$value ;;
          esac
          ;;
        *) usage ;;
      esac
    done
    [ -n "$dataset" ] && [ -n "$model" ] && [ -n "$output" ] || usage
    dataset=$(absolute_file "$dataset")
    model=$(absolute_file "$model")
    output_parent=$(CDPATH= cd -- "$(dirname -- "$output")" 2>/dev/null && pwd -P) || {
      printf 'output parent directory does not exist: %s\n' "$(dirname -- "$output")" >&2
      exit 2
    }
    output_name=$(basename -- "$output")
    [ -n "$output_name" ] && [ "$output_name" != "." ] && [ "$output_name" != ".." ] || usage
    [ ! -e "$output_parent/$output_name" ] || {
      printf 'training output root already exists: %s\n' "$output_parent/$output_name" >&2
      exit 2
    }
    dataset_root=$(dirname -- "$dataset")
    dataset_name=$(basename -- "$dataset")
    reject_unsupported_mount_path "$dataset_root"
    reject_unsupported_mount_path "$model"
    reject_unsupported_mount_path "$output_parent"

    set -- run --rm \
      --gpus all \
      --network none \
      --shm-size 8g \
      --user "$(id -u):$(id -g)" \
      --env YOLO_OFFLINE=true \
      --env HOME=/tmp/yolo-home \
      --env YOLO_CONFIG_DIR=/opt/ultralytics \
      --mount "type=bind,src=$dataset_root,dst=/dataset,readonly" \
      --mount "type=bind,src=$model,dst=/models/yolo11n-seg.pt,readonly" \
      --mount "type=bind,src=$output_parent,dst=/training-output" \
      "$image" \
      --contract /opt/so101_demo_py/config/perception/training.yaml \
      --dataset "/dataset/$dataset_name" \
      --base-model /models/yolo11n-seg.pt \
      --output "/training-output/$output_name" \
      --run-name "$run_name"
    [ -z "$epochs" ] || set -- "$@" --epochs "$epochs"
    [ -z "$fraction" ] || set -- "$@" --fraction "$fraction"
    exec docker "$@"
    ;;
  *) usage ;;
esac
