"""R1/R2: the default measurement entry carries real authority, sampling and sealing.

The tests here never inject a fake sealer, a fake controller or a synthetic
observation: they run the installed CLI, its default runner factory, the real
`MeasurementSession` (owned cgroup + sampler thread + abort latch + deadline +
verified cleanup) and the real `seal_measurement`. Only the low-level host ports
(cgroup files, NVML device, hardware facts) and the owned workload itself are
hermetic, exactly as the review allows.
"""

import hashlib
import json
import os
import stat
import time
from pathlib import Path

import pytest

from so101_demo.cli.measure_parallel_resources import main
from so101_demo.parallel_batch.contracts import ContractError
from so101_demo.parallel_batch.measurement_control import ProcessIdentity
from so101_demo.parallel_batch.owned_resources import MeasurementSession, OwnedCgroupV2
from so101_demo.parallel_batch.resource_budget import HostFacts, LiveObservationSource
from so101_demo.parallel_batch.resource_measurement import (
    MeasurementAuthorization, build_candidate_plan, run_candidate_batch)

PACKAGE = Path(__file__).resolve().parents[1]
WORKTREE = Path(__file__).resolve().parents[3]
V2_CONFIG = PACKAGE / "config/mujoco/parallel_batch_v2.yaml"
DIMENSIONS = ("ram_bytes", "gpu_bytes", "cpu_core_equivalent")
INSTALLED_PATTERN = "so101_demo_py/lib/python3.12/site-packages/so101_demo/parallel_batch"


def _write(path: Path, data: bytes) -> str:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_bytes(data)
    path.chmod(0o600)
    return hashlib.sha256(data).hexdigest()


def _identity() -> ProcessIdentity:
    fields = Path(f"/proc/{os.getpid()}/stat").read_text().rsplit(")", 1)[1].split()
    return ProcessIdentity(os.getpid(), int(fields[19]), os.getuid(), os.getpgrp())


# --- hermetic low-level ports --------------------------------------------------------

class HermeticCgroup(OwnedCgroupV2):
    """A cgroup stand-in with kernel-like live-PID semantics and readable counters."""

    def __init__(self, *, path: Path) -> None:
        super().__init__(path=path)
        self._attached: set[int] = set()
        self.throttle_count = 0
        self.memory_events_document = {"oom": 0, "oom_kill": 0, "high": 0, "max": 0}
        self.charged_bytes = 200 * 1024 * 1024

    @classmethod
    def create(cls, *, parent: Path, name: str) -> "HermeticCgroup":
        node = Path(parent) / name
        node.mkdir(mode=0o700, parents=True)
        (node / "cgroup.controllers").write_text("cpu memory\n")
        (node / "cgroup.procs").write_text("")
        (node / "cpu.stat").write_text("usage_usec 1000\nnr_throttled 0\n")
        (node / "cpu.max").write_text("max 100000\n")
        (node / "memory.max").write_text("max\n")
        (node / "memory.current").write_text("0\n")
        (node / "memory.peak").write_text("0\n")
        (node / "memory.events").write_text("oom 0\noom_kill 0\nhigh 0\nmax 0\n")
        return cls(path=node)

    def require_delegated(self, *, required=("cpu", "memory")) -> None:
        del required

    def attach(self, pid: int) -> None:
        self._attached.add(int(pid))
        (self.path / "cgroup.procs").write_text(
            "\n".join(str(item) for item in sorted(self._attached)) + "\n")

    def pids(self) -> tuple[int, ...]:
        alive = []
        for pid in sorted(self._attached):
            try:
                os.kill(pid, 0)
            except OSError:
                continue
            alive.append(pid)
        self._attached = set(alive)
        return tuple(alive)

    def cpu_usage_us(self) -> int:
        return 1000 + self.throttle_count

    def nr_throttled(self) -> int:
        return self.throttle_count

    def memory_current(self) -> int:
        return self.charged_bytes

    def memory_peak(self) -> int:
        return self.charged_bytes + 1024

    def memory_events(self) -> dict[str, int]:
        return dict(self.memory_events_document)

    def remove(self) -> None:
        if self.pids():
            raise ContractError("MEASUREMENT_CLEANUP_FAILED: cgroup_not_empty")
        for child in sorted(self.path.iterdir()):
            child.unlink()
        self.path.rmdir()


