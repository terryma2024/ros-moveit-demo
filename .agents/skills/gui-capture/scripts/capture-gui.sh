#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
HELPER="$SCRIPT_DIR/gui-capture.py"
SSH_TARGET=${GUI_CAPTURE_SSH_TARGET:-ai-station}
REMOTE_SCRIPT=${GUI_CAPTURE_REMOTE_SCRIPT:-.local/bin/gui-capture.py}
mode=""
output_root=""
selector_args=()
platform_args=()
list_windows=0

usage() {
  printf 'Usage: %s (--local|--remote) [--output-root DIR] (--window QUERY|--window-id ID|--desktop|--list-windows) [--platform auto|macos|gnome-x11]\n' "$0" >&2
}

while (( $# )); do
  case "$1" in
    --local|--remote)
      requested=${1#--}
      if [[ -n "$mode" && "$mode" != "$requested" ]]; then
        printf 'Choose exactly one of --local or --remote.\n' >&2
        exit 2
      fi
      mode=$requested
      shift
      ;;
    --output-root)
      (( $# >= 2 )) || { usage; exit 2; }
      output_root=$2
      shift 2
      ;;
    --window|--window-id|--platform)
      (( $# >= 2 )) || { usage; exit 2; }
      if [[ "$1" == --platform ]]; then
        platform_args=("$1" "$2")
      else
        selector_args+=("$1" "$2")
      fi
      shift 2
      ;;
    --desktop)
      selector_args+=("$1")
      shift
      ;;
    --list-windows)
      list_windows=1
      selector_args+=("$1")
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf 'Unknown argument: %s\n' "$1" >&2
      usage
      exit 2
      ;;
  esac
done

if [[ -z "$mode" ]]; then
  printf 'Choose exactly one of --local or --remote.\n' >&2
  exit 2
fi
if [[ ! -f "$HELPER" ]]; then
  printf 'Capture helper is missing: %s\n' "$HELPER" >&2
  exit 2
fi
if (( ! list_windows )) && [[ -z "$output_root" ]]; then
  printf -- '--output-root is required for capture.\n' >&2
  exit 2
fi

if [[ -n "$output_root" ]]; then
  mkdir -p -- "$output_root"
  output_root=$(realpath -- "$output_root")
  case "$SCRIPT_DIR" in
    */.agents/skills/gui-capture/scripts)
      repo_root=${SCRIPT_DIR%/.agents/skills/gui-capture/scripts}
      case "$output_root/" in
        "$repo_root/"*)
          printf 'Capture output must be outside the source tree: %s\n' "$repo_root" >&2
          exit 2
          ;;
      esac
      ;;
  esac
fi

helper_args=("${selector_args[@]}" "${platform_args[@]}")

validate_manifest() {
  python3 -c '
import json, re, sys
payload = json.load(sys.stdin)
required = {"captured_at", "platform", "session_type", "capture_mode", "selector", "window", "image"}
missing = sorted(required - payload.keys())
if missing:
    raise SystemExit(f"manifest missing keys: {missing}")
if not isinstance(payload["captured_at"], str) or not re.fullmatch(r"[A-Za-z0-9T:_-]+", payload["captured_at"]):
    raise SystemExit("invalid captured_at")
if payload["platform"] not in {"macos", "gnome"}:
    raise SystemExit("invalid platform")
if payload["capture_mode"] not in {"window", "desktop"}:
    raise SystemExit("invalid capture_mode")
if not isinstance(payload["image"], str) or not payload["image"]:
    raise SystemExit("image must be a nonempty string")
if payload["capture_mode"] == "window" and not isinstance(payload["window"], dict):
    raise SystemExit("window metadata is required for window capture")
if payload["capture_mode"] == "desktop" and payload["window"] is not None:
    raise SystemExit("desktop capture must not declare a target window")
print(payload["captured_at"])
print(payload["image"])
'
}

read_manifest_fields() {
  validated_fields=$(validate_manifest <<<"$manifest")
  case "$validated_fields" in
    *$'\n'*) ;;
    *)
      printf 'Manifest field extraction failed.\n' >&2
      exit 1
      ;;
  esac
  captured_at=${validated_fields%%$'\n'*}
  image_path=${validated_fields#*$'\n'}
  [[ -n "$captured_at" && -n "$image_path" && "$image_path" != *$'\n'* ]] || {
    printf 'Manifest field extraction failed.\n' >&2
    exit 1
  }
}

if [[ "$mode" == local ]]; then
  if (( list_windows )); then
    exec python3 "$HELPER" "${helper_args[@]}"
  fi
  manifest=$(python3 "$HELPER" --output-root "$output_root" "${helper_args[@]}")
  read_manifest_fields
  image_real=$(realpath -- "$image_path")
  case "$image_real" in
    "$output_root"/*) ;;
    *)
      printf 'Local image is outside the current output root.\n' >&2
      exit 1
      ;;
  esac
  [[ -s "$image_real" ]] || {
    printf 'Declared image is missing or empty: %s\n' "$image_path" >&2
    exit 1
  }
  destination=$(dirname -- "$image_real")
  printf '%s\n' "$manifest" > "$destination/manifest.json"
  printf 'Image: %s\nManifest: %s/manifest.json\n' "$image_real" "$destination"
  exit 0
fi

ssh "$SSH_TARGET" 'mkdir -p "$HOME/.local/bin"'
scp "$HELPER" "$SSH_TARGET:$REMOTE_SCRIPT"
ssh "$SSH_TARGET" "chmod 755 \"\$HOME/$REMOTE_SCRIPT\""
remote_args=("${helper_args[@]}")
if (( ! list_windows )); then
  remote_args=(--output-root /tmp/gui-captures "${remote_args[@]}")
fi
printf -v remote_command '"$HOME/%s"' "$REMOTE_SCRIPT"
for argument in "${remote_args[@]}"; do
  printf -v quoted_argument '%q' "$argument"
  remote_command+=" $quoted_argument"
done
if (( list_windows )); then
  exec ssh "$SSH_TARGET" "$remote_command"
fi
manifest=$(ssh "$SSH_TARGET" "$remote_command")
read_manifest_fields

destination=$(mktemp -d "$output_root/${captured_at}-XXXXXXXX")
local_name=$(basename -- "$image_path")
scp "$SSH_TARGET:$image_path" "$destination/$local_name"
[[ -s "$destination/$local_name" ]] || {
  printf 'Transferred image is missing or empty.\n' >&2
  exit 1
}
printf '%s\n' "$manifest" > "$destination/manifest.json"
printf 'Image: %s/%s\nManifest: %s/manifest.json\n' "$destination" "$local_name" "$destination"
