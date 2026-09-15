#!/usr/bin/env python3
"""Deterministic file-sharded runner for the ordinary SO-101 pytest gate."""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import statistics
import subprocess
import sys
import time
from typing import Iterable, Sequence
import xml.etree.ElementTree as ET


SERIAL_MODULE_REASONS = {
    "test_parallel_batch_resources.py": (
        "preserves the established first-module ordering for process/resource probes"
    ),
    "test_text_pick_agent_e2e_process.py": (
        "owns real launch child process trees and preserves the established second-module ordering"
    ),
    "test_parallel_adaptive_integration.py": (
        "starts and signals real process groups, including an unowned sentinel"
    ),
}
SERIAL_MODULES = tuple(SERIAL_MODULE_REASONS)
BENCHMARK_COMPONENT = "benchmark_test"


class CoverageError(RuntimeError):
    """The sharded result is not exactly the expected ordinary collection."""


@dataclass(frozen=True)
class ProcessLayout:
    name: str
    root: Path
    tmp_dir: Path
    ros_home: Path
    ros_log_dir: Path
    junit_path: Path
    log_path: Path
    node_manifest_path: Path
    ownership_path: Path
    resource_path: Path
    preflight_path: Path
    environment: dict[str, str]


@dataclass(frozen=True)
class ProcessOutcome:
    name: str
    returncode: int
    timed_out: bool
    provenance_valid: bool
    junit_readable: bool
    elapsed_s: float = 0.0
    max_rss_kib: int | None = None
    user_time_s: float | None = None
    system_time_s: float | None = None
    cpu_percent: float | None = None
    warning_count: int | None = None
    node_ids: tuple[str, ...] = ()
    junit_counts: dict[str, int] | None = None
    command: tuple[str, ...] = ()
    layout_root: str = ""
    error: str | None = None


def validate_worker_count(worker_count: int) -> int:
    if isinstance(worker_count, bool) or worker_count < 1:
        raise ValueError("worker count must be at least 1")
    return worker_count


def exact_executable(path: Path, cwd: Path) -> Path:
    """Make an executable absolute without resolving its user-specified symlink."""
    return path if path.is_absolute() else (cwd / path).absolute()


def preserve_porcelain_status(output: str) -> str:
    """Remove terminal newlines without stripping Git's leading status column."""
    return output.rstrip("\r\n")


def validate_source_status(
    source_status: str,
    allowed_dirty_paths: Sequence[str],
    *,
    allow_dirty: bool,
) -> None:
    if not source_status or allow_dirty:
        return
    allowed = set(allowed_dirty_paths)
    observed = set()
    for line in source_status.splitlines():
        path = line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        observed.add(path)
    unexpected = sorted(observed - allowed)
    if unexpected:
        raise RuntimeError(
            "source worktree has non-audit dirty paths: " + ", ".join(unexpected)
        )


def discover_ordinary_modules(package_root: Path) -> tuple[Path, ...]:
    test_root = package_root / "test"
    if not test_root.is_dir():
        raise FileNotFoundError(f"ordinary test root does not exist: {test_root}")
    modules = tuple(
        sorted(test_root.glob("test_*.py"), key=lambda path: path.as_posix())
    )
    if not modules:
        raise CoverageError("ordinary module discovery must be nonzero")
    if any(BENCHMARK_COMPONENT in path.parts for path in modules):
        raise CoverageError("benchmark module entered ordinary discovery")
    return modules


def split_lanes(modules: Sequence[Path]) -> tuple[tuple[Path, ...], tuple[Path, ...]]:
    by_name = {path.name: path for path in modules}
    missing = [name for name in SERIAL_MODULES if name not in by_name]
    if missing:
        raise CoverageError(f"required serial modules missing: {missing}")
    serial = tuple(by_name[name] for name in SERIAL_MODULES)
    serial_names = set(SERIAL_MODULES)
    parallel = tuple(
        sorted(
            (path for path in modules if path.name not in serial_names),
            key=lambda path: path.as_posix(),
        )
    )
    return serial, parallel


