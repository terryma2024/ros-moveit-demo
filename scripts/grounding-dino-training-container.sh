#!/bin/sh
set -eu

repository_root=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd -P)
dockerfile="$repository_root/src/so101_demo_py/docker/grounding-dino-training/Dockerfile"
default_image="so101-grounding-dino-tiny-train:torch2.13.0-cu130-transformers4.56.2"

usage() {
  printf '%s\n' \
    "Usage:" \
    "  scripts/grounding-dino-training-container.sh build [--image IMAGE] [--refresh-base]" \
    "  scripts/grounding-dino-training-container.sh train --train-images DIR --val-images DIR" \
    "    --train-inventory FILE --val-inventory FILE --base-model DIR --output NEW_ROOT" \
    "    --mode smoke|formal --training-commit SHA [--image IMAGE] [--resume-checkpoint DIR]" >&2
  exit 2
}

absolute_file() {
  input_file=$1
  if [ ! -f "$input_file" ] || [ -L "$input_file" ]; then
    printf 'required regular file does not exist: %s\n' "$input_file" >&2
    exit 2
  fi
  input_directory=$(CDPATH='' cd -- "$(dirname -- "$input_file")" && pwd -P)
  printf '%s/%s\n' "$input_directory" "$(basename -- "$input_file")"
}

absolute_directory() {
  input_directory=$1
  if [ ! -d "$input_directory" ] || [ -L "$input_directory" ]; then
    printf 'required directory does not exist: %s\n' "$input_directory" >&2
    exit 2
  fi
  CDPATH='' cd -- "$input_directory" && pwd -P
}

reject_mount_path() {
  case $1 in
    *,* | *:*)
      printf 'Docker bind-mount path must not contain comma or colon: %s\n' "$1" >&2
      exit 2
      ;;
  esac
}

[ "$#" -gt 0 ] || usage
command_name=$1
shift

case $command_name in
  build)
    image=$default_image
    refresh_base=false
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
        *) usage ;;
      esac
    done
    set -- build
    [ "$refresh_base" = false ] || set -- "$@" --pull
    set -- "$@" --platform linux/amd64 --provenance=false \
      --file "$dockerfile" --tag "$image" "$repository_root"
    exec docker "$@"
    ;;
  train)
    image=$default_image
    train_images=
    val_images=
    train_inventory=
    val_inventory=
    base_model=
    output=
    mode=
    training_commit=
    resume_checkpoint=
    while [ "$#" -gt 0 ]; do
      case $1 in
        --image | --train-images | --val-images | --train-inventory | --val-inventory | --base-model | --output | --mode | --training-commit | --resume-checkpoint)
          [ "$#" -ge 2 ] || usage
          option_name=$1
          option_value=$2
          shift 2
          case $option_name in
            --image) image=$option_value ;;
            --train-images) train_images=$option_value ;;
            --val-images) val_images=$option_value ;;
            --train-inventory) train_inventory=$option_value ;;
            --val-inventory) val_inventory=$option_value ;;
            --base-model) base_model=$option_value ;;
            --output) output=$option_value ;;
            --mode) mode=$option_value ;;
            --training-commit) training_commit=$option_value ;;
            --resume-checkpoint) resume_checkpoint=$option_value ;;
          esac
          ;;
        *) usage ;;
      esac
    done
    if [ -z "$train_images" ] || [ -z "$val_images" ] \
      || [ -z "$train_inventory" ] || [ -z "$val_inventory" ] \
      || [ -z "$base_model" ] || [ -z "$output" ] \
      || [ -z "$mode" ] || [ -z "$training_commit" ]; then
      usage
    fi
    case $mode in smoke | formal) ;; *) usage ;; esac
    case $training_commit in
      *[!0-9a-f]* | ??????????????????????????????????????? | ?????????????????????????????????????????*) usage ;;
    esac
    train_images=$(absolute_directory "$train_images")
    val_images=$(absolute_directory "$val_images")
    train_inventory=$(absolute_file "$train_inventory")
    val_inventory=$(absolute_file "$val_inventory")
    base_model=$(absolute_directory "$base_model")
    output_parent=$(CDPATH='' cd -- "$(dirname -- "$output")" 2>/dev/null && pwd -P) || {
      printf 'output parent directory does not exist: %s\n' "$(dirname -- "$output")" >&2
      exit 2
    }
    output_name=$(basename -- "$output")
    if [ -z "$output_name" ] || [ "$output_name" = . ] || [ "$output_name" = .. ]; then
      usage
    fi
    [ ! -e "$output_parent/$output_name" ] || {
      printf 'training output root already exists: %s\n' "$output_parent/$output_name" >&2
      exit 2
    }
    for mount_source in "$train_images" "$val_images" "$train_inventory" "$val_inventory" "$base_model" "$output_parent"; do
      reject_mount_path "$mount_source"
    done
    if [ -n "$resume_checkpoint" ]; then
      resume_checkpoint=$(absolute_directory "$resume_checkpoint")
      reject_mount_path "$resume_checkpoint"
    fi
    set -- run --rm \
      --gpus all \
      --network none \
      --shm-size 8g \
      --user "$(id -u):$(id -g)" \
      --env HF_HUB_OFFLINE=1 \
      --env TRANSFORMERS_OFFLINE=1 \
      --env CUDA_VISIBLE_DEVICES=0 \
      --env CUBLAS_WORKSPACE_CONFIG=:4096:8 \
      --env PYTHONUNBUFFERED=1 \
      --env HOME=/training-output \
      --mount "type=bind,src=$train_images,dst=/images/train,readonly" \
      --mount "type=bind,src=$val_images,dst=/images/val,readonly" \
      --mount "type=bind,src=$train_inventory,dst=/inventories/train.json,readonly" \
      --mount "type=bind,src=$val_inventory,dst=/inventories/val.json,readonly" \
      --mount "type=bind,src=$base_model,dst=/models/grounding-dino-tiny,readonly" \
      --mount "type=bind,src=$output_parent,dst=/training-output"
    if [ -n "$resume_checkpoint" ]; then
      set -- "$@" --mount "type=bind,src=$resume_checkpoint,dst=/resume,readonly"
    fi
    set -- "$@" "$image" \
      --contract /opt/so101_demo_py/config/perception/grounding_dino_training.yaml \
      --train-inventory /inventories/train.json \
      --val-inventory /inventories/val.json \
      --train-images /images/train \
      --val-images /images/val \
      --base-model /models/grounding-dino-tiny \
      --output "/training-output/$output_name" \
      --mode "$mode" \
      --training-commit "$training_commit"
    [ -z "$resume_checkpoint" ] || set -- "$@" --resume-checkpoint /resume
    exec docker "$@"
    ;;
  *) usage ;;
esac
