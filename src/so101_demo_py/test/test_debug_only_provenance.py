"""Debug-only provenance: a no-Git copied install runs, and the manifest gates nothing.

The runtime tests below execute the ACTUAL default TextAgent CLI bootstrap from a pure
copied install that lives outside any Git repository, with a hermetic agent port, and
prove that missing, malformed or mismatched source-commit metadata cannot refuse it.
The manifest tests cover the DEBUG-only emitter and the explicitly requested reader.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from ament_index_python.packages import get_package_prefix

from so101_demo.runtime.debug_provenance import (
    MANIFEST_RELATIVE_PATH, build_debug_manifest, collect_debug_artifacts,
    read_debug_manifest, write_debug_manifest)

WORKTREE = Path(__file__).resolve().parents[3]
PACKAGE_ROOT = WORKTREE / "src/so101_demo_py"


def _site_packages(prefix: Path) -> Path:
    version = f"python{sys.version_info.major}.{sys.version_info.minor}"
    return prefix / "lib" / version / "site-packages"


def _copied_install(tmp_path: Path) -> Path:
    """A pure copied install outside Git: real installed-layout bytes, no .git above."""

    destination = tmp_path / "deployed-install"
    if destination.exists():
        shutil.rmtree(destination)
    site = _site_packages(destination)
    site.mkdir(parents=True)
    shutil.copytree(PACKAGE_ROOT / "src", site / "so101_demo")
    # No fake entrypoint is written: this module proves MODULE admission only. The real
    # copied console/default-composition acceptance lives in
    # test_copied_installed_entrypoint.py against an immutable copied prefix.
    share = destination / "share/ament_index/resource_index/packages"
    share.mkdir(parents=True)
    (share / "so101_demo_py").write_text("")
    package_share = destination / "share/so101_demo_py"
    package_share.mkdir(parents=True)
    for name in ("config", "assets", "launch"):
        source = PACKAGE_ROOT / name
        if source.is_dir():
            shutil.copytree(source, package_share / name)
    (package_share / "package.xml").write_text(
        (PACKAGE_ROOT / "package.xml").read_text(encoding="utf-8"))
    return destination


_DRIVER = r"""
import json, os, sys
from pathlib import Path

argv = json.loads(sys.argv[1])
from so101_demo.application.text_agent import AgentResult, AgentStatus
from so101_demo.ports.task_planner import PlannerMetadata


class HermeticAgent:
    def handle(self, request):
        return AgentResult(
            request_id=request.request_id, status=AgentStatus.RUNTIME_COMPLETED,
            reason_code=None,
            metadata=PlannerMetadata("hermetic", "hermetic-v1", 1, 1, 1, 0, False),
            command=None, capability="dynamic_cup_pick_place", dispatch=True,
            runtime_session_id="debug-provenance-session",
            state_trace=(AgentStatus.RUNTIME_STARTED, AgentStatus.RUNTIME_COMPLETED),
            confirmation_mode="skipped")


from so101_demo.cli.text_pick_agent import main