def load_module_durations(
    junit_path: Path | None,
    test_root: Path,
) -> dict[Path, float]:
    if junit_path is None or not junit_path.is_file():
        return {}
    durations: dict[Path, float] = {}
    root = ET.parse(junit_path).getroot()
    for case in root.iter("testcase"):
        classname = case.attrib.get("classname", "")
        module_name = next(
            (part for part in classname.split(".") if part.startswith("test_")),
            None,
        )
        if module_name is None:
            continue
        try:
            duration = float(case.attrib.get("time", "0"))
        except ValueError:
            continue
        if not math.isfinite(duration) or duration < 0:
            continue
        path = test_root / f"{module_name}.py"
        durations[path] = durations.get(path, 0.0) + duration
    return durations


def assign_lpt(
    modules: Sequence[Path],
    worker_count: int,
    durations: dict[Path, float],
) -> tuple[tuple[Path, ...], ...]:
    validate_worker_count(worker_count)
    known = [
        value for value in durations.values() if math.isfinite(value) and value > 0
    ]
    fallback = statistics.median(known) if known else 1.0
    canonical = tuple(sorted(set(modules), key=lambda path: path.as_posix()))
    weighted = sorted(
        canonical,
        key=lambda path: (-durations.get(path, fallback), path.as_posix()),
    )
    shards: list[list[Path]] = [[] for _ in range(worker_count)]
    loads = [0.0] * worker_count
    for path in weighted:
        index = min(range(worker_count), key=lambda item: (loads[item], item))
        shards[index].append(path)
        loads[index] += durations.get(path, fallback)
    return tuple(tuple(shard) for shard in shards)


def validate_exact_coverage(
    expected: Sequence[str],
    collections: Iterable[Sequence[str]],
) -> dict[str, int | str]:
    expected_tuple = tuple(expected)
    actual = tuple(node_id for collection in collections for node_id in collection)
    if not expected_tuple:
        raise CoverageError("expected collection must be nonzero")
    if any(BENCHMARK_COMPONENT in node_id for node_id in (*expected_tuple, *actual)):
        raise CoverageError("benchmark node ID entered the ordinary gate")
    expected_counts = Counter(expected_tuple)
    actual_counts = Counter(actual)
    expected_duplicates = sorted(
        node for node, count in expected_counts.items() if count != 1
    )
    duplicates = sorted(node for node, count in actual_counts.items() if count > 1)
    missing = sorted(set(expected_counts) - set(actual_counts))
    unexpected = sorted(set(actual_counts) - set(expected_counts))
    problems = []
    if expected_duplicates:
        problems.append(
            f"expected manifest contains duplicate node IDs: {expected_duplicates}"
        )
    if duplicates:
        problems.append(f"duplicate node IDs: {duplicates}")
    if missing:
        problems.append(f"missing node IDs: {missing}")
    if unexpected:
        problems.append(f"unexpected node IDs: {unexpected}")
    if problems:
        raise CoverageError("; ".join(problems))
    digest = hashlib.sha256(
        ("\n".join(sorted(expected_tuple)) + "\n").encode()
    ).hexdigest()
    return {
        "expected_count": len(expected_tuple),
        "actual_count": len(actual),
        "collection_sha256": digest,
    }


def validate_process_outcomes(outcomes: Sequence[ProcessOutcome]) -> None:
    failures: list[str] = []
    for outcome in outcomes:
        reasons = []
        if outcome.timed_out:
            reasons.append("timed out")
        if outcome.returncode != 0:
            reasons.append(f"exit={outcome.returncode}")
        if not outcome.provenance_valid:
            reasons.append("invalid provenance")
        if not outcome.junit_readable:
            reasons.append("missing or unreadable JUnit")
        if reasons:
            failures.append(f"{outcome.name}: {', '.join(reasons)}")
    if failures:
        raise RuntimeError("pytest process failed closed: " + "; ".join(failures))


