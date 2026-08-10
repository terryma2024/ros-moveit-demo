from __future__ import annotations

import hashlib
import os
import re
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
GATE_RELATIVE_PATH = Path("src/so101_mujoco_demo_py/scripts/check_migration_isolation.sh")
LEDGER_RELATIVE_PATH = Path("docs/experiments/so101-mujoco-ros2-migration-experiment-ledger.md")
GATE_PATH = REPOSITORY_ROOT / GATE_RELATIVE_PATH
LEDGER_PATH = REPOSITORY_ROOT / LEDGER_RELATIVE_PATH
IMPLEMENTATION_ROOT = Path("src/so101_mujoco_demo_py")
PROVENANCE_RELATIVE_PATH = IMPLEMENTATION_ROOT / "docs/provenance.json"
MAIN_BASE_COMMIT = "d300e7a41fb274d6d7e120699b7040666ea61904"
TASK_BASE_COMMIT = "45c6efc701b133c45875e86b0053cfc37dab7f4f"
BEHAVIOR_SOURCE_COMMIT = "8d7913e7f552a40ee627d65be8b873ac16748bc9"
BACKUP_COMMIT = "3add34f8390b78a1f4a13ff49aefb2dc87638245"
EXPECTED_BRANCH = "codex/so101-mujoco-ros2"
EXPECTED_WORKTREE = "/data/work/ws_moveit/.worktrees/so101-mujoco-ros2"
EXPECTED_EVIDENCE_ROOT = "/tmp/so101-debug-mujoco-migration/"
LEGACY_NAMESPACE = "so101_gazebo_" + "demo_py"
PROTECTED_TREE = Path("src") / ("so101_gazebo_" + "demo_py")
BACKUP_BRANCH = "codex/so101-mujoco-ros2-pre-" + "isolation-20260810"
EMPTY_MANIFEST_SHA256 = hashlib.sha256(b"").hexdigest()


def run(*command: str | Path, cwd: Path = REPOSITORY_ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(part) for part in command],
        cwd=cwd,
        check=False,
        text=True,
        capture_output=True,
    )


def require_success(result: subprocess.CompletedProcess[str]) -> None:
    assert result.returncode == 0, result.stdout + result.stderr


def require_gate_failure(checkout: Path, expected_message: str) -> subprocess.CompletedProcess[str]:
    result = run(checkout / GATE_RELATIVE_PATH, cwd=checkout)
    assert result.returncode != 0, result.stdout + result.stderr
    assert expected_message in result.stderr
    return result


def replace_front_matter_value(document: Path, key: str, value: str) -> None:
    lines = document.read_text().splitlines()
    replacement = f"{key}: {value}"
    for index, line in enumerate(lines):
        if line.startswith(f"{key}:"):
            lines[index] = replacement
            break
    else:
        closing_marker = lines.index("---", 1)
        lines.insert(closing_marker, replacement)
    document.write_text("\n".join(lines) + "\n")


def append_git_exclude(checkout: Path, pattern: str) -> None:
    exclude_file = checkout / ".git/info/exclude"
    with exclude_file.open("a") as stream:
        stream.write(f"\n{pattern}\n")


def protected_nontracked_manifest_sha256(checkout: Path) -> str:
    tracked_result = run("git", "ls-files", "-z", "--", PROTECTED_TREE, cwd=checkout)
    require_success(tracked_result)
    tracked = {entry for entry in tracked_result.stdout.split("\0") if entry}
    records: list[str] = []
    protected_root = checkout / PROTECTED_TREE

    for current_root, directory_names, file_names in os.walk(protected_root, followlinks=False):
        current = Path(current_root)
        symlink_directories = [name for name in directory_names if (current / name).is_symlink()]
        directory_names[:] = [name for name in directory_names if name not in symlink_directories]
        for name in sorted(file_names + symlink_directories):
            candidate = current / name
            relative = candidate.relative_to(checkout).as_posix()
            if relative in tracked:
                continue
            metadata = candidate.lstat()
            mode = stat.S_IMODE(metadata.st_mode)
            if stat.S_ISLNK(metadata.st_mode):
                kind = "L"
                payload = os.readlink(candidate).encode()
            elif stat.S_ISREG(metadata.st_mode):
                kind = "F"
                payload = candidate.read_bytes()
            else:
                raise AssertionError(f"unsupported test fixture entry: {relative}")
            payload_sha256 = hashlib.sha256(payload).hexdigest()
            records.append(f"{kind}\t{mode:04o}\t{payload_sha256}\t{relative}\n")

    return hashlib.sha256("".join(sorted(records)).encode()).hexdigest()


