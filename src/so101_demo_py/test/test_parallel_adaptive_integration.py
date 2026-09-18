"""Integration contracts for adaptive convergence, output, and supervision."""

import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

PACKAGE = Path(__file__).resolve().parents[1]
POINTS = PACKAGE / "config/mujoco/moveit_expert_validation_points_v1.yaml"
CONFIG = PACKAGE / "config/mujoco/parallel_batch_v2.yaml"
ADAPTIVE_CONFIG = PACKAGE / "config/mujoco/parallel_adaptive_workers_v1.yaml"

import pytest


def test_adaptive_outcome_document_is_stable_and_failure_exit_is_nonzero(tmp_path):
    from so101_demo.cli.mujoco_parallel_batch import adaptive_outcome_document
    from so101_demo.parallel_batch.adaptive_contracts import (
        AdaptiveBatchSummary,
        BatchTerminalStatus,
        CommittedPointResult,
    )
    from so101_demo.parallel_batch.contracts import PointStatus

    summary = AdaptiveBatchSummary(
        BatchTerminalStatus.COMPLETED_WITH_FAILURES,
        8,
        6,
        (8, 6),
        (CommittedPointResult("p1", PointStatus.FAILED, tmp_path / "p1", 2),),
        (),
        True,
    )

    code, document = adaptive_outcome_document(summary, elapsed_s=1.25)

    assert code == 1
    assert document == {
        "schema_version": 1,
        "mode": "adaptive_workers",
        "status": "COMPLETED_WITH_FAILURES",
        "initial_worker_count": 8,
        "final_worker_count": 6,
        "levels_used": [8, 6],
        "fallback_transitions": [],
        "point_statuses": {"p1": "FAILED"},
        "infra_attempts": {"p1": 2},
        "batch_cleanup_complete": True,
        "elapsed_s": 1.25,
    }


def test_run_cli_writes_adaptive_aggregate(monkeypatch, tmp_path, capsys):
    from so101_demo.cli import mujoco_parallel_batch as cli
    from so101_demo.parallel_batch.adaptive_contracts import (
        AdaptiveBatchSummary,
        BatchTerminalStatus,
    )

    root = tmp_path / "adaptive-output"
    runtime_root = root / "r/a001"
    request = SimpleNamespace(evidence_root=root, runtime_root=runtime_root)
    prepared = SimpleNamespace(
        adaptive_request=request,
        request=None,
        manifest={"schema_version": 1, "mode": "adaptive_workers"},
    )
    summary = AdaptiveBatchSummary(
        BatchTerminalStatus.COMPLETED, 8, 8, (8,), (), (), True
    )
    closed = []

    class FakeRunner:
        def __init__(self, supplied_request, pool_factory):
            assert supplied_request is request
            assert pool_factory == "pool-factory"
            runtime_root.mkdir(parents=True, mode=0o700)

        def run(self):
            return summary

        def close(self):
            closed.append(True)

    monkeypatch.setattr(
        cli, "prepare_batch", lambda *_args, **_kwargs: prepared
    )
    monkeypatch.setattr(
        cli,
        "ProductionAdaptivePoolFactory",
        lambda *_args, **_kwargs: "pool-factory",
    )
    monkeypatch.setattr(cli, "AdaptiveBatchRunner", FakeRunner)

    assert cli.run_cli([], composition_factory=object()) == 0
    document = json.loads((runtime_root / "aggregate_results.json").read_text())
    assert document["mode"] == "adaptive_workers"
    assert document["status"] == "COMPLETED"
    assert document["batch_cleanup_complete"] is True
    assert closed == [True]
    assert json.loads(capsys.readouterr().out) == document