def create_process_layout(run_root: Path, name: str) -> ProcessLayout:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", name):
        raise ValueError(f"invalid process layout name: {name}")
    root = run_root / name
    root.mkdir(mode=0o700, parents=False, exist_ok=False)
    tmp_dir = root / "tmp"
    ros_home = root / "ros-home"
    ros_log_dir = root / "ros-log"
    for directory in (tmp_dir, ros_home, ros_log_dir):
        directory.mkdir(mode=0o700)
    return ProcessLayout(
        name=name,
        root=root,
        tmp_dir=tmp_dir,
        ros_home=ros_home,
        ros_log_dir=ros_log_dir,
        junit_path=root / "junit.xml",
        log_path=root / "pytest.log",
        node_manifest_path=root / "nodeids.json",
        ownership_path=root / "ownership.json",
        resource_path=root / "resource.txt",
        preflight_path=root / "preflight.json",
        environment={
            "TMPDIR": str(tmp_dir),
            "TMP": str(tmp_dir),
            "TEMP": str(tmp_dir),
            "ROS_HOME": str(ros_home),
            "ROS_LOG_DIR": str(ros_log_dir),
        },
    )


def _atomic_json(path: Path, document: object) -> None:
    payload = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode()
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _junit_counts(path: Path) -> tuple[bool, dict[str, int] | None]:
    try:
        root = ET.parse(path).getroot()
    except (FileNotFoundError, ET.ParseError, OSError):
        return False, None
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    if not suites:
        return False, None
    counts = {
        key: sum(int(suite.attrib.get(key, "0")) for suite in suites)
        for key in ("tests", "failures", "errors", "skipped")
    }
    return True, counts


def _resource_metrics(
    path: Path,
) -> tuple[int | None, float | None, float | None, float | None]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None, None, None, None

    def number(label: str, cast):
        match = re.search(
            rf"^{re.escape(label)}:\s*([0-9.]+)%?\s*$", text, re.MULTILINE
        )
        return cast(match.group(1)) if match else None

    return (
        number("Maximum resident set size (kbytes)", int),
        number("User time (seconds)", float),
        number("System time (seconds)", float),
        number("Percent of CPU this job got", float),
    )


def _warning_count(path: Path) -> int | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    matches = re.findall(r"(?:,|^)\s*(\d+) warnings?\b", text)
    return int(matches[-1]) if matches else 0


def _read_manifest(
    path: Path,
    *,
    expected_commit: str,
    expected_python: Path,
    expected_cwd: Path,
) -> tuple[bool, tuple[str, ...], str | None]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        executable = Path(document["python_executable"])
        valid_python = executable.samefile(expected_python)
        package_origin = document.get("so101_demo_origin")
        valid_package = isinstance(package_origin, str) and Path(
            package_origin
        ).resolve().is_relative_to(expected_cwd.resolve())
        valid = (
            document.get("schema_version") == 1
            and document.get("source_commit") == expected_commit
            and Path(document.get("cwd", "")).resolve() == expected_cwd.resolve()
            and valid_python
            and valid_package
            and isinstance(document.get("node_ids"), list)
            and all(isinstance(item, str) for item in document["node_ids"])
        )
        return (
            valid,
            tuple(document.get("node_ids", ())),
            None if valid else "manifest mismatch",
        )
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        return False, (), f"manifest unreadable: {error}"


