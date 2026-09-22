#!/bin/zsh
# One closed macOS live service window: one service, one console case, one receipt.
#
#   scripts/so101-macos-service-campaign-live-window.zsh \
#     --case w2|w1|retry --task-root <registered root> \
#     --selection-manifest <frozen 20-point selection> \
#     --install-prefix /opt/data/so101/workspace/install [--skip-run]
#
# The window owns the whole lifecycle: it writes a single-case functional manifest and a frozen
# service-launch document, proves with `playwright --list` that exactly one target case (plus the
# necessary preflight) is collected, refuses to start when port 8013 or the real stack is not empty,
# starts the installed service through `scripts/so101_macos_unified_service.py`, waits for `/health`,
# runs one Playwright project, then re-checks the owner identity, stops only that PID, and records
# the residue. It never signals a process it did not record, and it never deletes evidence.

emulate -L zsh
set -o pipefail
set -u

REGISTERED_WORKTREE="/Users/matianyi/Projects/ros-moveit-demo/.worktrees/so101-unified-webapp"
REGISTERED_TASK_ROOT="/tmp/so101-debug-macos-service-campaign-closure-2208b154-6e9f-4ae1-a448-1fa0101df9b1"
REGISTERED_PYTHON="/opt/ros2_jazzy/.venv/bin/python"
DEFAULT_INSTALL_PREFIX="/opt/data/so101/workspace/install"
SERVICE_URL="http://127.0.0.1:8013"
PORT=8013

case_name=""
task_root=""
selection_manifest=""
install_prefix="$DEFAULT_INSTALL_PREFIX"
skip_run=0

while (( $# > 0 )); do
  case "$1" in
    --case) case_name="$2"; shift 2 ;;
    --task-root) task_root="$2"; shift 2 ;;
    --selection-manifest) selection_manifest="$2"; shift 2 ;;
    --install-prefix) install_prefix="$2"; shift 2 ;;
    --skip-run) skip_run=1; shift ;;
    *) print -ru2 -- "unknown argument: $1"; exit 2 ;;
  esac
done

fail() { print -ru2 -- "LIVE_WINDOW_REFUSED $1: ${2:-}"; exit 2 }

[[ "$case_name" == (w2|w1|retry) ]] || fail "CASE_REQUIRED" "w2|w1|retry"
[[ "$task_root" == "$REGISTERED_TASK_ROOT" ]] || fail "TASK_ROOT_NOT_REGISTERED" "$task_root"
[[ -d "$task_root" ]] || fail "TASK_ROOT_MISSING" "$task_root"
[[ -n "$selection_manifest" && -f "$selection_manifest" ]] || fail "SELECTION_MANIFEST_REQUIRED"
[[ "$install_prefix" == "$DEFAULT_INSTALL_PREFIX" ]] || fail "INSTALL_PREFIX_NOT_REGISTERED"
[[ -d "$install_prefix" ]] || fail "INSTALL_PREFIX_MISSING" "$install_prefix"
[[ "$(git -C "$REGISTERED_WORKTREE" branch --show-current)" == "codex/so101-unified-webapp" ]] \
  || fail "BRANCH_NOT_REGISTERED"

worktree="$REGISTERED_WORKTREE"
web_root="$worktree/src/so101_teleop/web"
window_id="${case_name}-$(date -u +%Y%m%dT%H%M%SZ)-$$"
window_root="$task_root/remediation/windows/$window_id"
mkdir -p "$window_root"

# The console case each window owns. W2 is the parallel v4 route, W1 the sequential v6 route, and
# the retry window runs the same frozen twenty points as its own first pass before retrying.
case "$case_name" in
  w2) case_id="macos-w2-20"; mode="PARALLEL"; workers=2; points=20; project="fixed-n-execution"
      target_spec="expert-validation/live-sim/06-fixed-n-execution.spec.ts"; target_marker="R06 " ;;
  w1) case_id="macos-w1-20"; mode="SEQUENTIAL"; workers=1; points=20; project="fixed-n-execution"
      target_spec="expert-validation/live-sim/06-fixed-n-execution.spec.ts"; target_marker="R06 " ;;
  retry) case_id="macos-w1-20-retry"; mode="SEQUENTIAL"; workers=1; points=20; project="retry-full-restart"
      target_spec="expert-validation/live-sim/07-retry-full-restart.spec.ts"; target_marker="R07 " ;;
esac

