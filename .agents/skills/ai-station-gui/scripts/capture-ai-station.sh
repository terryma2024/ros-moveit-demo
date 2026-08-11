#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
HELPER="$SCRIPT_DIR/ai-station-capture.py"
SSH_TARGET=${AI_STATION_SSH_TARGET:-ai-station}
REMOTE_SCRIPT=${AI_STATION_CAPTURE_SCRIPT:-.local/bin/ai-station-capture.py}
mode=""
output_root=""
test_ghostty_tabs=0

usage() {
  printf 'Usage: %s [--local|--remote] --output-root DIR [--test-ghostty-tabs]\n' "$0" >&2
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
      if (( $# < 2 )); then
        usage
        exit 2
      fi
      output_root=$2
      shift 2
      ;;
    --test-ghostty-tabs)
      test_ghostty_tabs=1
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

if [[ -z "$output_root" ]]; then
  printf -- '--output-root is required.\n' >&2
  exit 2
fi
if [[ ! -f "$HELPER" ]]; then
  printf 'Capture helper is missing: %s\n' "$HELPER" >&2
  exit 2
fi

mkdir -p -- "$output_root"
output_root=$(realpath -- "$output_root")
case "$SCRIPT_DIR" in
  */.agents/skills/ai-station-gui/scripts)
    repo_root=${SCRIPT_DIR%/.agents/skills/ai-station-gui/scripts}
    case "$output_root/" in
      "$repo_root/"*)
        printf 'Capture output must be outside the source tree: %s\n' "$repo_root" >&2
        exit 2
        ;;
    esac
    ;;
esac

if [[ -z "$mode" ]]; then
  host=$(hostname -s)
  if [[ ( "$host" == AI-STATION-* || "$host" == ai-station* ) &&
        ( "$PWD" == /data/work/ws_moveit* || "$SCRIPT_DIR" == /data/work/ws_moveit* ) ]]; then
    mode=local
  else
    mode=remote
  fi
fi

helper_args=(--output-root "$output_root")
if (( test_ghostty_tabs )); then
  helper_args+=(--test-ghostty-tabs)
fi

validate_manifest() {
  python3 -c '
import json, re, sys
payload = json.load(sys.stdin)
required = {
    "captured_at", "desktop", "rviz", "ghostty", "captured_windows",
    "missing_windows", "capture_mode", "ghostty_tab_test",
}
missing = sorted(required - payload.keys())
if missing:
    raise SystemExit(f"manifest missing keys: {missing}")
if not isinstance(payload["captured_at"], str) or not re.fullmatch(r"[A-Za-z0-9T:_-]+", payload["captured_at"]):
    raise SystemExit("invalid captured_at")
if not isinstance(payload["desktop"], str) or not payload["desktop"]:
    raise SystemExit("desktop must be a nonempty string")
for name in ("rviz", "ghostty"):
    if payload[name] is not None and (not isinstance(payload[name], str) or not payload[name]):
        raise SystemExit(f"{name} must be null or a nonempty string")
if not isinstance(payload["captured_windows"], list) or not isinstance(payload["missing_windows"], list):
    raise SystemExit("window lists must be arrays")
if payload["capture_mode"] not in {"desktop_only", "desktop_and_windows"}:
    raise SystemExit("invalid capture_mode")
if payload["ghostty_tab_test"] not in {"not_requested", "completed", "skipped_no_window"}:
    raise SystemExit("invalid ghostty_tab_test")
print(payload["captured_at"])
print(payload["desktop"])
print(payload["rviz"] or "")
print(payload["ghostty"] or "")
'
}

read_manifest_fields() {
  mapfile -t manifest_fields < <(validate_manifest <<<"$manifest")
  if (( ${#manifest_fields[@]} != 4 )); then
    printf 'Manifest field extraction failed.\n' >&2
    exit 1
  fi
  captured_at=${manifest_fields[0]}
  desktop_path=${manifest_fields[1]}
  rviz_path=${manifest_fields[2]}
  ghostty_path=${manifest_fields[3]}
}

write_manifest() {
  local destination=$1
  printf '%s\n' "$manifest" > "$destination/manifest.json"
}

print_summary() {
  local destination=$1
  printf 'Desktop: %s/desktop.png\n' "$destination"
  if [[ -n "$rviz_path" ]]; then
    printf 'RViz: %s/rviz.png\n' "$destination"
  else
    printf 'RViz: not present\n'
  fi
  if [[ -n "$ghostty_path" ]]; then
    printf 'Ghostty: %s/ghostty.png\n' "$destination"
  else
    printf 'Ghostty: not present\n'
  fi
  printf 'Manifest: %s/manifest.json\n' "$destination"
}

if [[ "$mode" == local ]]; then
  manifest=$(python3 "$HELPER" "${helper_args[@]}")
  read_manifest_fields
  desktop_real=$(realpath -- "$desktop_path")
  case "$desktop_real" in
    "$output_root"/*) ;;
    *)
      printf 'Local desktop is outside the current output root.\n' >&2
      exit 1
      ;;
  esac
  if [[ ! -s "$desktop_real" ]]; then
    printf 'Declared desktop is missing or empty: %s\n' "$desktop_path" >&2
    exit 1
  fi
  destination=$(dirname -- "$desktop_real")
  for optional_path in "$rviz_path" "$ghostty_path"; do
    if [[ -n "$optional_path" && ! -s "$optional_path" ]]; then
      printf 'Declared optional artifact is missing or empty: %s\n' "$optional_path" >&2
      exit 1
    fi
  done
  write_manifest "$destination"
  print_summary "$destination"
  exit 0
fi

ssh "$SSH_TARGET" 'mkdir -p "$HOME/.local/bin"'
scp "$HELPER" "$SSH_TARGET:$REMOTE_SCRIPT"
ssh "$SSH_TARGET" "chmod 755 \"\$HOME/$REMOTE_SCRIPT\""
remote_args=(--output-root /tmp/ai-station-gui-captures)
if (( test_ghostty_tabs )); then
  remote_args+=(--test-ghostty-tabs)
fi
printf -v remote_command '"$HOME/%s"' "$REMOTE_SCRIPT"
for argument in "${remote_args[@]}"; do
  printf -v quoted_argument '%q' "$argument"
  remote_command+=" $quoted_argument"
done
manifest=$(ssh "$SSH_TARGET" "$remote_command")
read_manifest_fields

destination=$(mktemp -d "$output_root/${captured_at}-XXXXXXXX")
scp "$SSH_TARGET:$desktop_path" "$destination/desktop.png"
if [[ ! -s "$destination/desktop.png" ]]; then
  printf 'Transferred desktop is missing or empty.\n' >&2
  exit 1
fi
if [[ -n "$rviz_path" ]]; then
  scp "$SSH_TARGET:$rviz_path" "$destination/rviz.png"
  [[ -s "$destination/rviz.png" ]] || exit 1
fi
if [[ -n "$ghostty_path" ]]; then
  scp "$SSH_TARGET:$ghostty_path" "$destination/ghostty.png"
  [[ -s "$destination/ghostty.png" ]] || exit 1
fi
write_manifest "$destination"
print_summary "$destination"
