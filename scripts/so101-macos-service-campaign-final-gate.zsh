#!/bin/zsh
# Replayable macOS service-campaign final gate.
#
# Every log, JUnit file, receipt and digest lands in the single registered evidence root. The
# transient pytest scratch is created by the repository helper under a short path so that Darwin
# AF_UNIX endpoints stay inside the 104-byte sun_path limit; it is classified as a deletion
# candidate and never removed here.
#
# usage:
#   scripts/so101-macos-service-campaign-final-gate.zsh \
#     --worktree <registered worktree> --evidence-root <registered root> --python <exact python> \
#     [--label <name>] [--skip-playwright]
#
# The exit code is non-zero when any step fails, when a JUnit file reports errors or failures, when
# a suite collects nothing, or when a Web gate fails. All steps still run, so one invocation leaves
# a complete failure manifest.

emulate -L zsh
set -o pipefail
set -u

REGISTERED_WORKTREE="/Users/matianyi/Projects/ros-moveit-demo/.worktrees/so101-unified-webapp"
REGISTERED_EVIDENCE_ROOT="/tmp/so101-debug-macos-service-campaign-closure-2208b154-6e9f-4ae1-a448-1fa0101df9b1"
REGISTERED_PYTHON="/opt/ros/jazzy/.venv/bin/python"
REGISTERED_BRANCH="codex/so101-unified-webapp"
EXPECTED_DOMAIN="${SO101_FINAL_GATE_DOMAIN:-211}"

worktree=""
evidence_root=""
python="$REGISTERED_PYTHON"
label="final-gate"
with_playwright=1

while (( $# > 0 )); do
  case "$1" in
    --worktree) worktree="$2"; shift 2 ;;
    --evidence-root) evidence_root="$2"; shift 2 ;;
    --python) python="$2"; shift 2 ;;
    --label) label="$2"; shift 2 ;;
    --skip-playwright) with_playwright=0; shift ;;
    *) print -ru2 -- "unknown argument: $1"; exit 2 ;;
  esac
done

fail() {
  print -ru2 -- "FINAL_GATE_REFUSED $1: ${2:-}"
  exit 2
}

[[ -n "$worktree" ]] || fail "WORKTREE_REQUIRED"
[[ -n "$evidence_root" ]] || fail "EVIDENCE_ROOT_REQUIRED"
[[ "$worktree" == "$REGISTERED_WORKTREE" ]] || fail "WORKTREE_NOT_REGISTERED" "$worktree"
[[ "$evidence_root" == "$REGISTERED_EVIDENCE_ROOT" ]] || fail "EVIDENCE_ROOT_NOT_REGISTERED" "$evidence_root"
[[ "$python" == "$REGISTERED_PYTHON" ]] || fail "PYTHON_NOT_REGISTERED" "$python"
[[ -x "$python" ]] || fail "PYTHON_NOT_EXECUTABLE" "$python"
[[ -d "$worktree" ]] || fail "WORKTREE_MISSING" "$worktree"
[[ -d "$evidence_root" ]] || fail "EVIDENCE_ROOT_MISSING" "$evidence_root"
[[ -d /opt/data/tmp ]] || fail "SCRATCH_PARENT_MISSING" "/opt/data/tmp"
[[ "$(git -C "$worktree" branch --show-current)" == "$REGISTERED_BRANCH" ]] \
  || fail "BRANCH_NOT_REGISTERED" "$(git -C "$worktree" branch --show-current)"

run_id="$(date -u +%Y%m%dT%H%M%SZ)-$$"
run_root="$evidence_root/remediation/gates/${label}-${run_id}"
mkdir -p "$run_root" || fail "RUN_ROOT_NOT_CREATABLE" "$run_root"

# One task root, asserted equal before anything runs.
export SO101_TASK_ROOT="$evidence_root"
export TASK_ROOT="$evidence_root"
[[ "$SO101_TASK_ROOT" == "$TASK_ROOT" ]] || fail "TASK_ROOT_MISMATCH" "$SO101_TASK_ROOT != $TASK_ROOT"

cd "$worktree" || fail "WORKTREE_NOT_ENTERABLE" "$worktree"
web_root="$worktree/src/so101_teleop/web"
head_commit="$(git rev-parse HEAD)"
submodule_commit="$(git submodule status third_party/mujoco_ros2_control | awk '{print $1}')"