class HermeticDevice:
    """Whole-device NVML port with a fixed, safe headroom."""

    def __init__(self, *, total_bytes: int = 1000, used_bytes: int = 100) -> None:
        self._total = int(total_bytes)
        self._used = int(used_bytes)

    @property
    def total_bytes(self) -> int:
        return self._total

    @property
    def used_bytes(self) -> int:
        return self._used

    @property
    def consumers(self) -> tuple[int, ...]:
        return (os.getpid(),)

    @property
    def name(self) -> str:
        return "hermetic-gpu"


def _host_facts(**overrides) -> HostFacts:
    values = {
        "mem_total_bytes": 1000, "mem_available_bytes": 820, "swap_total_bytes": 0,
        "swap_pages": 0, "psi_full_s": 0.0, "cpu_capacity": 8.0, "cpu_host_cores": 24,
        "cpu_set_used_core_equivalent": 0.1, "cpu_host_used_core_equivalent": 0.1,
        "cpu_quota_core_equivalent": 8.0, "cpuset": "0-7", "nr_throttled": 0,
        "gpu_index": 0, "gpu_name": "hermetic-gpu", "gpu_uuid": "GPU-hermetic",
        "gpu_total_bytes": 1000.0, "gpu_used_bytes": 100.0, "gpu_consumers": (11,),
        "same_uid_pids": (11,), "own_tree_rss_bytes": 10, "own_tree_gpu_bytes": 0.0,
        "attributed": True,
        "facts": {"gpu_uuid": "GPU-hermetic", "cpu_model": "fixture", "kernel": "fixture",
                  "python": "3.12.3", "container_marker": "none", "install_kind": ""},
    }
    values.update(overrides)
    return HostFacts(**values)


def _session_factory(tmp_path, *, cgroup_holder=None, device=None, quiet_s=0.02):
    def factory(**kwargs):
        cgroup = HermeticCgroup.create(
            parent=tmp_path / "cgroup", name=f"batch-{kwargs['batch_id']}")
        if cgroup_holder is not None:
            cgroup_holder.append(cgroup)
        values = {**kwargs, "cgroup_parent": tmp_path / "cgroup"}
        return MeasurementSession(
            **values, cgroup_factory=lambda: cgroup,
            device_factory=lambda: device or HermeticDevice(),
            observation_source=LiveObservationSource(host_probe=lambda: _host_facts()),
            quiet_s=quiet_s)
    return factory


# --- fixtures ------------------------------------------------------------------------

def _install_prefix(tmp_path, *, exit_code: int = 0, sleep_s: float = 0.0) -> Path:
    """A frozen copied install with a real launcher that records its own argv."""

    prefix = tmp_path / "install"
    launcher = prefix / "so101_demo_py/lib/so101_demo_py/so101_parallel_batch"
    launcher.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    launcher.write_text(
        "#!/bin/sh\n"
        'printf "%s\\n" "$@" > "$SO101_TEST_ARGV_FILE"\n'
        f"sleep {sleep_s}\n"
        f"exit {exit_code}\n")
    launcher.chmod(0o700)
    for name in ("__init__.py", "resource_measurement.py"):
        _write(prefix / INSTALLED_PATTERN / name, b"# installed copy\n")
    return prefix