def parse_front_matter(document: Path) -> dict[str, str]:
    lines = document.read_text().splitlines()
    assert lines[0] == "---"
    closing_marker = lines.index("---", 1)
    values: dict[str, str] = {}
    for line in lines[1:closing_marker]:
        match = re.fullmatch(r"([a-z0-9_]+):\s*(.*)", line)
        if match:
            values[match.group(1)] = match.group(2)
    return values


@pytest.fixture
def isolated_checkout(tmp_path: Path) -> Path:
    checkout = tmp_path / "checkout"
    require_success(
        run(
            "git",
            "clone",
            "--quiet",
            "--shared",
            str(REPOSITORY_ROOT),
            str(checkout),
        )
    )

    copied_gate = checkout / GATE_RELATIVE_PATH
    copied_gate.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(GATE_PATH, copied_gate)
    copied_gate.chmod(0o755)

    copied_ledger = checkout / LEDGER_RELATIVE_PATH
    copied_ledger.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(LEDGER_PATH, copied_ledger)
    replace_front_matter_value(
        copied_ledger,
        "protected_nontracked_baseline_sha256",
        EMPTY_MANIFEST_SHA256,
    )
    return checkout


def test_required_isolation_artifacts_exist() -> None:
    missing = [
        str(artifact.relative_to(REPOSITORY_ROOT))
        for artifact in (GATE_PATH, LEDGER_PATH)
        if not artifact.is_file()
    ]
    assert not missing, f"missing required artifacts: {missing}"
    assert os.access(GATE_PATH, os.X_OK)


def test_ledger_records_complete_task_contract_and_checkpoint() -> None:
    front_matter = parse_front_matter(LEDGER_PATH)
    assert front_matter["main_base_commit"] == MAIN_BASE_COMMIT
    assert front_matter["task_base_commit"] == TASK_BASE_COMMIT
    assert front_matter["behavior_source_commit"] == BEHAVIOR_SOURCE_COMMIT
    assert front_matter["rejected_backup_commit"] == BACKUP_COMMIT
    assert front_matter["rejected_backup_branch"] == BACKUP_BRANCH
    assert front_matter["branch"] == EXPECTED_BRANCH
    assert front_matter["worktree"] == EXPECTED_WORKTREE
    assert front_matter["evidence_root"] == EXPECTED_EVIDENCE_ROOT
    assert re.fullmatch(r"EXP-[0-9]{3}", front_matter["next_experiment"])
    assert re.fullmatch(r"[0-9a-f]{64}", front_matter["protected_nontracked_baseline_sha256"])

    physics_contract = front_matter["strict_physics_contract"].lower()
    for required_phrase in (
        "positive path",
        "no weld",
        "no equality",
        "no adhesion",
        "no mocap",
        "no teleport",
        "no direct object qpos",
        "no direct object qvel",
    ):
        assert required_phrase in physics_contract

    pending = front_matter["ledger_commit_pending"]
    task_status = front_matter["task_status"]
    if pending == "true":
        assert task_status == "TASK_1_FIX_IMPLEMENTATION_PENDING_COMMIT"
    else:
        assert pending == "false"
        assert re.fullmatch(r"TASK_[1-9][0-9]*_COMPLETE", task_status)
        verified_commit = front_matter["last_verified_implementation_commit"]
        assert re.fullmatch(r"[0-9a-f]{40}", verified_commit)
        require_success(run("git", "merge-base", "--is-ancestor", verified_commit, "HEAD"))

    ledger_text = LEDGER_PATH.read_text()
    for checkpoint_field in (
        "checkpoint_id: CP-002",
        "last_valid_experiment:",
        "working_tree_status:",
        "owned_processes:",
        "preserved_processes:",
        "confirmed_conclusions:",
        "open_risks:",
        "next_command:",
    ):
        assert checkpoint_field in ledger_text