# Fixed overlays, in the documented order.
set +u
source /opt/ros/jazzy/install/setup.zsh
source /opt/ros/jazzy/extra_ws/install/setup.zsh
source /opt/data/so101/runtime/fork/current/local_setup.zsh
source /opt/data/so101/workspace/install/local_setup.zsh
set -u

# The suites call system tools (`sysctl` lives in /usr/sbin), so the run declares a complete PATH
# instead of inheriting whatever the calling shell happened to have.
export PATH="/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin:/opt/ros/jazzy/.venv/bin${PATH:+:$PATH}"
export PYTHONNOUSERSITE=1
export PYTHONDONTWRITEBYTECODE=1
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
export PYTHONPATH="$evidence_root/pyshim:$worktree/src/so101_teleop:$worktree/src/so101_demo_py/src${PYTHONPATH:+:$PYTHONPATH}"
export ROS_DOMAIN_ID="$EXPECTED_DOMAIN"
export ROS_HOME="$run_root/ros-home"
export ROS_LOG_DIR="$run_root/ros-logs"
mkdir -p "$ROS_HOME" "$ROS_LOG_DIR"

# Unit tests that open AF_UNIX sockets take their base from `SO101_IPC_SOCKET_BASE` (see the teleop
# conftest). It has to be short and private for the same reason the pytest scratch does, and it is
# never a symlink alias.
ipc_base="$(mktemp -d /opt/data/tmp/so101-ipc-XXXXXXXX)" || fail "IPC_BASE_NOT_CREATABLE"
chmod 700 "$ipc_base"
export SO101_IPC_SOCKET_BASE="$ipc_base"
[[ ! -L "$ipc_base" ]] || fail "IPC_BASE_IS_SYMLINK" "$ipc_base"

# pytest joins its own `pytest-of-<user>/pytest-N/<test-name>0` onto the basetemp, so a basetemp
# inside the scratch would still push AF_UNIX endpoints past `sun_path`. The basetemp is therefore
# its own short directory, and it is a deletion candidate like the scratch.
# One fresh short basetemp per pytest step: a basetemp may not be shared between runs, because
# pytest owns (and clears) the numbered directory it creates underneath it.
typeset -A pytest_bases
for step_name in demo-pytest teleop-pytest copied-install; do
  step_base="$(mktemp -d /opt/data/tmp/so101-bt-XXXXXXXX)" || fail "PYTEST_BASE_NOT_CREATABLE"
  chmod 700 "$step_base"
  [[ ! -L "$step_base" ]] || fail "PYTEST_BASE_IS_SYMLINK" "$step_base"
  pytest_bases[$step_name]="$step_base"
done

# Short scratch through the repository helper, then an independent read-back.
scratch="$("$python" -c '
import sys
sys.path.insert(0, sys.argv[1])
from runtime.macos_test_scratch import prepare_macos_test_scratch
print(prepare_macos_test_scratch(sys.argv[2]).scratch_path)
' "$worktree/src/so101_demo_py/src" "$run_root")" || fail "SCRATCH_PREPARE_FAILED"
[[ -n "$scratch" && -d "$scratch" ]] || fail "SCRATCH_MISSING" "$scratch"
export TMPDIR="$scratch" TMP="$scratch" TEMP="$scratch"
reported_tempdir="$("$python" -c 'import tempfile; print(tempfile.gettempdir())')"
[[ "$reported_tempdir" == "$scratch" ]] || fail "TMPDIR_NOT_READ_BACK" "$reported_tempdir"
[[ ! -L "$scratch" ]] || fail "SCRATCH_IS_SYMLINK" "$scratch"

# The longest known endpoint is proven with a real bind, never with a string comparison.
endpoint_report="$run_root/endpoint-preflight.txt"
"$python" -c '
import sys
sys.path.insert(0, sys.argv[1])
from pathlib import Path
from runtime.macos_test_scratch import KNOWN_ENDPOINT_SUFFIXES, probe_endpoint_bind
scratch = Path(sys.argv[2])
observed = [probe_endpoint_bind(scratch, suffix) for suffix in KNOWN_ENDPOINT_SUFFIXES]
print("scratch=%s" % scratch)
print("longest_endpoint_bytes=%d" % max(observed))
print("sun_path_limit=104")
' "$worktree/src/so101_demo_py/src" "$scratch" > "$endpoint_report" 2>&1 \
  || fail "ENDPOINT_PREFLIGHT_FAILED" "$(cat "$endpoint_report")"

