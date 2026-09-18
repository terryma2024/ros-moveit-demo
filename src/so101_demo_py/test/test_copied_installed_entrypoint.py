"""Final copied-install acceptance through the REAL installed console entrypoint.

These tests exist because an earlier "copied install" case wrote a fake
``#!/bin/sh exit 1`` entrypoint and injected a hermetic agent, which only proved module
admission. Here the real console script of an immutable copied prefix is executed as a
subprocess with the copied module origins, and the assertions cover:

* the default bootstrap/composition actually running from the copied bytes and stopping
  only at the documented provider gate (an unauthorized live LLM call);
* fail-closed behaviour for invalid execution context;
* functional discovery of the installed executable, launch files, config and assets.

No agent, admission factory, provider, resolver, default factory or global gate is
injected or mocked; the only hermetic inputs are the environment of a copied prefix.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

TASK_ROOT = Path(
    "/data/work/so101-evidence/teleop-expert-validation-serve/20260917-merged-main"
    "/unbounded-queue-resource-budget")
#: The copied install under test. Task 9 of the lightweight start guard plan replaced the
#: hardcoded historical prefix with an explicit one: the new immutable copy of the current
#: runtime is named by SO101_E2E_INSTALL_PREFIX, and the old path stays only as the
#: historical default for this file's pre-guard assertions.
COPIED_PREFIX = Path(
    os.environ.get("SO101_E2E_INSTALL_PREFIX", str(TASK_ROOT / "freeze-install")))
DEMO_PREFIX = COPIED_PREFIX / "so101_demo_py"
ENTRYPOINT = DEMO_PREFIX / "lib/so101_demo_py/text_pick_agent"
WORKTREE = Path(__file__).resolve().parents[3]
RUNTIME_MODULES = (
    "runtime/provenance.py",
    "runtime/debug_provenance.py",
    "runtime/launch_composition.py",
    "cli/text_pick_agent.py",
)


def _current_runtime_files() -> tuple[str, ...]:
    """Every runtime file the copy is expected to carry, repository-relative and sorted."""

    roots = ("src/so101_demo_py/src", "src/so101_teleop/so101_teleop")
    files: list[str] = []
    for root in roots:
        for path in sorted((WORKTREE / root).rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            files.append(str(path.relative_to(WORKTREE)))
    # setup.py is build metadata: colcon installs its own generated copy, so it is not a
    # byte-for-byte runtime artifact. The entry points, modules, launch/config/assets and the
    # generated OpenAPI document are.
    files.append("src/so101_teleop/so101_teleop/expert_validation_openapi.json")
    return tuple(sorted(files))


def _copied_runtime_path(relative: str) -> Path:
    """Map a repository-relative runtime path into the copied install under test."""

    text = str(relative)
    if text.startswith("src/so101_demo_py/src/"):
        return (DEMO_PREFIX / "lib/python3.12/site-packages/so101_demo"
                / text[len("src/so101_demo_py/src/"):])
    if text.startswith("src/so101_teleop/so101_teleop/"):
        return (COPIED_PREFIX / "so101_teleop/lib/python3.12/site-packages/so101_teleop"
                / text[len("src/so101_teleop/so101_teleop/"):])
    if text.startswith("src/so101_demo_py/"):
        return DEMO_PREFIX / text[len("src/so101_demo_py/"):]
    if text == "src/so101_demo_py/setup.py":
        return DEMO_PREFIX / "setup.py"
    raise AssertionError(f"unmapped runtime path: {relative}")


def _copied_environment(scratch: Path, **extra: str) -> dict[str, str]:
    environment = dict(os.environ)
    site = COPIED_PREFIX / "so101_demo_py/lib/python3.12/site-packages"
    teleop_site = COPIED_PREFIX / "so101_teleop/lib/python3.12/site-packages"
    inherited = environment.get("PYTHONPATH", "")
    environment.update({
        "PYTHONPATH": os.pathsep.join(
            [str(site), str(teleop_site), inherited] if inherited else [str(site), str(teleop_site)]),
        "AMENT_PREFIX_PATH": os.pathsep.join([
            str(DEMO_PREFIX),
            str(COPIED_PREFIX / "so101_teleop"),
            str(COPIED_PREFIX / "so101_mujoco_support"),
        ]),
        "SO101_DISABLE_KIMI_EDITABLE_FINDER": "1",
        "PYTHONNOUSERSITE": "1",
        "TMPDIR": str(scratch), "TMP": str(scratch), "TEMP": str(scratch),
    })
    environment.update(extra)
    return environment


def _run_entrypoint(tmp_path: Path, *extra: str, timeout: float = 60.0, **env):
    scratch = tmp_path / "tmp"
    scratch.mkdir(parents=True, exist_ok=True)
    evidence = tmp_path / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    arguments = [
        str(ENTRYPOINT),
        "--instruction", "Pick the plastic cup.",
        "--mode", "execute", "--execute", "--skip-confirmation",
        "--backend", "mujoco",
        "--session-id", "copied-cli-session",
        "--expected-reset-epoch", "0",
        "--evidence-root", str(evidence),
        "--installed-prefix", str(DEMO_PREFIX),
        "--request-id", "copied-cli-request",
        *extra,
    ]
    completed = subprocess.run(
        [sys.executable, *arguments], capture_output=True, text=True,
        env=_copied_environment(scratch, **env), cwd=str(tmp_path), timeout=timeout)
    documents = []
    for line in completed.stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                documents.append(json.loads(line))
            except ValueError:
                continue
    return completed, documents, evidence


def test_runtime_bytes_of_the_copied_prefix_match_the_frozen_source() -> None:
    """Reuse of an immutable prefix is only valid while its bytes still match."""

    assert ENTRYPOINT.is_file()
    assert not ENTRYPOINT.is_symlink()
    if os.environ.get("SO101_E2E_INSTALL_PREFIX"):
        # An explicitly named copy is checked against the tree it was built from: every
        # current runtime file must match byte for byte, and a retired module must be gone.
        mismatched = []
        for relative in _current_runtime_files():
            source = WORKTREE / relative
            copied = _copied_runtime_path(relative)
            if not copied.is_file() or source.read_bytes() != copied.read_bytes():
                mismatched.append(relative)
        assert mismatched == [], (
            f"copied runtime bytes differ from the tree: {len(mismatched)} file(s): "
            f"{mismatched[:12]}")
        for retired in ("parallel_batch/resource_budget.py",
                        "parallel_batch/resource_measurement.py",
                        "parallel_batch/measurement_control.py",
                        "parallel_batch/owned_resources.py"):
            assert not _copied_runtime_path(
                f"src/so101_demo_py/src/{retired}").exists(), retired
    else:
        head = subprocess.run(
            ["git", "-C", str(WORKTREE), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True).stdout.strip()
        changed = subprocess.run(
            ["git", "-C", str(WORKTREE), "diff", "--name-only", "6e68d0f51", head, "--",
             "src/so101_demo_py/src", "src/so101_teleop/so101_teleop", "src/so101_demo_py/setup.py"],
            capture_output=True, text=True, check=True).stdout.split()
        assert changed == [], f"runtime code changed since the copied install: {changed}"
    for relative in RUNTIME_MODULES:
        source = WORKTREE / "src/so101_demo_py/src" / relative
        installed = DEMO_PREFIX / "lib/python3.12/site-packages/so101_demo" / relative
        assert hashlib.sha256(source.read_bytes()).hexdigest() == hashlib.sha256(
            installed.read_bytes()).hexdigest(), relative


def test_the_installed_entrypoint_is_a_real_console_script() -> None:
    """Guard against a stub entrypoint standing in for the installed console script."""

    payload = ENTRYPOINT.read_bytes()
    assert payload.startswith(b"#!")
    assert b"EASY-INSTALL-ENTRY-SCRIPT" in payload
    assert b"exit 1" not in payload
    assert ENTRYPOINT.stat().st_mode & 0o111
    manifest = json.loads((
        DEMO_PREFIX / "share/so101_demo_py/debug-provenance-manifest.json").read_text())
    recorded = {
        item["path"]: item["sha256"] for item in manifest["artifacts"]}
    assert recorded["lib/so101_demo_py/text_pick_agent"] == hashlib.sha256(
        payload).hexdigest()


def test_copied_entrypoint_default_bootstrap_stops_only_at_the_provider_gate(tmp_path) -> None:
    """The real entrypoint runs the copied composition and hits the live-provider gate."""

    completed, documents, evidence = _run_entrypoint(tmp_path)
    assert documents, completed.stderr[-2000:]
    document = documents[-1]
    assert document["status"] == "PLANNER_FAILED"
    assert document["reason_code"] == "PLANNER_CHAIN_FAILED"
    assert completed.returncode == 1
    provenance = document["execution_provenance"]
    assert provenance["module"]["path"].startswith(str(DEMO_PREFIX))
    assert provenance["entrypoint"]["path"] == str(ENTRYPOINT)
    assert provenance["entrypoint"]["sha256"] == hashlib.sha256(
        ENTRYPOINT.read_bytes()).hexdigest()
    # Debug metadata: no runtime Git and no prefix admission, recorded as observations.
    assert provenance["source_commit"] is None
    assert provenance["source_commit_source"] == "UNKNOWN"
    persisted = list((evidence / "text-agent-provenance").glob("*.json"))
    assert len(persisted) == 1
    assert json.loads(persisted[0].read_text())["execution_provenance"] == provenance
    # The remaining step is the unauthorized live provider/ROS boundary, not metadata.
    assert "provider" not in document


@pytest.mark.parametrize(
    ("arguments", "expected_code"),
    [
        (("--session-id", ""), "EXECUTION_SESSION_ID_REQUIRED"),
        (("--expected-reset-epoch", "-1"), "EXECUTION_RESET_EPOCH_INVALID"),
        (("--evidence-root", "relative-evidence"), "EXECUTION_EVIDENCE_ROOT_INVALID"),
        (("--evidence-root", "/proc/self/definitely-missing"), "EXECUTION_EVIDENCE_ROOT_INVALID"),
    ],
)
def test_copied_entrypoint_fails_closed_on_invalid_context(
    tmp_path, arguments, expected_code
) -> None:
    """Independent session/reset/evidence gates keep refusing through the real entry."""

    completed, documents, evidence = _run_entrypoint(tmp_path, *arguments)
    assert completed.returncode == 1
    assert documents and documents[-1]["reason_code"] == expected_code, documents
    assert not (evidence / "text-agent-provenance").exists()


def test_copied_launch_resources_are_functionally_discovered(tmp_path) -> None:
    """Real installed executable, launch files, config and assets resolve from the copy."""

    scratch = tmp_path / "tmp"
    scratch.mkdir(parents=True, exist_ok=True)
    program = (
        "import json,sys;"
        "from pathlib import Path;"
        "from so101_demo.runtime.launch_composition import installed_executable;"
        "from ament_index_python.packages import get_package_share_directory;"
        "exe=installed_executable('text_pick_agent');"
        "share=Path(get_package_share_directory('so101_demo_py'));"
        "print(json.dumps({'exe':str(exe),'executable':exe.stat().st_mode & 0o111 != 0,"
        "'share':str(share),'launch':sorted(p.name for p in (share/'launch').glob('*.launch.py')),"
        "'policy':(share/'config/policies/light_cup_wall_pick/v1/mujoco.yaml').is_file(),"
        "'scene':(share/'assets/mujoco/scene.xml').is_file(),"
        "'module':__import__('so101_demo').__file__}))"
    )
    completed = subprocess.run(
        [sys.executable, "-c", program], capture_output=True, text=True,
        env=_copied_environment(scratch), cwd=str(tmp_path), timeout=60.0)
    assert completed.returncode == 0, completed.stderr[-1500:]
    document = json.loads(completed.stdout.strip().splitlines()[-1])
    assert document["exe"] == str(ENTRYPOINT)
    assert document["executable"] is True
    assert document["module"].startswith(str(DEMO_PREFIX))
    assert document["policy"] is True and document["scene"] is True
    assert "so101_mujoco_text_pick_agent.launch.py" in document["launch"]

    # A genuinely unavailable resource still fails closed, even with metadata present.
    missing = tmp_path / "empty-prefix"
    missing.mkdir()
    environment = _copied_environment(scratch)
    environment["AMENT_PREFIX_PATH"] = str(missing)
    environment["PATH"] = str(missing)
    environment["PYTHONPATH"] = environment["PYTHONPATH"]
    failed = subprocess.run(
        [sys.executable, "-c",
         "from so101_demo.runtime.launch_composition import installed_executable;"
         "installed_executable('text_pick_agent')"],
        capture_output=True, text=True, env=environment, cwd=str(tmp_path), timeout=60.0)
    assert failed.returncode != 0
    assert "installed executable is unavailable" in failed.stderr