def test_worktree_contains_the_pinned_task_and_main_bases() -> None:
    for pinned_ancestor in (MAIN_BASE_COMMIT, TASK_BASE_COMMIT):
        result = run("git", "merge-base", "HEAD", pinned_ancestor)
        require_success(result)
        assert result.stdout.strip() == pinned_ancestor


def test_gate_accepts_the_current_isolated_worktree() -> None:
    require_success(run(GATE_PATH))


def test_gate_does_not_require_origin_main(isolated_checkout: Path) -> None:
    require_success(
        run(
            "git",
            "update-ref",
            "-d",
            "refs/remotes/origin/main",
            cwd=isolated_checkout,
        )
    )

    require_success(run(isolated_checkout / GATE_RELATIVE_PATH, cwd=isolated_checkout))


def test_gate_rejects_history_without_the_pinned_task_base(
    isolated_checkout: Path,
) -> None:
    require_success(
        run(
            "git",
            "update-ref",
            "HEAD",
            f"{TASK_BASE_COMMIT}^",
            cwd=isolated_checkout,
        )
    )

    require_gate_failure(isolated_checkout, "pinned task base is not an ancestor")


def test_gate_rejects_the_wrong_branch(isolated_checkout: Path) -> None:
    require_success(
        run("git", "switch", "--quiet", "-c", "test/wrong-branch", cwd=isolated_checkout)
    )

    require_gate_failure(isolated_checkout, "unexpected branch")


def test_gate_rejects_tracked_protected_tree_drift(isolated_checkout: Path) -> None:
    protected_file = isolated_checkout / PROTECTED_TREE / "README.md"
    protected_file.write_text(protected_file.read_text() + "\nprotected drift\n")

    require_gate_failure(isolated_checkout, "protected Gazebo tree differs")


def test_gate_rejects_untracked_protected_tree_status(isolated_checkout: Path) -> None:
    untracked_file = isolated_checkout / PROTECTED_TREE / "unexpected.txt"
    untracked_file.write_text("must be rejected\n")

    require_gate_failure(isolated_checkout, "protected Gazebo tree has worktree changes")


def test_gate_allows_snapshotted_ignored_protected_content_but_rejects_additions(
    isolated_checkout: Path,
) -> None:
    append_git_exclude(isolated_checkout, f"/{PROTECTED_TREE}/generated/")
    existing = isolated_checkout / PROTECTED_TREE / "generated/existing.bin"
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"pre-task baseline\n")
    replace_front_matter_value(
        isolated_checkout / LEDGER_RELATIVE_PATH,
        "protected_nontracked_baseline_sha256",
        protected_nontracked_manifest_sha256(isolated_checkout),
    )
    require_success(run(isolated_checkout / GATE_RELATIVE_PATH, cwd=isolated_checkout))

    (existing.parent / "new.bin").write_bytes(b"post-task generated file\n")
    require_gate_failure(isolated_checkout, "protected nontracked filesystem differs from baseline")


def test_gate_rejects_an_ignored_protected_symlink(isolated_checkout: Path) -> None:
    append_git_exclude(isolated_checkout, f"/{PROTECTED_TREE}/generated-link")
    target = isolated_checkout / "docs/target.txt"
    target.write_text("target\n")
    (isolated_checkout / PROTECTED_TREE / "generated-link").symlink_to(target)

    require_gate_failure(isolated_checkout, "protected nontracked filesystem differs from baseline")