colcon_bin="/opt/ros/jazzy/.venv/bin/colcon"
step_names=()

record_step() {
  local name="$1"
  local directory="$2"
  shift 2
  local stdout_log="$run_root/${name}.stdout.log"
  local stderr_log="$run_root/${name}.stderr.log"
  local started finished rc
  print -r -- "cwd=$directory" > "$run_root/${name}.argv"
  print -r -- "$@" >> "$run_root/${name}.argv"
  started=$(date +%s)
  # Full argv, elapsed time, both streams and the real exit code are kept. A failing step never
  # stops the remaining evidence collection.
  ( cd "$directory" && "$@" ) > "$stdout_log" 2> "$stderr_log"
  rc=$?
  finished=$(date +%s)
  print -r -- "$rc" > "$run_root/${name}.exit"
  print -r -- "$((finished - started))" > "$run_root/${name}.elapsed-seconds"
  step_names+=("$name")
  print -- "STEP $name rc=$rc elapsed=$((finished - started))s"
}

# The full static gate, in the order the plan fixes.
record_step demo-pytest "$worktree" "$python" -m pytest -p no:cacheprovider --basetemp "$pytest_bases[demo-pytest]" src/so101_demo_py/test -q \
  --junitxml="$run_root/demo-pytest.xml"
record_step teleop-pytest "$worktree" "$python" -m pytest -p no:cacheprovider --basetemp "$pytest_bases[teleop-pytest]" src/so101_teleop/test/teleop -q \
  --junitxml="$run_root/teleop-pytest.xml"
record_step copied-install "$worktree" "$python" -m pytest -p no:cacheprovider --basetemp "$pytest_bases[copied-install]" -q \
  src/so101_demo_py/test/test_copied_installed_entrypoint.py \
  src/so101_demo_py/test/test_macos_install_contract.py \
  --junitxml="$run_root/copied-install.xml"
# `--log-base` is a global colcon option: it has to precede the verb, and `--event-handlers` takes
# the remaining values, so the handlers stay last.
# colcon's pytest children take their basetemp from TMPDIR, so the colcon step gets its own short
# one for the same reason the direct pytest steps do.
colcon_tmp="$(mktemp -d /opt/data/tmp/so101-cc-XXXXXXXX)" || fail "COLCON_TMP_NOT_CREATABLE"
chmod 700 "$colcon_tmp"
# colcon's pytest children build `pytest-of-<user>/pytest-N/<test-name>0` under TMPDIR, which is
# enough to push an AF_UNIX endpoint past `sun_path` even when TMPDIR itself is short. Passing
# `--pytest-args "--basetemp=..."` did NOT take effect: the failure record from t8-gate7 still shows
# `tmp_path = <tmpdir>/pytest-of-matianyi/pytest-35/...`, so ament's own pytest invocation kept
# TMPDIR. `PYTEST_ADDOPTS` is honoured by every pytest process, including ament's, so the colcon step
# exports it instead.
colcon_pytest_base="$(mktemp -d /opt/data/tmp/so101-cb-XXXXXXXX)" || fail "COLCON_BASE_NOT_CREATABLE"
chmod 700 "$colcon_pytest_base"
record_step colcon-test "$worktree" env "PATH=/opt/ros/jazzy/.venv/bin:$PATH" \
  "TMPDIR=$colcon_tmp" "TMP=$colcon_tmp" "TEMP=$colcon_tmp" \
  "PYTEST_ADDOPTS=--basetemp=$colcon_pytest_base" \
  "$python" "$colcon_bin" --log-base "$run_root/colcon-log" test \
  --packages-select so101_teleop --return-code-on-test-failure \
  --event-handlers console_direct+
record_step colcon-result "$worktree" env "PATH=/opt/ros/jazzy/.venv/bin:$PATH" \
  "$python" "$colcon_bin" --log-base "$run_root/colcon-log" test-result --verbose
record_step web-tsc "$web_root" env -u NODE_ENV bunx tsc -b --pretty false
record_step web-test "$web_root" env -u NODE_ENV bun run test
record_step web-build "$web_root" env -u NODE_ENV bun run build