def _verify_tempfile(
    python: Path, layout: ProcessLayout, environment: dict[str, str]
) -> None:
    completed = subprocess.run(
        [
            str(python),
            "-c",
            "import json,sys,tempfile; print(json.dumps({'python':sys.executable,'tempdir':tempfile.gettempdir()}))",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    document = json.loads(completed.stdout) if completed.returncode == 0 else {}
    valid_python = Path(document.get("python", "/nonexistent")).samefile(python)
    valid_temp = (
        Path(document.get("tempdir", "/nonexistent")).resolve()
        == layout.tmp_dir.resolve()
    )
    _atomic_json(
        layout.preflight_path,
        {
            "command": [str(python), "-c", "import sys,tempfile"],
            "exit_code": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "python_valid": valid_python,
            "tempdir_valid": valid_temp,
        },
    )
    if completed.returncode != 0 or not valid_python or not valid_temp:
        raise RuntimeError(f"{layout.name}: exact-Python tempfile preflight failed")


def _stop_owned_group(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)


def _run_pytest_process(
    *,
    python: Path,
    repo_root: Path,
    layout: ProcessLayout,
    paths: Sequence[Path],
    expected_commit: str,
    timeout_s: float,
    collect_only: bool,
) -> ProcessOutcome:
    environment = dict(os.environ)
    environment.update(layout.environment)
    environment.update(
        PYTHONNOUSERSITE="1",
        PYTHONDONTWRITEBYTECODE="1",
        SO101_PYTEST_NODE_MANIFEST=str(layout.node_manifest_path),
    )
    _verify_tempfile(python, layout, environment)
    pytest_command = [
        str(python),
        "-m",
        "pytest",
        "-p",
        "no:cacheprovider",
        "-p",
        "tools.so101_pytest_manifest",
        "-q",
    ]
    if collect_only:
        pytest_command.append("--collect-only")
    pytest_command.append(f"--junitxml={layout.junit_path}")
    pytest_command.extend(str(path.relative_to(repo_root)) for path in paths)
    command = [
        "/usr/bin/time",
        "-v",
        "-o",
        str(layout.resource_path),
        "--",
        *pytest_command,
    ]
    started = time.monotonic()
    timed_out = False
    error = None
    with layout.log_path.open("xb") as log:
        process = subprocess.Popen(
            command,
            cwd=repo_root,
            env=environment,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        _atomic_json(
            layout.ownership_path,
            {
                "schema_version": 1,
                "state": "RUNNING",
                "owner_pid": os.getpid(),
                "child_pid": process.pid,
                "child_pgid": process.pid,
                "command": command,
                "scratch_root": str(layout.root),
            },
        )
        try:
            returncode = process.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            error = f"timeout after {timeout_s:.3f}s"
            _stop_owned_group(process)
            returncode = (
                process.returncode
                if process.returncode is not None
                else -signal.SIGKILL
            )
    elapsed_s = time.monotonic() - started
    _atomic_json(
        layout.ownership_path,
        {
            "schema_version": 1,
            "state": "EXITED",
            "owner_pid": os.getpid(),
            "child_pid": process.pid,
            "child_pgid": process.pid,
            "command": command,
            "scratch_root": str(layout.root),
            "returncode": returncode,
            "timed_out": timed_out,
            "cleanup_readback": process.poll(),
        },
    )
    provenance_valid, node_ids, manifest_error = _read_manifest(
        layout.node_manifest_path,
        expected_commit=expected_commit,
        expected_python=python,
        expected_cwd=repo_root,
    )
    junit_readable, junit_counts = _junit_counts(layout.junit_path)
    max_rss, user_time, system_time, cpu_percent = _resource_metrics(
        layout.resource_path
    )
    return ProcessOutcome(
        name=layout.name,
        returncode=returncode,
        timed_out=timed_out,
        provenance_valid=provenance_valid,
        junit_readable=junit_readable,
        elapsed_s=elapsed_s,
        max_rss_kib=max_rss,
        user_time_s=user_time,
        system_time_s=system_time,
        cpu_percent=cpu_percent,
        warning_count=_warning_count(layout.log_path),
        node_ids=node_ids,
        junit_counts=junit_counts,
        command=tuple(command),
        layout_root=str(layout.root),
        error=error or manifest_error,
    )


def _git(repo_root: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", *arguments],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _git_status(repo_root: Path) -> str:
    completed = subprocess.run(
        ["git", "status", "--short"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return preserve_porcelain_status(completed.stdout)


def _sha256(path: Path | None) -> str | None:
    if path is None or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _outcome_document(outcome: ProcessOutcome) -> dict[str, object]:
    document = asdict(outcome)
    document.pop("node_ids")
    document["node_count"] = len(outcome.node_ids)
    document["node_manifest"] = str(Path(outcome.layout_root) / "nodeids.json")
    document["command"] = list(outcome.command)
    return document


def run_gate(arguments: argparse.Namespace) -> dict[str, object]:
    overall_started = time.monotonic()
    repo_root = arguments.repo_root.resolve()
    package_root = arguments.package_root.resolve()
    python = exact_executable(arguments.python, Path.cwd())
    if not python.is_file():
        raise FileNotFoundError(f"Python executable does not exist: {python}")
    workers = validate_worker_count(arguments.workers)
    run_root = arguments.evidence_root.resolve() / "scratch" / arguments.run_id
    run_root.mkdir(mode=0o700, parents=True, exist_ok=False)
    summary_path = run_root / "summary.json"
    source_commit = _git(repo_root, "rev-parse", "HEAD")
    if (
        arguments.expected_source_commit
        and source_commit != arguments.expected_source_commit
    ):
        raise RuntimeError(
            f"source commit mismatch: expected {arguments.expected_source_commit}, got {source_commit}"
        )
    source_status = _git_status(repo_root)
    validate_source_status(
        source_status,
        arguments.allow_dirty_path,
        allow_dirty=arguments.allow_dirty,
    )
    modules = discover_ordinary_modules(package_root)
    serial_modules, parallel_modules = split_lanes(modules)
    test_root = package_root / "test"
    timing_input = arguments.timings.resolve() if arguments.timings else None
    durations = load_module_durations(timing_input, test_root)
    assignments = assign_lpt(parallel_modules, workers, durations)
    fallback_values = [value for value in durations.values() if value > 0]
    fallback = statistics.median(fallback_values) if fallback_values else 1.0

    collection_layout = create_process_layout(run_root, "collection")
    collection = _run_pytest_process(
        python=python,
        repo_root=repo_root,
        layout=collection_layout,
        paths=(test_root,),
        expected_commit=source_commit,
        timeout_s=arguments.timeout_s,
        collect_only=True,
    )
    validate_process_outcomes((collection,))
    if not collection.node_ids:
        raise CoverageError("ordinary serial collection must be nonzero")
    if any(BENCHMARK_COMPONENT in node_id for node_id in collection.node_ids):
        raise CoverageError("benchmark node ID entered expected collection")
    setup_elapsed_s = time.monotonic() - overall_started

    serial_layout = create_process_layout(run_root, "serial")
    serial = _run_pytest_process(
        python=python,
        repo_root=repo_root,
        layout=serial_layout,
        paths=serial_modules,
        expected_commit=source_commit,
        timeout_s=arguments.timeout_s,
        collect_only=False,
    )
    validate_process_outcomes((serial,))

    shard_inputs = []
    for index, assignment in enumerate(assignments, start=1):
        if not assignment:
            continue
        shard_inputs.append(
            (
                create_process_layout(run_root, f"shard-{index:02d}"),
                assignment,
            )
        )
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [
            executor.submit(
                _run_pytest_process,
                python=python,
                repo_root=repo_root,
                layout=layout,
                paths=assignment,
                expected_commit=source_commit,
                timeout_s=arguments.timeout_s,
                collect_only=False,
            )
            for layout, assignment in shard_inputs
        ]
        shards = tuple(future.result() for future in futures)
    validate_process_outcomes(shards)
    coverage = validate_exact_coverage(
        collection.node_ids,
        (serial.node_ids, *(shard.node_ids for shard in shards)),
    )
    final_source_status = _git_status(repo_root)
    if final_source_status != source_status:
        raise RuntimeError("source worktree changed during the pytest gate")
    all_execution = (serial, *shards)
    cpu_time_s = sum(
        (outcome.user_time_s or 0.0) + (outcome.system_time_s or 0.0)
        for outcome in all_execution
    )
    total_elapsed_s = time.monotonic() - overall_started
    summary = {
        "schema_version": 1,
        "result": "PASS",
        "source_commit": source_commit,
        "source_status": source_status.splitlines(),
        "source_status_final": final_source_status.splitlines(),
        "allowed_dirty_paths": list(arguments.allow_dirty_path),
        "python_executable": str(python),
        "repo_root": str(repo_root),
        "package_root": str(package_root),
        "install_overlay": os.environ.get("SO101_DEMO_EXPECTED_PREFIX"),
        "ament_prefix_path": os.environ.get("AMENT_PREFIX_PATH"),
        "worker_count": workers,
        "timing_input": str(timing_input) if timing_input else None,
        "timing_input_sha256": _sha256(timing_input),
        "fallback_duration_s": fallback,
        "serial_lane": [
            {
                "module": str(path.relative_to(repo_root)),
                "reason": SERIAL_MODULE_REASONS[path.name],
            }
            for path in serial_modules
        ],
        "shard_assignment": [
            {
                "shard": index,
                "modules": [str(path.relative_to(repo_root)) for path in assignment],
                "estimated_duration_s": sum(
                    durations.get(path, fallback) for path in assignment
                ),
            }
            for index, assignment in enumerate(assignments, start=1)
        ],
        "collection": coverage,
        "expected_node_manifest": str(collection_layout.node_manifest_path),
        "collection_process": _outcome_document(collection),
        "serial_process": _outcome_document(serial),
        "shard_processes": [_outcome_document(outcome) for outcome in shards],
        "setup_elapsed_s": setup_elapsed_s,
        "serial_lane_elapsed_s": serial.elapsed_s,
        "parallel_lane_critical_path_s": max(
            (item.elapsed_s for item in shards), default=0.0
        ),
        "total_elapsed_s": total_elapsed_s,
        "cpu_time_s": cpu_time_s,
        "cpu_utilization_percent": 100.0 * cpu_time_s / total_elapsed_s,
        "maximum_rss_kib": max(
            (
                item.max_rss_kib
                for item in all_execution
                if item.max_rss_kib is not None
            ),
            default=None,
        ),
        "warnings_total": sum(item.warning_count or 0 for item in all_execution),
        "cleanup": {
            "owned_processes_remaining": [],
            "all_children_reaped": True,
        },
    }
    _atomic_json(summary_path, summary)
    return summary


def _parser() -> argparse.ArgumentParser:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--timings", type=Path)
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    parser.add_argument("--timeout-s", type=float, default=900.0)
    parser.add_argument("--expected-source-commit")
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="allow a provenance-recorded diagnostic run from a dirty worktree",
    )
    parser.add_argument(
        "--allow-dirty-path",
        action="append",
        default=[],
        help="allow one exact audit-only dirty path while rejecting all others",
    )
    parser.add_argument("--repo-root", type=Path, default=repo_root)
    parser.add_argument(
        "--package-root",
        type=Path,
        default=repo_root / "src/so101_demo_py",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        summary = run_gate(arguments)
    except Exception as error:
        run_root = arguments.evidence_root.resolve() / "scratch" / arguments.run_id
        summary_path = run_root / "summary.json"
        if run_root.is_dir() and not summary_path.exists():
            _atomic_json(
                summary_path,
                {
                    "schema_version": 1,
                    "result": "FAIL",
                    "worker_count": arguments.workers,
                    "run_root": str(run_root),
                    "error": f"{type(error).__name__}: {error}",
                },
            )
        print(f"SO101_PYTEST_GATE_ERROR: {error}", file=sys.stderr)
        return 1
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