def test_run_cli_reports_adaptive_runner_error_and_closes(
    monkeypatch, tmp_path, capsys
):
    from so101_demo.cli import mujoco_parallel_batch as cli
    from so101_demo.parallel_batch.adaptive_runner import AdaptiveRunnerError

    root = tmp_path / "adaptive-error"
    runtime_root = root / "r/a001"
    request = SimpleNamespace(evidence_root=root, runtime_root=runtime_root)
    prepared = SimpleNamespace(
        adaptive_request=request,
        request=None,
        manifest={"schema_version": 1},
    )
    closed = []

    class FailingRunner:
        def __init__(self, *_args, **_kwargs):
            runtime_root.mkdir(parents=True, mode=0o700)

        def run(self):
            raise AdaptiveRunnerError("RUNNER_FAILED")

        def close(self):
            closed.append(True)

    monkeypatch.setattr(
        cli, "prepare_batch", lambda *_args, **_kwargs: prepared
    )
    monkeypatch.setattr(
        cli, "ProductionAdaptivePoolFactory", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(cli, "AdaptiveBatchRunner", FailingRunner)

    assert cli.run_cli([]) == 1
    assert json.loads(capsys.readouterr().err) == {
        "status": "ERROR",
        "message": "RUNNER_FAILED",
    }
    assert closed == [True]


def test_adaptive_wrapper_has_strict_cleanup_trap_contract():
    script = Path(__file__).resolve().parents[3] / "scripts/run_so101_adaptive_batch.zsh"
    document = script.read_text(encoding="utf-8")

    assert document.startswith("#!/usr/bin/env zsh\nset -euo pipefail\n")
    assert "so101_parallel_batch_cleanup" in document
    assert "--runtime-root" in document


def test_adaptive_wrapper_preserves_runner_status_after_successful_cleanup(tmp_path):
    script = Path(__file__).resolve().parents[3] / "scripts/run_so101_adaptive_batch.zsh"
    commands = tmp_path / "commands"
    commands.mkdir()
    runner = commands / "so101_parallel_batch"
    runner.write_text("#!/bin/sh\nexit 17\n", encoding="utf-8")
    runner.chmod(0o700)
    cleanup = commands / "so101_parallel_batch_cleanup"
    cleanup.write_text(
        "#!/bin/sh\nprintf '%s\\n' \"$@\" > \"$CLEANUP_ARGS\"\n",
        encoding="utf-8",
    )
    cleanup.chmod(0o700)
    cleanup_args = tmp_path / "cleanup-args"
    evidence_root = tmp_path / "evidence"
    environment = dict(os.environ)
    environment.update(
        PATH=f"{commands}:{environment['PATH']}",
        CLEANUP_ARGS=str(cleanup_args),
    )

    completed = subprocess.run(
        [
            str(script),
            "--evidence-root",
            str(evidence_root),
            "--batch-id",
            "a01",
        ],
        check=False,
        env=environment,
    )

    assert completed.returncode == 17
    assert cleanup_args.read_text(encoding="utf-8").splitlines() == [
        "--runtime-root",
        str(evidence_root / "r/a01"),
    ]


def test_adaptive_wrapper_emits_exact_runner_handshake(tmp_path):
    import json
    import signal
    import time

    script = Path(__file__).resolve().parents[3] / "scripts/run_so101_adaptive_batch.zsh"
    commands = tmp_path / "commands"
    commands.mkdir()
    runner = commands / "so101_parallel_batch"
    runner.write_text(
        "#!/bin/sh\n"
        "root=\n"
        "batch=\n"
        "while [ $# -gt 0 ]; do\n"
        "  case \"$1\" in\n"
        "    --evidence-root) root=$2; shift 2 ;;\n"
        "    --batch-id) batch=$2; shift 2 ;;\n"
        "    *) shift ;;\n"
        "  esac\n"
        "done\n"
        "mkdir -p \"$root/r/$batch\"\n"
        "trap 'exit 0' INT TERM\n"
        "while :; do sleep 1; done\n",
        encoding="utf-8",
    )
    runner.chmod(0o700)
    cleanup = commands / "so101_parallel_batch_cleanup"
    cleanup.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    cleanup.chmod(0o700)
    evidence_root = tmp_path / "evidence"
    environment = dict(os.environ)
    environment["PATH"] = f"{commands}:{environment['PATH']}"
    process = subprocess.Popen(
        [
            str(script),
            "--adaptive-workers",
            "--evidence-root",
            str(evidence_root),
            "--batch-id",
            "a01",
        ],
        env=environment,
    )
    handshake_path = evidence_root / "r/a01/handshake.json"
    try:
        deadline = time.monotonic() + 5.0
        while not handshake_path.is_file() and time.monotonic() < deadline:
            time.sleep(0.01)
        document = json.loads(handshake_path.read_text(encoding="utf-8"))
        assert document["wrapper_pid"] == process.pid
        assert document["runner_pid"] > 0
        assert document["batch_id"] == "a01"
    finally:
        if "document" in locals():
            os.kill(document["runner_pid"], signal.SIGTERM)
        else:
            process.send_signal(signal.SIGTERM)
        process.wait(timeout=5.0)


def test_scaling_driver_accepts_w16_and_rejects_w17_in_dry_run(tmp_path):
    """The maintained launcher must expose the same optional ceiling as the CLI."""

    script = (
        Path(__file__).resolve().parents[3]
        / "scripts/run_so101_adaptive_worker_scaling.zsh"
    )
    accepted = subprocess.run(
        [
            str(script),
            "--worker-counts",
            "16",
            "--evidence-root",
            str(tmp_path),
            "--dry-run",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    rejected = subprocess.run(
        [
            str(script),
            "--worker-counts",
            "17",
            "--evidence-root",
            str(tmp_path),
            "--dry-run",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert accepted.returncode == 0
    assert "--worker-count 16" in accepted.stdout
    assert rejected.returncode == 2
    assert "unsupported Worker count: 17" in rejected.stderr


def test_external_cleanup_retires_only_owned_worker_and_releases_claim(tmp_path):
    from so101_demo.cli.parallel_batch_cleanup import cleanup_runtime
    from so101_demo.parallel_batch.journal import CoordinatorJournal
    from so101_demo.runtime.parallel_processes import ProcessSupervisor

    # The leaf must stay the batch id (cleanup_runtime validates it), so isolation comes
    # from a per-test parent: the previous fixed path collided with other tests that share
    # one scratch tree when the suite runs in parallel.
    runtime_root = Path(os.environ["TMPDIR"]).parent / f"rt-{tmp_path.name}" / "a001"
    runtime_root.mkdir(parents=True, mode=0o700)
    pool_root = runtime_root / "p/g01w01"
    pool_root.mkdir(parents=True, mode=0o700)
    pool_batch_id = "a001-g01-w01"

    journal = CoordinatorJournal.create(runtime_root / "journal", "a001")
    journal.append("POOL_STARTING", "pool-starting-01", {
        "generation": 1,
        "worker_count": 1,
    })
    journal.close()

    supervisor = ProcessSupervisor(
        pool_batch_id,
        manifest_path=pool_root / "owned-processes.json",
    )
    worker = supervisor.start("worker", ["/usr/bin/sleep", "60"])
    worker_poll = supervisor._owned[worker.pid][1]
    reaped = threading.Event()

    def reap_worker():
        while worker_poll() is None:
            time.sleep(0.005)
        reaped.set()

    threading.Thread(target=reap_worker, daemon=True).start()
    sentinel = subprocess.Popen(["/usr/bin/sleep", "60"], start_new_session=True)
    try:
        claim_root = runtime_root / "claims"
        claim_root.mkdir(mode=0o700)
        claim_path = claim_root / "domain-215.lock"
        claim = {
            "protocol": "uid_flock_v1",
            "scope": "cooperating_same_uid_processes",
            "domain_id": 215,
            "uid": os.getuid(),
            "pid": os.getpid(),
            "process_starttime_ticks": 1,
            "batch_id": pool_batch_id,
            "evidence_root": str(pool_root),
            "claim_path": str(claim_path),
            "claim_state": "ACTIVE",
            "generation": 1,
        }
        claim_path.write_text(json.dumps(claim) + "\n", encoding="utf-8")
        claim_path.chmod(0o600)
        (pool_root / "resource_manifest.json").write_text(
            json.dumps({
                "domain_claims": [claim],
                "workers": [{"ros_domain_id": 215}],
            }),
            encoding="utf-8",
        )
        (pool_root / "resource_manifest.json").chmod(0o600)

        receipt = cleanup_runtime(runtime_root)

        assert reaped.wait(2.0)
        assert not Path(f"/proc/{worker.pid}").exists()
        assert sentinel.poll() is None
        assert receipt["cleanup_complete"] is True
        assert receipt["released_domain_ids"] == [215]
        assert json.loads(
            (pool_root / "owned-processes.json").read_text(encoding="utf-8")
        )["processes"] == []
        assert json.loads(claim_path.read_text(encoding="utf-8"))["claim_state"] == "RELEASED"
        assert cleanup_runtime(runtime_root) == receipt
    finally:
        supervisor.shutdown(
            interrupt_timeout_s=0.1,
            term_timeout_s=0.1,
            kill_timeout_s=0.1,
        )
        sentinel.terminate()
        sentinel.wait(timeout=2.0)


def test_external_cleanup_accepts_w16_and_rejects_w17_pool_identity(tmp_path):
    """Top-level cleanup must recognize every supported pool and fail closed above it."""

    from so101_demo.cli.parallel_batch_cleanup import CleanupError, cleanup_runtime
    from so101_demo.parallel_batch.journal import CoordinatorJournal

    def runtime(worker_count):
        batch_id = f"w{worker_count}"
        root = tmp_path / batch_id
        root.mkdir(mode=0o700)
        journal = CoordinatorJournal.create(root / "journal", batch_id)
        journal.append(
            "POOL_STARTING",
            f"pool-starting-{worker_count}",
            {"generation": 1, "worker_count": worker_count},
        )
        journal.close()
        (root / f"p/g01w{worker_count:02d}").mkdir(parents=True, mode=0o700)
        return root

    receipt = cleanup_runtime(runtime(16))

    assert receipt["worker_count"] == 16
    assert receipt["cleanup_complete"] is True
    with pytest.raises(CleanupError, match="ACTIVE_POOL_IDENTITY"):
        cleanup_runtime(runtime(17))


def test_setup_installs_adaptive_config_and_cleanup_entry_point(monkeypatch):
    import setuptools

    package = Path(__file__).resolve().parents[1]
    captured = {}
    monkeypatch.setattr(setuptools, "setup", lambda **values: captured.update(values))

    runpy.run_path(str(package / "setup.py"), run_name="__task9_setup__")

    installed = {
        source
        for _destination, sources in captured["data_files"]
        for source in sources
    }
    assert "config/mujoco/parallel_adaptive_workers_v1.yaml" in installed
    assert (
        "so101_parallel_batch_cleanup = "
        "so101_demo.cli.parallel_batch_cleanup:main"
    ) in captured["entry_points"]["console_scripts"]


def test_setup_adaptive_wrapper_source_is_relative_and_resolves(monkeypatch):
    import setuptools

    package = Path(__file__).resolve().parents[1]
    captured = {}
    monkeypatch.setattr(setuptools, "setup", lambda **values: captured.update(values))

    runpy.run_path(str(package / "setup.py"), run_name="__task_runtime_setup__")

    wrapper_sources = [
        source
        for destination, sources in captured["data_files"]
        if destination == "lib/so101_demo_py"
        for source in sources
    ]
    assert len(wrapper_sources) == 1
    source = Path(wrapper_sources[0])
    assert not source.is_absolute()
    assert (package / source).resolve() == (
        package.parents[1] / "scripts/run_so101_adaptive_batch.zsh"
    )
    assert (package / source).is_file()


def test_adaptive_help_is_explicit_and_rejects_heavy_admission_flags():
    from so101_demo.cli.mujoco_parallel_batch import build_parser, CliError

    parser = build_parser()
    help_document = parser.format_help()
    expected = {
        "--adaptive-workers",
        "--adaptive-config",
        "--fallback-worker-counts",
        "--initial-points-per-worker",
        "--worker-start-timeout-s",
        "--max-infra-attempts-per-point",
    }
    forbidden = {
        "--admission-mode",
        "--admission-profile",
        "--admission-authority",
        "--cgroup-parent",
        "--qualification",
        "--canary",
    }

    assert all(option in help_document for option in expected)
    assert forbidden.isdisjoint(parser._option_string_actions)
    for option in forbidden:
        with pytest.raises(CliError, match="ARGUMENT_ERROR"):
            parser.parse_args([option])


def test_adaptive_module_imports_exclude_abandoned_heavy_stack():
    command = """
import importlib
import json
import sys

for name in (
    'so101_demo.parallel_batch.adaptive_contracts',
    'so101_demo.parallel_batch.adaptive_queue',
    'so101_demo.parallel_batch.adaptive_runner',
    'so101_demo.parallel_batch.adaptive_pool',
):
    importlib.import_module(name)
forbidden = (
    'so101_demo.parallel_batch.qualification',
    'so101_demo.parallel_batch.resource_monitor',
    'so101_demo.parallel_batch.watchdog',
    'so101_demo.parallel_batch.cgroups',
)
print(json.dumps([name for name in forbidden if name in sys.modules]))
"""
    environment = dict(os.environ)
    environment["PYTHONNOUSERSITE"] = "1"

    completed = subprocess.run(
        [sys.executable, "-c", command],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert json.loads(completed.stdout) == []


def test_adaptive_cli_keeps_its_own_config_route(tmp_path):
    """The adaptive route loads its own contract; fixed v2 is never substituted for it."""

    from so101_demo.cli import mujoco_parallel_batch as cli

    parser = cli.build_parser()
    options = parser.parse_args([
        "--points", str(POINTS), "--config", str(CONFIG), "--batch-id", "b1",
        "--evidence-root", str(tmp_path), "--adaptive-workers",
        "--adaptive-config", str(ADAPTIVE_CONFIG), "--broker-image", "image:tag",
        "--yolo-weights", "/models/yolo.pt", "--yolo-weights-sha256", "a" * 64,
        "--grounded-root", "/models/grounded",
        "--grounded-manifest-sha256", "b" * 64, "--run-mode", "dry_run",
    ])
    worker_options, adaptive_path = cli._adaptive_options(options)
    assert Path(adaptive_path).name == "parallel_adaptive_workers_v1.yaml"
    assert worker_options.worker_count >= 1
    source = Path(cli.__file__).read_text(encoding="utf-8")
    assert "parallel_batch_v2.yaml" in source
    assert "_adaptive_options" in source


def test_cleanup_of_a_pool_that_failed_before_allocating_is_a_no_op(tmp_path):
    """A pool that failed before its directory existed left nothing to clean up.

    This is exactly what the adaptive wrapper hit: the journal records POOL_STARTING, the
    allocation is refused (START_GUARD_UNAVAILABLE), only `p/gNNwMM-failure.json` is written --
    and cleanup then raised POOL_ROOT, so the campaign never reached a terminal state and sat in
    CLEANING_UP with `batch_cleanup_complete: false` forever.  A failure marker without a pool
    directory means nothing was allocated, so cleanup completes without retiring anything, and the
    marker itself stays on disk as evidence.
    """

    from so101_demo.cli.parallel_batch_cleanup import cleanup_runtime
    from so101_demo.parallel_batch.journal import CoordinatorJournal

    runtime_root = Path(os.environ["TMPDIR"]).parent / f"rt-{tmp_path.name}" / "a001"
    runtime_root.mkdir(parents=True, mode=0o700)
    pool_parent = runtime_root / "p"
    pool_parent.mkdir(mode=0o700)
    failure_path = pool_parent / "g01w08-failure.json"
    failure_path.write_text(
        json.dumps(
            {
                "batch_id": "a001-g01-w08",
                "generation": 1,
                "kind": "so101_adaptive_pool_failure",
                "stage": "resource_allocation",
                "pool_running": False,
                "cleanup_complete": False,
                "exception_chain": [
                    {"type": "ResourceAllocationError", "message": "START_GUARD_UNAVAILABLE"}
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    journal = CoordinatorJournal.create(runtime_root / "journal", "a001")
    journal.append("POOL_STARTING", "pool-starting-01", {"generation": 1, "worker_count": 8})
    journal.close()

    receipt = cleanup_runtime(runtime_root)

    assert receipt["cleanup_complete"] is True
    assert receipt["active_generation"] == 1
    assert receipt["worker_count"] == 0
    assert receipt["released_domain_ids"] == []
    assert failure_path.is_file(), "the failure marker is evidence and must survive cleanup"