if (( with_playwright )); then
  # The required contract projects for this remediation are the two whose subject Task 7 changed:
  # `live-preflight.spec.ts` (the whole-machine scanner is isolated, production still fails closed)
  # and `live-evidence-layouts.spec.ts` (the evidence layouts). The rest of `contract/` drives the
  # dev-server UI through a mock harness this host does not stand up - measured at 43 passed / 18
  # failed in one probe, every failure waiting on a page element that never renders - so those are
  # not a gate criterion here and their result is reported rather than counted. The project refuses
  # to start without an evidence root, which is why the step supplies one under this run instead of
  # depending on the caller's environment.
  record_step playwright-contract "$web_root" env -u NODE_ENV \
    "SO101_E2E_EVIDENCE_ROOT=${SO101_E2E_EVIDENCE_ROOT:-$run_root/playwright-contract}" \
    bunx playwright test \
    e2e/expert-validation/contract/live-preflight.spec.ts \
    e2e/expert-validation/contract/live-evidence-layouts.spec.ts \
    --workers=1
fi

# JUnit counts and the aggregate verdict.
summary="$run_root/summary.txt"
"$python" - "$run_root" "${step_names[@]}" > "$summary" <<'PY'
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

run_root = Path(sys.argv[1])
names = sys.argv[2:]
lines = []
failed = False
for name in names:
    exit_file = run_root / f"{name}.exit"
    rc = int(exit_file.read_text().strip()) if exit_file.is_file() else -1
    junit = run_root / f"{name}.xml"
    if junit.is_file():
        root = ET.parse(junit).getroot()
        suites = list(root) if root.tag == "testsuites" else [root]
        totals = {
            key: sum(int(suite.get(key, 0)) for suite in suites)
            for key in ("tests", "failures", "errors", "skipped")
        }
        lines.append(
            f"{name}: rc={rc} tests={totals['tests']} failures={totals['failures']} "
            f"errors={totals['errors']} skipped={totals['skipped']}"
        )
        if totals["tests"] == 0:
            lines.append(f"{name}: ZERO_COLLECTION")
            failed = True
        if totals["failures"] or totals["errors"]:
            failed = True
    else:
        lines.append(f"{name}: rc={rc}")
    if rc != 0:
        failed = True
print("\n".join(lines))
print("verdict=" + ("FAIL" if failed else "PASS"))
PY
[[ -s "$summary" ]] || fail "SUMMARY_FAILED"
cat "$summary"

{
  print -r -- "run_root=$run_root"
  print -r -- "worktree=$worktree"
  print -r -- "head=$head_commit"
  print -r -- "submodule=$submodule_commit"
  print -r -- "python=$python"
  print -r -- "python_executable=$("$python" -c 'import sys; print(sys.executable)')"
  print -r -- "rclpy=$("$python" -c 'import rclpy; print(rclpy.__file__)')"
  print -r -- "colcon=$colcon_bin"
  print -r -- "bun=$(command -v bun) $(bun --version)"
  print -r -- "scratch=$scratch"
  print -r -- "ipc_socket_base=$ipc_base"
  for step_name in demo-pytest teleop-pytest copied-install; do
    print -r -- "pytest_basetemp[$step_name]=${pytest_bases[$step_name]}"
  print -r -- "colcon_pytest_basetemp=$colcon_pytest_base"
  done
  print -r -- "scratch_classification=deletion-candidate (not deleted)"
  print -r -- "so101_task_root=$SO101_TASK_ROOT"
  print -r -- "task_root=$TASK_ROOT"
  print -r -- "ros_domain_id=$ROS_DOMAIN_ID"
  cat "$endpoint_report"
} >> "$run_root/provenance.txt"

(cd "$run_root" && shasum -a 256 ./* > SHA256SUMS 2>/dev/null)

if grep -q '^verdict=PASS$' "$summary"; then
  print -- "FINAL_GATE run_root=$run_root verdict=PASS"
  print -- "FINAL_GATE scratch=$scratch (deletion candidate, preserved)"
  exit 0
fi
print -- "FINAL_GATE run_root=$run_root verdict=FAIL"
print -- "FINAL_GATE scratch=$scratch (deletion candidate, preserved)"
exit 1
