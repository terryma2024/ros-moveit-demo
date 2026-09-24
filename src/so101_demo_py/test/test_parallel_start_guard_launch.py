"""The real installed parallel entry, its guard, and the product negative gates.

Task 8 of the lightweight start guard plan. This file deliberately does **not** substitute the
TextAgent copied-entry case for the parallel guard: it discovers the installed console script
through the functional lookup, runs the real allocator entry as a subprocess against the active
v3 config, and reads back the composition it wrote. The TextAgent launch resource is verified
separately with `ros2 launch ... --show-args`, which proves discovery only, not physical success.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

TASK_ROOT = Path(
    "/data/work/so101-evidence/teleop-expert-validation-serve/20260917-merged-main"
    "/unbounded-queue-resource-budget")
WORKTREE = Path(__file__).resolve().parents[3]
V3_CONFIG = WORKTREE / "src/so101_demo_py/config/mujoco/parallel_batch_v3.yaml"
V2_CONFIG = WORKTREE / "src/so101_demo_py/config/mujoco/parallel_batch_v2.yaml"


def _installed_prefix() -> Path:
    """The demo package prefix: an explicit copy (base/so101_demo_py) or the active overlay."""

    explicit = os.environ.get("SO101_E2E_INSTALL_PREFIX")
    if explicit:
        base = Path(explicit).resolve()
        return (base / "so101_demo_py").resolve() if (base / "so101_demo_py").is_dir() else base
    from ament_index_python.packages import get_package_prefix

    return Path(get_package_prefix("so101_demo_py")).resolve()


def _copy_base() -> Path | None:
    """The copied install base when one was named explicitly, else None (overlay mode)."""

    explicit = os.environ.get("SO101_E2E_INSTALL_PREFIX")
    if not explicit:
        return None
    base = Path(explicit).resolve()
    return base if (base / "so101_demo_py").is_dir() else base.parent


def _v3_config(tmp_path: Path, workers: int) -> Path:
    """Copy the packaged v3 config without changing its frozen domain list."""

    target = tmp_path / f"parallel_v3_w{workers}.yaml"
    shutil.copyfile(V3_CONFIG, target)
    return target


def _isolated_allocator_argv(tmp_path: Path) -> list[str]:
    """Call the installed allocator composition with test-owned domain claims."""

    script = (
        "import sys; from pathlib import Path; "
        "from so101_demo.parallel_batch.resources import main; "
        "raise SystemExit(main(sys.argv[2:], claim_root=Path(sys.argv[1])))"
    )
    return [sys.executable, "-c", script, str(tmp_path / "domain-claims")]


def _entry_environment(prefix: Path, task_root: Path | None = None) -> dict[str, str]:
    """The runtime environment of the entry: install prefix plus the shared guard root.

    ``SO101_TASK_ROOT`` is the design's own requirement (the guard's lock and cleanup state
    live in one task-owned directory shared by CLI and Web), so it is part of the runtime
    environment rather than a metadata gate.
    """

    environment = dict(os.environ)
    environment.update({
        "SO101_E2E_INSTALL_PREFIX": str(prefix),
        "PYTHONNOUSERSITE": "1",
        "SO101_DISABLE_KIMI_EDITABLE_FINDER": "1",
    })
    if os.environ.get("SO101_E2E_INSTALL_PREFIX"):
        # An explicit copied prefix must supply the modules too, not just the console script.
        base = _copy_base() or prefix
        sites = [base / "so101_demo_py/lib/python3.12/site-packages",
                 base / "so101_teleop/lib/python3.12/site-packages"]
        inherited = environment.get("PYTHONPATH", "")
        environment["PYTHONPATH"] = os.pathsep.join(
            [str(site) for site in sites] + ([inherited] if inherited else []))
        prefixes = [base / "so101_demo_py", base / "so101_teleop",
                    base / "so101_mujoco_support"]
        existing = environment.get("AMENT_PREFIX_PATH", "")
        environment["AMENT_PREFIX_PATH"] = os.pathsep.join(
            [str(item) for item in prefixes] + ([existing] if existing else []))
    if task_root is not None:
        environment["SO101_TASK_ROOT"] = str(task_root)
        environment["ROS_HOME"] = str(task_root / "ros-home")
        environment["ROS_LOG_DIR"] = str(task_root / "ros-home/log")
    else:
        environment.pop("SO101_TASK_ROOT", None)
    return environment


def test_installed_parallel_entry_is_functionally_discovered() -> None:
    """Discovery is functional (ament/share/PATH); a missing entry is a normal error."""

    from so101_demo.runtime.launch_composition import installed_executable

    located = installed_executable("so101_parallel_batch")
    assert located.is_file() and os.access(located, os.X_OK), located
    assert located.name == "so101_parallel_batch"
    assert located.parent.name == "so101_demo_py"

    with pytest.raises(Exception) as excinfo:
        installed_executable("so101_entry_that_does_not_exist")
    assert "so101_entry_that_does_not_exist" in str(excinfo.value)


def test_real_parallel_entry_requires_real_control_inputs(tmp_path) -> None:
    """The installed entry runs current code and refuses a missing control input."""

    prefix = _installed_prefix()
    entry = prefix / "lib/so101_demo_py/so101_parallel_batch"
    completed = subprocess.run(
        [sys.executable, str(entry),
         "--config", str(V3_CONFIG), "--points", str(tmp_path / "missing-points.yaml"),
         "--batch-id", "lg-t8-controls", "--worker-count", "1", "--run-mode", "dry_run",
         "--evidence-root", str(tmp_path / "batch"), "--yolo-weights", str(tmp_path / "best.pt"),
         "--yolo-weights-sha256", "0" * 64, "--grounded-root", str(tmp_path),
         "--grounded-manifest-sha256", "0" * 64,
         "--broker-image", "so101-parallel-perception:test"],
        capture_output=True, text=True, timeout=120, cwd=str(tmp_path),
        env=_entry_environment(prefix, tmp_path / "task-root"))
    output = completed.stdout + completed.stderr
    assert completed.returncode != 0, output
    assert "missing-points.yaml" in output or "POINTS" in output.upper(), output
    # A prefix/commit lookup must never be what refuses a real control input.
    assert "git" not in output.lower(), output


def test_the_shared_guard_state_root_is_required_not_guessed(tmp_path) -> None:
    """Without the task root the entry fails closed instead of inventing a lock location."""

    prefix = _installed_prefix()
    config = _v3_config(tmp_path, 1)
    completed = subprocess.run(
        [sys.executable, "-m", "so101_demo.parallel_batch.resources",
         "--config", str(config), "--worker-count", "1",
         "--evidence-root", str(tmp_path / "no-root"), "--dry-run"],
        capture_output=True, text=True, timeout=180, cwd=str(tmp_path),
        env=_entry_environment(prefix))
    assert completed.returncode != 0
    assert "PROBE_STATE_ROOT_UNSET" in completed.stdout + completed.stderr


def test_allocator_default_entry_writes_the_v3_guard_composition(tmp_path) -> None:
    """The real default entry runs the guard and records it, without starting ROS."""

    prefix = _installed_prefix()
    evidence = tmp_path / "guard-batch"
    config = _v3_config(tmp_path, 2)
    completed = subprocess.run(
        [*_isolated_allocator_argv(tmp_path),
         "--config", str(config), "--worker-count", "2",
         "--evidence-root", str(evidence), "--dry-run"],
        capture_output=True, text=True, timeout=180, cwd=str(tmp_path),
        env=_entry_environment(prefix, tmp_path / "task-root"))
    if sys.platform == "darwin":
        assert completed.returncode == 2, completed.stdout + completed.stderr
        failure = json.loads(completed.stderr.strip().splitlines()[-1])
        assert failure["error"] == "GPU_TARGET_UNAVAILABLE"
        assert failure["admission"]["reason"] == "GPU_TARGET_UNAVAILABLE"
        return
    assert completed.returncode == 0, completed.stdout + completed.stderr
    manifest = json.loads(completed.stdout.strip().splitlines()[-1])
    assert manifest["schema_version"] == 3
    assert manifest["worker_count"] == 2
    admission = manifest["admission"]
    assert admission["status"] in ("PASS", "WARN")
    assert admission["cleanup_state"] == "CLEAR"
    assert set(admission["checks"]) == {"cpu_capacity", "cpu_busy", "ram", "gpu"}
    assert admission["checks"]["ram"]["unit"] == "bytes"
    assert manifest["start_guard"]["status"] == admission["status"]
    for retired in ("required_live_headroom_ratio", "profile_sha256", "qualification_sha256",
                    "failures", "observed", "required"):
        assert retired not in admission, retired
    written = json.loads((evidence / "resource_manifest.json").read_text())
    assert written["schema_version"] == 3
    assert written["admission"]["status"] in ("PASS", "WARN")


def test_debug_metadata_cannot_block_but_control_errors_still_refuse(tmp_path) -> None:
    """Missing debug provenance is not an admission gate; real control errors still are."""

    prefix = _installed_prefix()
    config = _v3_config(tmp_path, 1)

    debug_hostile = _entry_environment(prefix, tmp_path / "task-root")
    debug_hostile.update({
        "SO101_PARALLEL_DEBUG_MANIFEST": str(tmp_path / "missing-manifest.json"),
        "SO101_SOURCE_COMMIT": "not-a-commit",
        "SO101_VALIDATION_BUDGET_PROFILE": str(tmp_path / "retired-profile.json"),
        "SO101_VALIDATION_EXECUTION_IDENTITY": "0" * 64,
    })
    accepted = subprocess.run(
        [*_isolated_allocator_argv(tmp_path),
         "--config", str(config), "--worker-count", "1",
         "--evidence-root", str(tmp_path / "debug-hostile"), "--dry-run"],
        capture_output=True, text=True, timeout=180, cwd=str(tmp_path), env=debug_hostile)
    if sys.platform == "darwin":
        assert accepted.returncode == 2, accepted.stdout + accepted.stderr
        failure = json.loads(accepted.stderr.strip().splitlines()[-1])
        assert failure["error"] == "GPU_TARGET_UNAVAILABLE"
        assert "manifest" not in failure["error"].lower()
        assert "commit" not in failure["error"].lower()
        return
    assert accepted.returncode == 0, accepted.stdout + accepted.stderr
    assert json.loads(accepted.stdout.strip().splitlines()[-1])["schema_version"] == 3

    # A real control error: the evidence root already belongs to another batch.
    existing = tmp_path / "already-there"
    existing.mkdir()
    (existing / "resource_manifest.json").write_text("{}")
    refused = subprocess.run(
        [*_isolated_allocator_argv(tmp_path),
         "--config", str(config), "--worker-count", "1",
         "--evidence-root", str(existing), "--dry-run"],
        capture_output=True, text=True, timeout=180, cwd=str(tmp_path),
        env=_entry_environment(prefix, tmp_path / "task-root"))
    assert refused.returncode == 2, refused.stdout + refused.stderr
    failure = json.loads(refused.stderr.strip().splitlines()[-1])
    assert failure["admitted"] is False
    assert failure["error"].startswith("DIRECTORY_CONFLICT")


def test_retired_measurement_entry_reports_retirement(tmp_path) -> None:
    """The old console script still exists but measures nothing."""

    prefix = _installed_prefix()
    entry = prefix / "lib/so101_demo_py/so101_measure_parallel_resources"
    completed = subprocess.run([sys.executable, str(entry)], capture_output=True, text=True,
                               timeout=60, env=_entry_environment(prefix, tmp_path))
    combined = completed.stdout + completed.stderr
    assert completed.returncode == 2, combined
    lines = completed.stdout.strip().splitlines()
    assert lines, f"the retired entry printed nothing on stdout: {combined!r}"
    payload = json.loads(lines[-1])
    assert payload["error"] == "MEASUREMENT_ENTRY_RETIRED"
    assert payload["authorizes_execution"] is False


def test_installed_text_agent_launch_resource_is_discoverable(tmp_path) -> None:
    """The installed launch resource is found by the standard ROS lookup (not physical proof)."""

    prefix = _installed_prefix()
    completed = subprocess.run(
        ["ros2", "launch", "so101_demo_py", "so101_mujoco_text_pick_agent.launch.py",
         "--show-args"],
        capture_output=True, text=True, timeout=180, cwd=str(tmp_path),
        env=_entry_environment(prefix, tmp_path / "task-root"))
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "instruction" in completed.stdout
    assert (prefix / "share/so101_demo_py/launch"
            / "so101_mujoco_text_pick_agent.launch.py").exists()