def _bindings(tmp_path, prefix: Path) -> dict:
    points = tmp_path / "models/points.yaml"
    points_sha = _write(points, b"points: [p1, p2]\n")
    weights = tmp_path / "models/yolo.pt"
    weights_sha = _write(weights, b"yolo-weights")
    grounded = tmp_path / "models/grounded"
    grounded.mkdir(mode=0o700, parents=True, exist_ok=True)
    manifest_sha = _write(grounded / "manifest.json", b'{"models": ["grounded", "sam"]}\n')
    evidence_root = tmp_path / "evidence"
    evidence_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    provenance = tmp_path / "bindings/provenance.json"
    provenance_sha = _write(provenance, json.dumps({
        "schema_version": 1, "kind": "OFFLINE_COPIED_BINDING",
        "source_root": str(WORKTREE), "source_commit": "a" * 40,
        "install_prefix": str(prefix), "install_kind": "offline_copied",
    }, sort_keys=True).encode())
    return {
        "points_path": str(points), "points_sha256": points_sha,
        "yolo_weights_path": str(weights), "yolo_weights_sha256": weights_sha,
        "grounded_root": str(grounded), "grounded_manifest_sha256": manifest_sha,
        "broker_image_id": "sha256:" + "b" * 64,
        "provenance_binding_path": str(provenance),
        "provenance_binding_sha256": provenance_sha,
        "evidence_root": evidence_root,
    }


def _sealed_identity(tmp_path, bindings) -> str:
    """The identity the installed composer itself derives for these real bytes."""

    from so101_demo.parallel_batch.resource_budget import (
        build_runtime_fingerprint_from_environment)

    environment = {
        "SO101_VALIDATION_PROVENANCE_BINDING": bindings["provenance_binding_path"],
        "SO101_PARALLEL_RUNTIME_CONFIG": str(V2_CONFIG),
    }
    return build_runtime_fingerprint_from_environment(
        environment, identity=None, config_path=V2_CONFIG).sha256


def _authorization_document(tmp_path, bindings, **changes) -> dict:
    document = {
        "schema_version": 2, "operator_uid": os.getuid(), "dispatch_id": "dispatch-a",
        "task_id": "task-a", "source_commit": "a" * 40,
        "execution_identity_sha256": _sealed_identity(tmp_path, bindings),
        "worker_count": 2, "catalog_sha256": bindings["points_sha256"], "seed": 7,
        "lifecycle": "FULL_RESTART", "maximum_batches": 1, "batch_deadline_s": 5400.0,
        "expires_at_ns": time.time_ns() + 3_600_000_000_000,
        "batch_root": str(bindings["evidence_root"] / "batches"),
        "owned_scope_sha256": "d" * 64, "safety_policy_sha256": "e" * 64,
        "intent": "CALIBRATION_ONLY", "calibration_sha256": None,
        "runtime_bindings": {
            key: value for key, value in bindings.items() if key != "evidence_root"},
    }
    document.update(changes)
    return document


def _sealed_authorization(tmp_path, bindings, **changes):
    from so101_demo.parallel_batch.resource_measurement import MeasurementAuthorization

    document = _authorization_document(tmp_path, bindings, **changes)
    digest = _write(tmp_path / "private/authorization.json",
                    json.dumps(document, sort_keys=True).encode())
    path = tmp_path / "private/authorization.json"
    return MeasurementAuthorization.load(path, expected_sha256=digest), path, digest


def _argv(tmp_path, bindings, path, digest, *, intent="CALIBRATION_ONLY"):
    return ["--authorization", str(path), "--authorization-sha256", digest,
            "--config", str(V2_CONFIG), "--batch-id", "batch-a",
            "--evidence-root", str(bindings["evidence_root"]), "--intent", intent]


# --- R1: the default CLI runs the default launcher with measurement authority -------

