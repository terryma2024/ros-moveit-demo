"""Contract tests for the closed macOS live service-window runner (remediation Task 7B).

One window owns one service and one console case. These tests read the runner's own text and drive
its refusal paths; they never start the service, a browser or a simulator.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
RUNNER = REPOSITORY_ROOT / "scripts" / "so101-macos-service-campaign-live-window.zsh"
REGISTERED_TASK_ROOT = (
    "/tmp/so101-debug-macos-service-campaign-closure-2208b154-6e9f-4ae1-a448-1fa0101df9b1"
)
SPRINT_SPEC = (
    REPOSITORY_ROOT / "src/so101_teleop/web/e2e/expert-validation/live-sim"
    / "06-fixed-n-execution.spec.ts"
)
RETRY_SPEC = (
    REPOSITORY_ROOT / "src/so101_teleop/web/e2e/expert-validation/live-sim"
    / "07-retry-full-restart.spec.ts"
)


def test_the_runner_declares_one_case_per_window_and_a_closed_environment() -> None:
    assert RUNNER.is_file()
    assert RUNNER.stat().st_mode & 0o111
    runner = RUNNER.read_text(encoding="utf-8")

    for token in (
        'case "$case_name" in',
        'w2) case_id="macos-w2-20"; mode="PARALLEL"; workers=2; points=20; project="fixed-n-execution"',
        'w1) case_id="macos-w1-20"; mode="SEQUENTIAL"; workers=1; points=20; project="fixed-n-execution"',
        'retry) case_id="macos-w1-20-retry"; mode="SEQUENTIAL"; workers=1; points=20; project="retry-full-restart"',
        'export SO101_LIVE_SIM_HOST="$(hostname)"',
        'export SO101_LIVE_SERVICE_BASE_URL="$SERVICE_URL"',
        'export SO101_LIVE_SERVICE_STATE_ROOT="$state_root"',
        'export SO101_FUNCTIONAL_MANIFEST="$functional_manifest"',
        'export SO101_FROZEN_SELECTION_MANIFEST="$selection_manifest"',
        'export SO101_LIVE_CASE_ID="$case_id"',
        'export SO101_TASK_ROOT="$task_root"',
        'export SO101_E2E_EVIDENCE_ROOT="$evidence_root"',
        'export SO101_E2E_INSTALL_PREFIX="$install_prefix"',
        'export SO101_E2E_PYTHON="$REGISTERED_PYTHON"',
    ):
        assert token in runner, token
    # "cases" is a single-entry manifest, so the R06 spec cannot traverse another route.
    assert '"cases": [case], "stability": case' in runner
    # The service is started through the frozen-identity launcher, never through a shell that would
    # clear the service parameters.
    assert "scripts/so101_macos_unified_service.py" in runner
    assert "clean_reexec" not in runner


def test_the_runner_refuses_before_it_starts_anything(tmp_path: Path) -> None:
    zsh = shutil.which("zsh")
    if zsh is None:
        pytest.skip("zsh is required for the macOS window runner")

    def run(*arguments: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [zsh, str(RUNNER), *arguments],
            check=False, capture_output=True, text=True,
        )

    assert run("--case", "w9", "--task-root", REGISTERED_TASK_ROOT,
               "--selection-manifest", "/tmp/none.json").returncode == 2
    assert "LIVE_WINDOW_REFUSED CASE_REQUIRED" in run(
        "--case", "w9", "--task-root", REGISTERED_TASK_ROOT).stderr
    refused = run("--case", "w2", "--task-root", str(tmp_path),
                  "--selection-manifest", "/tmp/none.json")
    assert refused.returncode == 2
    assert "TASK_ROOT_NOT_REGISTERED" in refused.stderr
    refused = run("--case", "w2", "--task-root", REGISTERED_TASK_ROOT,
                  "--selection-manifest", "/tmp/none.json")
    assert refused.returncode == 2
    assert "SELECTION_MANIFEST_REQUIRED" in refused.stderr


def test_the_runner_proves_collection_and_stops_only_its_own_process() -> None:
    runner = RUNNER.read_text(encoding="utf-8")

    assert "playwright --list" in runner or '"${playwright_argv[@]}" --list' in runner
    for token in ("PLAYWRIGHT_LIST_NOT_SINGLE_CASE", "PLAYWRIGHT_LIST_PREFLIGHT",
                  "PLAYWRIGHT_LIST_WRONG_CASE", "PLAYWRIGHT_LIST_EXTRA_SPEC", "PORT_IN_USE",
                  "STACK_PRESENT", "identity_recheck_ok", "residue.txt",
                  "service-window-receipt.json"):
        assert token in runner, token
    # The collected file set is closed: only the target spec and its preflight may appear.
    for token in ('target_spec="expert-validation/live-sim/06-fixed-n-execution.spec.ts"',
                  'target_spec="expert-validation/live-sim/07-retry-full-restart.spec.ts"',
                  "collected_files=", "expected_files="):
        assert token in runner, token
    # Only the recorded pid is ever signalled, and only after the birth identity matches.
    assert "kill -INT \"$service_pid\"" in runner
    assert 'if [[ "$identity_ok" -eq 1 ]]' in runner
    assert "killall" not in runner and "pkill" not in runner
    # Evidence is never removed.
    assert "rm -rf" not in runner and "rm -f" not in runner


def test_the_live_specs_require_a_closed_single_case_id() -> None:
    first_pass = SPRINT_SPEC.read_text(encoding="utf-8")
    assert "export function selectLiveCase(" in first_pass
    assert "LIVE_CASE_ID_REQUIRED" in first_pass
    assert "LIVE_CASE_ID_NOT_UNIQUE" in first_pass
    assert "process.env.SO101_LIVE_CASE_ID" in first_pass
    assert re.search(r"selectLiveCase\(\s*loadManifest\(\)\.cases", first_pass)

    retry = RETRY_SPEC.read_text(encoding="utf-8")
    assert "assertRetryWindowCase();" in retry
    assert "LIVE_CASE_ID_REQUIRED" in retry
    assert "LIVE_CASE_ID_NOT_A_RETRY_CASE" in retry
    assert "process.env.SO101_LIVE_CASE_ID" in retry


def test_the_single_case_manifest_shape_is_the_one_the_specs_read(tmp_path: Path) -> None:
    """The runner writes `{cases: [...], stability: {...}}`; the spec reads exactly those keys."""

    spec = SPRINT_SPEC.read_text(encoding="utf-8")
    assert "type FunctionalManifest = { cases: FunctionalCase[]; stability: FunctionalCase }" in spec
    runner = RUNNER.read_text(encoding="utf-8")
    assert '"lifecycle": "FIRST_PASS"' in runner
    assert '"maximum_attempts": 1' in runner
    manifest = {"cases": [{"id": "macos-w2-20"}], "stability": {"id": "macos-w2-20"}}
    assert json.loads(json.dumps(manifest))["cases"][0]["id"] == "macos-w2-20"