functional_manifest="$window_root/functional-manifest.json"
"$REGISTERED_PYTHON" - "$functional_manifest" "$case_id" "$mode" "$workers" "$points" <<'PY'
import json, sys
path, case_id, mode, workers, points = sys.argv[1:6]
case = {
    "id": case_id,
    "mode": mode,
    "worker_count": int(workers),
    "point_count": int(points),
    "lifecycle": "FIRST_PASS",
    "maximum_attempts": 1,
    "batch_timeout_s": 2400.0,
}
json.dump({"cases": [case], "stability": case}, open(path, "w", encoding="utf-8"),
          indent=2, sort_keys=True)
PY
[[ -s "$functional_manifest" ]] || fail "FUNCTIONAL_MANIFEST_NOT_WRITTEN"

# The frozen identities the launcher re-resolves. They are read here, written into the launch
# document, and re-read by the launcher before it execs anything.
identity_report="$window_root/frozen-identities.json"
"$REGISTERED_PYTHON" - "$worktree" "$install_prefix" "$identity_report" <<'PY'
import hashlib, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(sys.argv[1]) / "scripts"))
from so101_macos_unified_service import (
    _directory_inventory_sha256, installed_web_bundle, CONSOLE_ENTRY_RELATIVE_PATH,
)
from so101_macos_runtime_contract import RuntimePaths
worktree, install_prefix, report = sys.argv[1:4]
paths = RuntimePaths.production(Path(worktree))
farm_entries = [
    {"name": entry.name, "resolved": str(entry.resolve(strict=True)),
     "size": entry.resolve(strict=True).stat().st_size}
    for entry in sorted(paths.dylib_farm.iterdir(), key=lambda item: item.name)
    if entry.name.endswith(".dylib")
]
document = {
    "install_prefix": str(paths.project_install),
    "install_inventory_sha256": _directory_inventory_sha256(paths.project_install),
    "web_bundle_sha256": _directory_inventory_sha256(installed_web_bundle(paths.project_install)),
    "farm_logical": str(paths.dylib_farm),
    "farm_resolved": str(paths.dylib_farm.resolve(strict=True)),
    "farm_manifest_sha256": hashlib.sha256(
        json.dumps(farm_entries, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
    "python": str(paths.python),
    "console_entry": CONSOLE_ENTRY_RELATIVE_PATH,
}
assert document["install_prefix"] == install_prefix, document["install_prefix"]
json.dump(document, open(report, "w", encoding="utf-8"), indent=2, sort_keys=True)
PY

# Every check that must hold before a service may exist.
[[ -z "$(/usr/sbin/lsof -nP -iTCP:$PORT -sTCP:LISTEN 2>/dev/null)" ]] \
  || fail "PORT_IN_USE" "$PORT"
if ps -axo pid=,command= | grep -E 'ros2_control_node|move_group|so101_unified_web_server|so101_mujoco_task_station' \
    | grep -v grep > /dev/null; then
  fail "STACK_PRESENT" "a real stack is already running"
fi

evidence_root="$window_root/browser"
state_root="$window_root/service-state"
socket_dir="$window_root/sockets"
mkdir -p "$evidence_root" "$state_root" "$socket_dir"
# The live fixture requires the run root to be a private directory inside the registered task root,
# so all three are created 0700 rather than with the ambient umask.
chmod 700 "$evidence_root" "$state_root" "$socket_dir"

launch_document="$window_root/service-launch.json"
"$REGISTERED_PYTHON" - "$launch_document" "$identity_report" "$case_id" "$evidence_root" \
    "$socket_dir" "$state_root" <<'PY'
import json, sys
launch_path, identity_path, case_id, evidence_root, socket_dir, state_root = sys.argv[1:7]
identity = json.load(open(identity_path, encoding="utf-8"))
document = {
    "schema_version": 1,
    "case_id": case_id,
    "host": "127.0.0.1",
    "port": 8013,
    "evidence_root": state_root,
    "socket_dir": socket_dir,
    "ros_domain_id": 211,
    **identity,
}
json.dump(document, open(launch_path, "w", encoding="utf-8"), indent=2, sort_keys=True)
PY

export SO101_TASK_ROOT="$task_root"
export TASK_ROOT="$task_root"
export SO101_LIVE_SIM_HOST="$(hostname)"
export SO101_LIVE_SERVICE_BASE_URL="$SERVICE_URL"
export SO101_LIVE_SERVICE_STATE_ROOT="$state_root"
export SO101_FUNCTIONAL_MANIFEST="$functional_manifest"
export SO101_FROZEN_SELECTION_MANIFEST="$selection_manifest"
export SO101_LIVE_CASE_ID="$case_id"
export SO101_E2E_EVIDENCE_ROOT="$evidence_root"
export SO101_E2E_INSTALL_PREFIX="$install_prefix"
export SO101_E2E_PYTHON="$REGISTERED_PYTHON"
export SO101_ENABLE_LIVE_SIM_E2E=1
export SO101_DEBUG_SOURCE_COMMIT="$(git -C "$worktree" rev-parse HEAD)"
export NODE_ENV=  # the Web gates read this; it must not be inherited
unset NODE_ENV

playwright_argv=(
  env -u NODE_ENV bunx playwright test
  --config playwright.live-sim.config.ts
  --project "$project"
  --workers=1
)

# Collection readback: the arguments above have to collect exactly the one target case and the
# preflight it depends on, and nothing else from the live-sim directory.
list_output="$window_root/playwright-list.txt"
( cd "$web_root" && "${playwright_argv[@]}" --list ) > "$list_output" 2>&1
list_rc=$?
[[ "$list_rc" -eq 0 ]] || fail "PLAYWRIGHT_LIST_FAILED" "$(tail -3 "$list_output")"
target_lines=$(grep -c "$target_marker" "$list_output")
[[ "$target_lines" -eq 1 ]] || fail "PLAYWRIGHT_LIST_NOT_SINGLE_CASE" "$target_lines"
# The R06 titles carry the manifest case id; the R07 title is a single frozen scenario, so its
# identity is the spec file itself plus the case id this window exported to the environment.
if [[ "$case_name" == "retry" ]]; then
  grep -q 'R07 ' "$list_output" || fail "PLAYWRIGHT_LIST_WRONG_CASE" "$case_id"
else
  grep -q "$case_id" "$list_output" || fail "PLAYWRIGHT_LIST_WRONG_CASE" "$case_id"
fi
collected_files=$(grep -o 'expert-validation/live-sim/[a-z0-9-]*\.spec\.ts' "$list_output" | sort -u)
expected_files=$(print -l "expert-validation/live-sim/preflight.spec.ts" "$target_spec" | sort -u)
[[ "$collected_files" == "$expected_files" ]] \
  || fail "PLAYWRIGHT_LIST_EXTRA_SPEC" "$(print -l -- $collected_files)"
preflight_lines=$(grep -c 'preflight.spec.ts:' "$list_output")
[[ "$preflight_lines" -ge 1 ]] || fail "PLAYWRIGHT_LIST_PREFLIGHT" "$preflight_lines"
print -- "LIVE_WINDOW collection ok: 1 target case ($case_id) + $preflight_lines preflight test(s)"

if (( skip_run )); then
  print -- "LIVE_WINDOW $window_id collected only (--skip-run)"
  print -- "LIVE_WINDOW window_root=$window_root"
  exit 0
fi

# The service starts here and nowhere else: the launcher re-validates every frozen identity, writes
# the child receipt, and execs the installed console entry.
set +u
source /opt/ros2_jazzy/install/setup.zsh
source /opt/ros2_jazzy/extra_ws/install/setup.zsh
source /opt/data/so101/runtime/fork/current/setup.zsh
source /opt/data/so101/workspace/install/setup.zsh
set -u

spawn_intent="$window_root/service-spawn-intent.json"
"$REGISTERED_PYTHON" - "$spawn_intent" "$launch_document" "$case_id" <<'PY'
import json, os, sys
intent_path, launch_path, case_id = sys.argv[1:4]
json.dump({
    "schema_version": 1,
    "case_id": case_id,
    "role": "unified_web_service",
    "launch_document": launch_path,
    "owner_pid": os.getpid(),
    "window_root": os.path.dirname(intent_path),
}, open(intent_path, "w", encoding="utf-8"), indent=2, sort_keys=True)
PY

service_stdout="$window_root/service.stdout.log"
service_stderr="$window_root/service.stderr.log"
child_receipt="$window_root/service-child-receipt.json"
"$REGISTERED_PYTHON" "$worktree/scripts/so101_macos_unified_service.py" \
  --launch-document "$launch_document" --receipt "$child_receipt" \
  > "$service_stdout" 2> "$service_stderr" &
service_pid=$!
started_rc=$?

service_birth="$("$REGISTERED_PYTHON" - "$service_pid" <<'PY'
import sys
from so101_teleop.process_identity import read_identity
print(read_identity(int(sys.argv[1])).start_marker)
PY
)"
service_executable="$(ps -o comm= -p "$service_pid" 2>/dev/null || print)"
print -- "LIVE_WINDOW service pid=$service_pid birth=$service_birth"

ready=0
for _ in {1..120}; do
  if curl -fsS "$SERVICE_URL/health" > "$window_root/health.json" 2>/dev/null; then
    ready=1
    break
  fi
  if ! kill -0 "$service_pid" 2>/dev/null; then
    break
  fi
  sleep 0.5
done
if [[ "$ready" -ne 1 ]]; then
  print -ru2 -- "LIVE_WINDOW service did not become ready; child receipt:"
  cat "$child_receipt" 2>/dev/null || print -ru2 -- "(no child receipt)"
  tail -5 "$service_stderr" >&2 || true
  cleanup_rc=1
else
  ( cd "$web_root" && "${playwright_argv[@]}" ) > "$window_root/playwright.log" 2>&1
  cleanup_rc=$?
fi

# Identity recheck, then the bounded stop of *only* the process this window recorded.
identity_ok=0
current_birth="$("$REGISTERED_PYTHON" - "$service_pid" <<'PY' 2>/dev/null || print ""
import sys
from so101_teleop.process_identity import read_identity
print(read_identity(int(sys.argv[1])).start_marker)
PY
)"
[[ -n "$current_birth" && "$current_birth" == "$service_birth" ]] && identity_ok=1
if [[ "$identity_ok" -eq 1 ]]; then
  kill -INT "$service_pid" 2>/dev/null || true
  for _ in {1..40}; do
    kill -0 "$service_pid" 2>/dev/null || break
    sleep 0.25
  done
  if kill -0 "$service_pid" 2>/dev/null; then
    kill -TERM "$service_pid" 2>/dev/null || true
    sleep 2
  fi
  if kill -0 "$service_pid" 2>/dev/null; then
    kill -KILL "$service_pid" 2>/dev/null || true
  fi