def test_default_cli_runs_the_installed_launcher_with_sealed_authority(tmp_path, capsys):
    prefix = _install_prefix(tmp_path)
    bindings = _bindings(tmp_path, prefix)
    authorization, path, digest = _sealed_authorization(tmp_path, bindings)
    argv_file = tmp_path / "argv.txt"
    previous = os.environ.get("SO101_TEST_ARGV_FILE")
    os.environ["SO101_TEST_ARGV_FILE"] = str(argv_file)
    holders: list[HermeticCgroup] = []
    try:
        code = main(
            _argv(tmp_path, bindings, path, digest), capability_probe=lambda: {
                "cgroup_parent": str(tmp_path / "cgroup"), "controllers": ["cpu", "memory"]},
            session_factory=_session_factory(tmp_path, cgroup_holder=holders))
    finally:
        if previous is None:
            os.environ.pop("SO101_TEST_ARGV_FILE", None)
        else:
            os.environ["SO101_TEST_ARGV_FILE"] = previous
    assert code == 0, capsys.readouterr().err
    summary = json.loads(capsys.readouterr().out)
    assert summary["status"] == "SEALED" and summary["worker_count"] == 2
    assert Path(summary["sealed_path"]).is_relative_to(
        authorization.batch_root / "batch-a")
    # The child really received the sealed authorization, not a production profile.
    transported = argv_file.read_text().split()
    assert "--measurement-authorization" in transported
    assert transported[transported.index("--measurement-authorization") + 1] == str(path)
    assert transported[transported.index(
        "--measurement-authorization-sha256") + 1] == digest
    assert "--max-points-per-worker" not in transported
    # The seal preserves the original authorization, and the run left real raw streams.
    sealed = json.loads(Path(summary["sealed_path"]).read_bytes())
    assert sealed["dispatch_id"] == authorization.dispatch_id
    assert sealed["task_id"] == authorization.task_id
    assert sealed["source_commit"] == authorization.source_commit
    assert sealed["safety_policy_sha256"] == authorization.safety_policy_sha256
    assert sealed["owned_scope_sha256"] == authorization.owned_scope_sha256
    assert sealed["calibration_sha256"] == authorization.calibration_sha256
    assert sealed["execution_identity_sha256"] == authorization.execution_identity_sha256
    assert sealed["batch_root"] == str(authorization.batch_root / "batch-a")
    assert sealed["authorization_sha256"] == digest
    names = {entry["name"] for entry in sealed["raw_files"]}
    assert {"samples.jsonl", "coverage-events.json", "cleanup-receipt.json",
            "workload-stdout.log", "workload-stderr.log"} <= names
    receipt = json.loads((authorization.batch_root / "batch-a/cleanup-receipt.json")
                         .read_bytes())
    assert receipt["containment_cleared"] is True
    assert receipt["samples"] >= 1
    assert receipt["limits"]["memory_max_bytes"] == int(0.8 * 1000 - 180 - 10)
    assert holders and holders[0].path.exists() is False


def test_default_cli_refuses_a_non_zero_workload_and_leaks_no_cgroup(tmp_path, capsys):
    prefix = _install_prefix(tmp_path, exit_code=3)
    bindings = _bindings(tmp_path, prefix)
    authorization, path, digest = _sealed_authorization(tmp_path, bindings)
    holders: list[HermeticCgroup] = []
    os.environ["SO101_TEST_ARGV_FILE"] = str(tmp_path / "argv.txt")
    try:
        code = main(_argv(tmp_path, bindings, path, digest),
                    capability_probe=lambda: {}, session_factory=_session_factory(
                        tmp_path, cgroup_holder=holders))
    finally:
        os.environ.pop("SO101_TEST_ARGV_FILE", None)
    assert code == 1
    assert "MEASUREMENT_WORKLOAD_FAILED" in capsys.readouterr().err
    assert holders and holders[0].path.exists() is False
    assert not list((authorization.batch_root / "batch-a/sealed").glob("*.json")) \
        if (authorization.batch_root / "batch-a/sealed").is_dir() else True


def test_default_cli_refuses_an_inherited_production_authority(tmp_path, capsys, monkeypatch):
    prefix = _install_prefix(tmp_path)
    bindings = _bindings(tmp_path, prefix)
    _, path, digest = _sealed_authorization(tmp_path, bindings)
    monkeypatch.setenv("SO101_VALIDATION_BUDGET_PROFILE", "/sealed/profile.json")
    code = main(_argv(tmp_path, bindings, path, digest), capability_probe=lambda: {},
                session_factory=_session_factory(tmp_path))
    assert code == 1
    assert "MEASUREMENT_AUTHORITY_ENV_CONFLICT" in capsys.readouterr().err