code = main(argv, _agent=HermeticAgent())
print(json.dumps({"exit": code}))
raise SystemExit(code)
"""


def _run_cli(prefix: Path, evidence_root: Path, *extra: str, installed_prefix=None):
    evidence_root.mkdir(parents=True, exist_ok=True)
    argv = [
        "--instruction", "Pick the plastic cup.",
        "--request-id", "req-debug",
        "--mode", "execute", "--execute",
        "--session-id", "debug-provenance-session",
        "--expected-reset-epoch", "0",
        "--evidence-root", str(evidence_root),
        "--installed-prefix", str(installed_prefix or prefix),
        *extra,
    ]
    environment = dict(os.environ)
    inherited = environment.get("PYTHONPATH", "")
    environment.update({
        "PYTHONPATH": f"{_site_packages(prefix)}{os.pathsep}{inherited}" if inherited
        else str(_site_packages(prefix)),
        "AMENT_PREFIX_PATH": str(prefix),
        "PYTHONNOUSERSITE": "1",
        "SO101_DISABLE_KIMI_EDITABLE_FINDER": "1",
    })
    environment.pop("SO101_SOURCE_COMMIT", None)
    return subprocess.run(
        [sys.executable, "-c", _DRIVER, json.dumps(argv)],
        capture_output=True, text=True, env=environment, cwd=str(evidence_root))


@pytest.mark.parametrize("extra", [
    (),
    ("--source-commit", "abc123"),
    ("--source-commit", "g" * 40),
    ("--source-commit", "0" * 40),
])
def test_copied_install_outside_git_runs_the_default_cli(tmp_path: Path, extra) -> None:
    """Module admission: any commit value used to refuse a pure copied install.

    This is NOT the copied console/default-composition acceptance - see
    test_copied_installed_entrypoint.py for that.
    """

    prefix = _copied_install(tmp_path)
    assert not (prefix / ".git").exists()
    evidence = tmp_path / "evidence"
    completed = _run_cli(prefix, evidence, *extra)
    assert completed.returncode == 0, completed.stderr[-2000:]
    assert json.loads(completed.stdout.strip().splitlines()[-1])["exit"] == 0
    persisted = list((evidence / "text-agent-provenance").glob("*.json"))
    assert len(persisted) == 1
    document = json.loads(persisted[0].read_text())
    provenance = document["execution_provenance"]
    assert provenance["installed_prefix"] == str(prefix)
    # The copied bytes, not the development overlay, produced this identity.
    assert provenance["module"]["path"].startswith(str(prefix))
    expected_commit = extra[1] if extra else None
    assert provenance["source_commit"] in {None, expected_commit}
    assert provenance["source_commit_source"] in {"OBSERVED", "DECLARED", "UNKNOWN"}
    assert provenance["module"]["sha256"]
    # The entrypoint artifact is absent here by design (no fake stub is fabricated).
    assert provenance.get("entrypoint") is None


def test_copied_install_accepts_arbitrary_prefix_metadata(tmp_path: Path) -> None:
    """Prefix metadata is optional debug data; the functional chain still runs."""

    prefix = _copied_install(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    completed = _run_cli(
        prefix, tmp_path / "evidence", "--source-commit", "0" * 40,
        installed_prefix=elsewhere)
    assert completed.returncode == 0, completed.stderr[-1500:]
    assert json.loads(completed.stdout.strip().splitlines()[-1])["exit"] == 0
    persisted = list((tmp_path / "evidence/text-agent-provenance").glob("*.json"))
    assert persisted
    provenance = json.loads(persisted[0].read_text())["execution_provenance"]
    # The mismatch is not an admission rule: the value is recorded, never enforced.
    assert provenance["installed_prefix"] in {None, str(elsewhere), str(prefix)}


def test_functional_executable_discovery_is_preserved(tmp_path: Path, monkeypatch) -> None:
    """Removing metadata admission must not remove real resource discovery."""

    from so101_demo.runtime.launch_composition import installed_executable

    found = installed_executable("text_pick_agent")
    assert found.is_file()

    import so101_demo.runtime.launch_composition as module

    def unavailable(*_args, **_kwargs):
        raise LookupError("no ament index")

    monkeypatch.setattr(module, "get_package_prefix", unavailable)
    monkeypatch.setattr(module, "get_package_share_directory", unavailable)
    monkeypatch.setattr(module.shutil, "which", lambda _name: None)
    with pytest.raises(RuntimeError, match="installed executable is unavailable"):
        installed_executable("text_pick_agent")


def test_runtime_never_reads_a_debug_manifest(tmp_path: Path) -> None:
    """A missing, corrupt or stale manifest cannot change runtime availability."""

    prefix = _copied_install(tmp_path)
    evidence = tmp_path / "evidence"
    manifest = prefix / MANIFEST_RELATIVE_PATH
    manifest.parent.mkdir(parents=True, exist_ok=True)

    # Missing, corrupt, stale (foreign commit) and unknown-schema manifests all run.
    attempts = [
        ("missing", None),
        ("corrupt", "not json at all"),
        ("stale", json.dumps({
            "schema_version": 1, "kind": "DEBUG_INSTALL_PROVENANCE",
            "source_commit": "f" * 40, "artifacts": []})),
        ("foreign-schema", json.dumps({"schema_version": 99, "kind": "OTHER"})),
    ]
    for label, payload in attempts:
        if payload is None:
            if manifest.exists():
                manifest.unlink()
        else:
            manifest.write_text(payload)
        completed = _run_cli(prefix, evidence / label)
        assert completed.returncode == 0, f"{label}: {completed.stderr[-1500:]}"
        assert json.loads(completed.stdout.strip().splitlines()[-1])["exit"] == 0


def test_debug_manifest_covers_installed_artifacts_and_detects_byte_change(tmp_path: Path) -> None:
    prefix = _copied_install(tmp_path)
    target = write_debug_manifest(prefix, source_root=WORKTREE)
    assert target == prefix / MANIFEST_RELATIVE_PATH
    document = read_debug_manifest(prefix)
    assert document is not None
    assert document["kind"] == "DEBUG_INSTALL_PROVENANCE"
    assert document["authority"] == "DEBUG_ONLY_NOT_RUNTIME_AUTHORITY"
    paths = {item["path"] for item in document["artifacts"]}
    relative_module = _site_packages(Path(".")).relative_to(".").as_posix()
    assert f"{relative_module}/so101_demo/cli/text_pick_agent.py" in paths
    assert "lib/python3.12/site-packages/so101_demo/cli/text_pick_agent.py" in paths
    assert any(path.startswith("share/so101_demo_py/") for path in paths)
    assert MANIFEST_RELATIVE_PATH not in paths
    assert not any("__pycache__" in path or path.endswith(".pyc") for path in paths)
    for item in document["artifacts"]:
        assert not item["path"].startswith("/")
        assert len(item["sha256"]) == 64

    # Deterministic: identical bytes produce identical manifest bytes.
    first = target.read_bytes()
    write_debug_manifest(prefix, source_root=WORKTREE)
    assert target.read_bytes() == first

    # A real installed byte change is reported.
    victim = _site_packages(prefix) / "so101_demo/cli/text_pick_agent.py"
    victim.write_bytes(victim.read_bytes() + b"\n# drifted\n")
    rebuilt = build_debug_manifest(prefix, source_root=WORKTREE)
    victim_path = f"{_site_packages(Path('.'))}/so101_demo/cli/text_pick_agent.py".replace(
        str(Path(".")) + "/", "")
    recorded = {item["path"]: item["sha256"] for item in rebuilt["artifacts"]}
    before = {item["path"]: item["sha256"] for item in document["artifacts"]}
    assert recorded[victim_path] != before[victim_path]


def test_debug_manifest_records_unknown_commit_without_git(tmp_path: Path, monkeypatch) -> None:
    """A build with no Git succeeds and records unknown, never a fabricated commit."""

    prefix = _copied_install(tmp_path)
    source = tmp_path / "no-git-source"
    (source / "src/so101_demo_py").mkdir(parents=True)
    monkeypatch.setenv("SO101_SOURCE_COMMIT", "")
    monkeypatch.delenv("GIT_DIR", raising=False)
    monkeypatch.delenv("GIT_WORK_TREE", raising=False)
    document = build_debug_manifest(prefix, source_root=source)
    assert document["source_commit"] is None
    assert document["source_dirty"] is None
    assert document["authority"] == "DEBUG_ONLY_NOT_RUNTIME_AUTHORITY"


def test_debug_manifest_is_relocatable_and_documents_symlinks(tmp_path: Path) -> None:
    prefix = _copied_install(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text("external\n")
    link = prefix / "share/so101_demo_py/external-link.txt"
    link.symlink_to(outside)
    inside_target = prefix / "share/so101_demo_py/inside.txt"
    inside_target.write_text("inside\n")
    inner_link = prefix / "share/so101_demo_py/inside-link.txt"
    inner_link.symlink_to("inside.txt")

    write_debug_manifest(prefix, source_root=WORKTREE)
    recorded = {item["path"]: item for item in read_debug_manifest(prefix)["artifacts"]}
    assert recorded["share/so101_demo_py/inside-link.txt"]["sha256"] == recorded[
        "share/so101_demo_py/inside.txt"]["sha256"]
    assert recorded["share/so101_demo_py/external-link.txt"]["sha256"] is None
    assert recorded["share/so101_demo_py/external-link.txt"]["symlink_target"] == "EXTERNAL"

    # Relocation: the manifest is install-relative, so moving the prefix keeps it valid.
    moved = tmp_path / "relocated"
    shutil.move(str(prefix), str(moved))
    relocated = read_debug_manifest(moved)
    assert relocated is not None
    assert relocated["artifacts"] == [
        item for item in relocated["artifacts"]
    ]
    assert {item["path"] for item in relocated["artifacts"]} == set(recorded)
    assert not (prefix / MANIFEST_RELATIVE_PATH).exists()


def test_debug_reader_reports_drift_without_gating_runtime(tmp_path: Path) -> None:
    prefix = _copied_install(tmp_path)
    (prefix / "share/so101_demo_py/inside.txt").write_text("inside\n")
    write_debug_manifest(prefix, source_root=WORKTREE)
    from so101_demo.cli.debug_provenance import main as debug_main

    assert debug_main(["--prefix", str(prefix), "--verify"]) == 0
    victim = prefix / "share/so101_demo_py/inside.txt"
    victim.write_text("drifted\n")
    assert debug_main(["--prefix", str(prefix), "--verify"]) == 1
    missing = tmp_path / "no-manifest"
    missing.mkdir()
    assert debug_main(["--prefix", str(missing), "--verify"]) == 0