fi
wait "$service_pid" 2>/dev/null
stop_rc=$?

residue="$window_root/residue.txt"
{
  print -r -- "# processes this window owned that are still alive"
  if [[ "$identity_ok" -eq 1 ]] && kill -0 "$service_pid" 2>/dev/null; then
    print -r -- "service pid=$service_pid birth=$service_birth STILL ALIVE"
  fi
  print -r -- "# port 8013 listeners"
  /usr/sbin/lsof -nP -iTCP:$PORT -sTCP:LISTEN 2>/dev/null || print -r -- "(none)"
  print -r -- "# task-owned stack processes"
  ps -axo pid=,command= | grep -E 'ros2_control_node|move_group|so101_unified_web_server' \
    | grep -v grep || print -r -- "(none)"
} > "$residue"

receipt="$window_root/service-window-receipt.json"
"$REGISTERED_PYTHON" - "$receipt" "$window_root" "$case_id" "$service_pid" "$service_birth" \
  "$service_executable" "$started_rc" "$stop_rc" "$identity_ok" "$child_receipt" "$residue" <<'PY'
import hashlib, json, sys
from pathlib import Path
receipt_path, window_root, case_id, pid, birth, executable, start_rc, stop_rc, identity_ok, \
    child_receipt, residue = sys.argv[1:12]
window = Path(window_root)
def digest(name):
    path = window / name
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
document = {
    "schema_version": 1,
    "case_id": case_id,
    "service": {
        "pid": int(pid),
        "birth_identity": int(birth) if birth else None,
        "executable": executable,
        "identity_recheck_ok": bool(int(identity_ok)),
        "start_rc": int(start_rc),
        "stop_rc": int(stop_rc),
    },
    "sha256": {
        "launch_document": digest("service-launch.json"),
        "spawn_intent": digest("service-spawn-intent.json"),
        "child_receipt": digest("service-child-receipt.json"),
        "health": digest("health.json"),
        "playwright_list": digest("playwright-list.txt"),
        "playwright_log": digest("playwright.log"),
        "residue": digest("residue.txt"),
    },
    "residue": Path(residue).read_text(encoding="utf-8").splitlines(),
}
json.dump(document, open(receipt_path, "w", encoding="utf-8"), indent=2, sort_keys=True)
PY

(cd "$window_root" && shasum -a 256 ./* > SHA256SUMS 2>/dev/null)
print -- "LIVE_WINDOW window=$window_id receipt=$receipt rc=$cleanup_rc"
[[ "$cleanup_rc" -eq 0 ]] || exit 1
exit 0