def test_default_cli_refuses_a_swapped_composition_argument(tmp_path, capsys):
    prefix = _install_prefix(tmp_path)
    bindings = _bindings(tmp_path, prefix)
    _, path, digest = _sealed_authorization(tmp_path, bindings)
    argv = _argv(tmp_path, bindings, path, digest)
    argv[argv.index("--batch-id") + 1] = "batch-b"
    # The plan is derived from the sealed document, so a caller cannot rename the batch.
    code = main(argv, capability_probe=lambda: {}, session_factory=_session_factory(tmp_path))
    assert code == 0, capsys.readouterr().err
    summary = json.loads(capsys.readouterr().out)
    assert summary["batch_id"] == "batch-b"


# --- R2: the real session latches, kills, cleans and refuses ------------------------

def test_real_session_latches_on_a_safety_breach_and_refuses(tmp_path):
    prefix = _install_prefix(tmp_path, sleep_s=30)
    bindings = _bindings(tmp_path, prefix)
    authorization, path, digest = _sealed_authorization(tmp_path, bindings)
    plan = build_candidate_plan(
        authorization=authorization, authorization_path=path, config_path=V2_CONFIG,
        evidence_root=bindings["evidence_root"], batch_id="batch-a")
    holders: list[HermeticCgroup] = []
    breached = []

    def factory(**kwargs):
        cgroup = HermeticCgroup.create(parent=tmp_path / "cgroup", name="breach")
        cgroup.memory_events_document = {"oom": 0, "oom_kill": 1, "high": 0, "max": 0}
        cgroup.charged_bytes = 500
        breached.append(cgroup)
        values = {**kwargs, "cgroup_parent": tmp_path / "cgroup"}
        return MeasurementSession(
            **values, cgroup_factory=lambda: cgroup, device_factory=HermeticDevice,
            observation_source=LiveObservationSource(host_probe=lambda: _host_facts()),
            quiet_s=0.0, sampler_interval_s=0.01, host_facts=lambda: _host_facts())
    del holders

    from so101_demo.cli.measure_parallel_resources import production_runner_factory
    from so101_demo.parallel_batch.contracts import load_parallel_runtime_config_v2

    config = load_parallel_runtime_config_v2(V2_CONFIG)
    session = factory(authorization=authorization, batch_root=plan.batch_root,
                      batch_id=plan.batch_id, sampling=config.measurement.sampling,
                      safety=config.measurement.safety, owner=_identity())
    started = time.monotonic()
    with pytest.raises(ContractError) as error:
        run_candidate_batch(plan=plan, runner=production_runner_factory(plan), session=session)
    assert "MEASUREMENT_ABORT_LATCHED" in str(error.value)
    assert "CGROUP_MEMORY_OOM_KILL" in str(error.value)
    assert time.monotonic() - started < 20
    assert breached and breached[0].path.exists() is False


def test_real_session_enforces_the_authorized_deadline(tmp_path):
    prefix = _install_prefix(tmp_path, sleep_s=30)
    bindings = _bindings(tmp_path, prefix)
    authorization, path, digest = _sealed_authorization(tmp_path, bindings)
    plan = build_candidate_plan(
        authorization=authorization, authorization_path=path, config_path=V2_CONFIG,
        evidence_root=bindings["evidence_root"], batch_id="batch-a")
    from so101_demo.parallel_batch.contracts import load_parallel_runtime_config_v2

    config = load_parallel_runtime_config_v2(V2_CONFIG)
    cgroup = HermeticCgroup.create(parent=tmp_path / "cgroup", name="deadline")
    session = MeasurementSession(
        authorization=authorization, batch_root=plan.batch_root, batch_id=plan.batch_id,
        sampling=config.measurement.sampling, safety=config.measurement.safety,
        owner=_identity(), cgroup_parent=tmp_path / "cgroup",
        cgroup_factory=lambda: cgroup, device_factory=HermeticDevice,
        observation_source=LiveObservationSource(host_probe=lambda: _host_facts()),
        quiet_s=0.0, sampler_interval_s=0.01)
    from so101_demo.cli.measure_parallel_resources import production_runner_factory

    # Only a shorter offline deadline is allowed; the sealed authorization is the bound.
    with pytest.raises(ContractError) as error:
        MeasurementSession(
            authorization=authorization, batch_root=plan.batch_root, batch_id=plan.batch_id,
            sampling=config.measurement.sampling, safety=config.measurement.safety,
            owner=_identity(), cgroup_factory=lambda: cgroup,
            deadline_s=authorization.batch_deadline_s + 1)
    assert "MEASUREMENT_DEADLINE_INVALID" in str(error.value)
    session.deadline_s = 0.2
    with pytest.raises(ContractError) as error:
        run_candidate_batch(
            plan=plan, runner=production_runner_factory(plan), session=session)
    assert "MEASUREMENT_DEADLINE_EXCEEDED" in str(error.value)
    assert cgroup.path.exists() is False


