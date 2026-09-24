"""Contract tests for the closed macOS live service-window runner (remediation Task 7B).

One window owns one service and one console case. These tests read the runner's own text and drive
its refusal paths; they never start the service, a browser or a simulator.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
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

#: The runner writes its functional manifest with an inline Python program fed to its registered
#: interpreter. The test runs that same program - not a copy of its logic - so the document it
#: asserts on is the one a window really writes.
_MANIFEST_WRITER = re.compile(
    r'"\$REGISTERED_PYTHON" - "\$functional_manifest" "\$case_id" "\$mode" "\$workers" '
    r'"\$points" <<\'PY\'\n(?P<program>.*?)\nPY\n',
    re.DOTALL,
)
_CASE_VALUE = re.compile(r'(\w+)=(?:"([^"]*)"|([^;\s]+))')


def _manifest_writer(runner: str) -> str:
    match = _MANIFEST_WRITER.search(runner)
    assert match is not None, "the runner no longer writes its functional manifest inline"
    return match.group("program")


def _case_parameters(runner: str, case_name: str) -> dict[str, str]:
    """The ``key=value`` assignments of one ``case "$case_name" in`` branch."""

    block = re.search(
        rf"^  {re.escape(case_name)}\)(?P<body>.*?);;$", runner, re.DOTALL | re.MULTILINE
    )
    assert block is not None, case_name
    return {
        key: quoted or bare for key, quoted, bare in _CASE_VALUE.findall(block.group("body"))
    }


def _written_manifest(tmp_path: Path, program: str, parameters: dict[str, str]) -> dict:
    output = tmp_path / "functional-manifest.json"
    completed = subprocess.run(
        [
            sys.executable, "-", str(output), parameters["case_id"], parameters["mode"],
            parameters["workers"], parameters["points"],
        ],
        input=program, text=True, capture_output=True, check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(output.read_text(encoding="utf-8"))


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
    # The service is started through the frozen-identity launcher, never through a shell that would
    # clear the service parameters. The manifest itself is asserted where it is produced, in
    # ``test_the_single_case_manifest_shape_is_the_one_the_specs_read``.
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
    """Run the runner's own manifest writer and read the document it really produces.

    The window writes ``{cases: [...], stability: {...}}`` and the R06 spec reads exactly those
    keys, so the shape has to be asserted on the produced file rather than on a dictionary this test
    built itself: a round trip through ``json.dumps``/``json.loads`` of a literal proves only that
    the standard library works.
    """

    spec = SPRINT_SPEC.read_text(encoding="utf-8")
    assert "type FunctionalManifest = { cases: FunctionalCase[]; stability: FunctionalCase }" in spec

    runner = RUNNER.read_text(encoding="utf-8")
    parameters = _case_parameters(runner, "w2")
    manifest = _written_manifest(tmp_path, _manifest_writer(runner), parameters)

    assert set(manifest) == {"cases", "stability"}
    assert [case["id"] for case in manifest["cases"]] == [parameters["case_id"]]
    # The stability case is the same case, not a second one the spec could traverse instead.
    assert manifest["stability"] == manifest["cases"][0]
    assert manifest["stability"]["id"] == parameters["case_id"]
    assert manifest["cases"][0]["lifecycle"] == "FIRST_PASS"
    assert manifest["cases"][0]["maximum_attempts"] == 1
    assert manifest["cases"][0]["point_count"] == int(parameters["points"])