@pytest.mark.parametrize(
    ("relative_path", "contents"),
    [
        (
            Path("package.xml"),
            f"<package><exec_depend>{LEGACY_NAMESPACE}</exec_depend></package>\n",
        ),
        (Path("setup.py"), f"install_requires=[{LEGACY_NAMESPACE!r}]\n"),
        (
            Path("so101_mujoco_demo_py/runtime.py"),
            f"from {LEGACY_NAMESPACE}.runtime import Runtime\n",
        ),
        (
            Path("launch/runtime.launch.py"),
            "from launch_ros.substitutions import FindPackageShare\n"
            f"RESOURCE = FindPackageShare({LEGACY_NAMESPACE!r})\n",
        ),
        (
            Path("so101_mujoco_demo_py/case_variant.py"),
            f"PACKAGE = {LEGACY_NAMESPACE.upper()!r}\n",
        ),
        (
            Path("so101_mujoco_demo_py/dynamic_import.py"),
            "import importlib\n"
            'RUNTIME = importlib.import_module("so101_gazebo_" "demo_py.runtime")\n',
        ),
        (
            Path("launch/dynamic.launch.py"),
            "from launch_ros.substitutions import FindPackageShare\n"
            'PACKAGE = "so101_gazebo_" + "demo_py"\n'
            "RESOURCE = FindPackageShare(PACKAGE)\n",
        ),
    ],
    ids=[
        "package-xml",
        "setup-py",
        "python-import",
        "launch-resource-lookup",
        "case-insensitive",
        "constant-folded-importlib",
        "constant-propagated-launch-resource",
    ],
)
def test_gate_rejects_legacy_runtime_dependencies(
    isolated_checkout: Path, relative_path: Path, contents: str
) -> None:
    dependency_file = isolated_checkout / IMPLEMENTATION_ROOT / relative_path
    dependency_file.parent.mkdir(parents=True, exist_ok=True)
    dependency_file.write_text(contents)

    require_gate_failure(isolated_checkout, "legacy Gazebo Python dependency")


@pytest.mark.parametrize(
    ("relative_path", "ignored"),
    [
        (Path(".hidden-runtime.py"), False),
        (Path("generated/runtime.py"), True),
    ],
    ids=["hidden", "ignored-generated"],
)
def test_gate_scans_hidden_and_ignored_implementation_sources(
    isolated_checkout: Path, relative_path: Path, ignored: bool
) -> None:
    dependency_file = isolated_checkout / IMPLEMENTATION_ROOT / relative_path
    dependency_file.parent.mkdir(parents=True, exist_ok=True)
    dependency_file.write_text(f"PACKAGE = {LEGACY_NAMESPACE!r}\n")
    if ignored:
        append_git_exclude(isolated_checkout, f"/{dependency_file.relative_to(isolated_checkout)}")

    require_gate_failure(isolated_checkout, "legacy Gazebo Python dependency")


def test_gate_scans_symlinked_implementation_source(isolated_checkout: Path) -> None:
    target = isolated_checkout / "docs/symlink-target.py"
    target.write_text(f"PACKAGE = {LEGACY_NAMESPACE!r}\n")
    linked_source = isolated_checkout / IMPLEMENTATION_ROOT / "launch/linked.launch.py"
    linked_source.parent.mkdir(parents=True, exist_ok=True)
    linked_source.symlink_to(target)

    require_gate_failure(isolated_checkout, "legacy Gazebo Python dependency")


def test_gate_fails_closed_when_python_source_cannot_be_parsed(
    isolated_checkout: Path,
) -> None:
    invalid_source = isolated_checkout / IMPLEMENTATION_ROOT / "launch/invalid.launch.py"
    invalid_source.parent.mkdir(parents=True, exist_ok=True)
    invalid_source.write_bytes(b"\xff\xfe\x00")

    require_gate_failure(isolated_checkout, "implementation scan failed")