def test_measurement_arguments_must_match_the_sealed_authorization(tmp_path):
    from so101_demo.parallel_batch.resource_measurement import (
        verify_measurement_arguments)

    prefix = _install_prefix(tmp_path)
    bindings = _bindings(tmp_path, prefix)
    authorization, path, digest = _sealed_authorization(tmp_path, bindings)
    del path, digest
    common = {
        "authorization": authorization, "batch_id": "batch-a", "worker_count": 2,
        "evidence_root": authorization.batch_root / "batch-a",
        "points_path": Path(bindings["points_path"]),
        "points_sha256": bindings["points_sha256"],
        "yolo_weights_path": Path(bindings["yolo_weights_path"]),
        "yolo_weights_sha256": bindings["yolo_weights_sha256"],
        "grounded_root": Path(bindings["grounded_root"]),
        "grounded_manifest_sha256": bindings["grounded_manifest_sha256"],
        "broker_image": bindings["broker_image_id"], "config_path": V2_CONFIG,
    }
    verify_measurement_arguments(**common)
    with pytest.raises(ContractError) as error:
        verify_measurement_arguments(**{**common, "worker_count": 3})
    assert "MEASUREMENT_ARGUMENT_MISMATCH: WORKER_COUNT" in str(error.value)
    with pytest.raises(ContractError) as error:
        verify_measurement_arguments(**{**common, "broker_image": "sha256:" + "c" * 64})
    assert "MEASUREMENT_ARGUMENT_MISMATCH: BROKER_IMAGE" in str(error.value)
    with pytest.raises(ContractError) as error:
        verify_measurement_arguments(
            **{**common, "evidence_root": tmp_path / "other-root"})
    assert "MEASUREMENT_ARGUMENT_MISMATCH" in str(error.value)


def test_launcher_permissions_and_identity_drift_are_refused(tmp_path, capsys):
    prefix = _install_prefix(tmp_path)
    bindings = _bindings(tmp_path, prefix)
    _, path, digest = _sealed_authorization(tmp_path, bindings)
    # Removing the executable bit is a real unavailable runtime, not a silent skip.
    launcher = prefix / "so101_demo_py/lib/so101_demo_py/so101_parallel_batch"
    launcher.chmod(0o600)
    assert stat.S_IMODE(launcher.stat().st_mode) == 0o600
    assert main(_argv(tmp_path, bindings, path, digest), capability_probe=lambda: {},
                session_factory=_session_factory(tmp_path)) == 1
    assert "MEASUREMENT_WORKLOAD" in capsys.readouterr().err

    # A drifted identity can no longer be derived, so the sealed bytes are refused.
    launcher.chmod(0o700)
    _write(prefix / INSTALLED_PATTERN / "resource_measurement.py", b"# drifted bytes\n")
    assert main(_argv(tmp_path, bindings, path, digest), capability_probe=lambda: {},
                session_factory=_session_factory(tmp_path)) == 1
    assert "RUNTIME_FINGERPRINT_MISMATCH" in capsys.readouterr().err