def write_valid_provenance(checkout: Path) -> Path:
    provenance = checkout / PROVENANCE_RELATIVE_PATH
    provenance.parent.mkdir(parents=True, exist_ok=True)
    provenance.write_text(
        "{\n"
        '  "schema_version": 1,\n'
        '  "behavior_source": {\n'
        f'    "commit": "{BEHAVIOR_SOURCE_COMMIT}",\n'
        f'    "paths": ["src/{LEGACY_NAMESPACE}/runtime.py"]\n'
        "  },\n"
        '  "rejected_backup": {\n'
        f'    "branch": "{BACKUP_BRANCH}",\n'
        f'    "commit": "{BACKUP_COMMIT}"\n'
        "  },\n"
        '  "adaptations": [{\n'
        f'    "source_commit": "{BEHAVIOR_SOURCE_COMMIT}",\n'
        f'    "source_path": "src/{LEGACY_NAMESPACE}/runtime.py",\n'
        '    "destination_path": "src/so101_mujoco_demo_py/runtime.py",\n'
        f'    "source_sha256": "{"0" * 64}",\n'
        '    "adaptation": "Backend-neutral rewrite."\n'
        "  }]\n"
        "}\n"
    )
    return provenance


def test_gate_allows_structured_source_references_only_in_exact_provenance_json(
    isolated_checkout: Path,
) -> None:
    write_valid_provenance(isolated_checkout)

    require_success(run(isolated_checkout / GATE_RELATIVE_PATH, cwd=isolated_checkout))


@pytest.mark.parametrize(
    "mutation",
    ["wrong-field", "nested-provenance", "malformed-json", "undeclared-adaptation-source"],
)
def test_gate_rejects_invalid_provenance_exemptions(isolated_checkout: Path, mutation: str) -> None:
    provenance = write_valid_provenance(isolated_checkout)
    if mutation == "wrong-field":
        provenance.write_text('{"runtime_fallback": "src/' + LEGACY_NAMESPACE + '/runtime.py"}\n')
    elif mutation == "nested-provenance":
        provenance.unlink()
        provenance = provenance.parent / "archive/provenance.json"
        provenance.parent.mkdir()
        provenance.write_text(
            '{"behavior_source": {"paths": ["src/' + LEGACY_NAMESPACE + '/runtime.py"]}}\n'
        )
    elif mutation == "malformed-json":
        provenance.write_text('{"behavior_source": "src/' + LEGACY_NAMESPACE)
    else:
        document = provenance.read_text().replace(
            f'"source_path": "src/{LEGACY_NAMESPACE}/runtime.py"',
            f'"source_path": "src/{LEGACY_NAMESPACE}/undeclared.py"',
        )
        provenance.write_text(document)

    require_gate_failure(isolated_checkout, "provenance")


@pytest.mark.parametrize("backup_reference", [BACKUP_BRANCH, BACKUP_COMMIT])
def test_gate_rejects_backup_branch_and_commit_in_implementation(
    isolated_checkout: Path, backup_reference: str
) -> None:
    leaked_reference = isolated_checkout / IMPLEMENTATION_ROOT / "README.txt"
    leaked_reference.parent.mkdir(parents=True, exist_ok=True)
    leaked_reference.write_text(f"Runtime fallback: {backup_reference}\n")

    require_gate_failure(isolated_checkout, "rejected backup reference")


@pytest.mark.parametrize(
    "evidence_path",
    [Path("build/evidence.txt"), Path("install/evidence.txt"), Path(".superpowers/sdd/log.txt")],
    ids=["build", "install", "sdd"],
)
def test_gate_ignores_backup_references_in_generated_evidence_roots(
    isolated_checkout: Path, evidence_path: Path
) -> None:
    evidence_file = isolated_checkout / evidence_path
    evidence_file.parent.mkdir(parents=True, exist_ok=True)
    evidence_file.write_text(f"review evidence: {BACKUP_BRANCH} {BACKUP_COMMIT}\n")

    require_success(run(isolated_checkout / GATE_RELATIVE_PATH, cwd=isolated_checkout))
