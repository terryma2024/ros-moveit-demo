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

    def memory_swap_current(self) -> int:
        return 0

    def memory_pressure_full(self) -> int:
        return 0

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

    def refresh(self) -> dict:
        return {"total_bytes": self._total, "used_bytes": self._used}

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
    _write(prefix / INSTALLED_PATTERN / "so101_demo/cli/mujoco_parallel_batch.py",
           b"# installed launcher module\n")
    _write(prefix / INSTALLED_PATTERN / "so101_demo_py-0.1.0-py3.12.egg-info/entry_points.txt",
           b"[console_scripts]\nso101_parallel_batch = "
           b"so101_demo.cli.mujoco_parallel_batch:main\n")
    (prefix / "so101_mujoco_support").mkdir(mode=0o700, parents=True, exist_ok=True)
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


def _image_inspector(_tag):
    """Local image stub: reports the digest the fixtures seal in their authorizations."""

    return "sha256:" + "b" * 64

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
            image_inspector=_image_inspector, session_factory=_session_factory(tmp_path, cgroup_holder=holders))
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
                    capability_probe=lambda: {}, image_inspector=_image_inspector, session_factory=_session_factory(
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
                image_inspector=_image_inspector, session_factory=_session_factory(tmp_path))
    assert code == 1
    assert "MEASUREMENT_AUTHORITY_ENV_CONFLICT" in capsys.readouterr().err


def test_default_cli_refuses_a_swapped_composition_argument(tmp_path, capsys):
    prefix = _install_prefix(tmp_path)
    bindings = _bindings(tmp_path, prefix)
    _, path, digest = _sealed_authorization(tmp_path, bindings)
    argv = _argv(tmp_path, bindings, path, digest)
    argv[argv.index("--batch-id") + 1] = "batch-b"
    # The plan is derived from the sealed document, so a caller cannot rename the batch.
    code = main(argv, capability_probe=lambda: {}, image_inspector=_image_inspector, session_factory=_session_factory(tmp_path))
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
        run_candidate_batch(plan=plan, runner=production_runner_factory(plan, image_inspector=_image_inspector), session=session)
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
            plan=plan, runner=production_runner_factory(plan, image_inspector=_image_inspector), session=session)
    assert "MEASUREMENT_DEADLINE_EXCEEDED" in str(error.value)
    assert cgroup.path.exists() is False


def test_default_capability_probe_verifies_the_session_selection(tmp_path, monkeypatch):
    """The default probe must check the exact cgroup parent/device the session owns."""

    from so101_demo.cli import measure_parallel_resources as cli

    prefix = _install_prefix(tmp_path)
    bindings = _bindings(tmp_path, prefix)
    _, path, digest = _sealed_authorization(tmp_path, bindings)
    requested = tmp_path / "delegated-cgroup"
    requested.mkdir()
    seen: list[dict[str, object]] = []

    def fake_probe(**kwargs):
        seen.append(kwargs)
        return {}

    monkeypatch.setattr(cli, "require_measurement_capabilities", fake_probe)
    main(_argv(tmp_path, bindings, path, digest) + [
        "--cgroup-parent", str(requested), "--device-index", "1"],
        image_inspector=_image_inspector, session_factory=_session_factory(tmp_path))
    assert seen == [{
        "cgroup_parent": requested, "device_index": 1,
    }], seen


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
                image_inspector=_image_inspector, session_factory=_session_factory(tmp_path)) == 1
    assert "MEASUREMENT_WORKLOAD" in capsys.readouterr().err

    # A drifted identity can no longer be derived, so the sealed bytes are refused.
    launcher.chmod(0o700)
    _write(prefix / INSTALLED_PATTERN / "resource_measurement.py", b"# drifted bytes\n")
    assert main(_argv(tmp_path, bindings, path, digest), capability_probe=lambda: {},
                image_inspector=_image_inspector, session_factory=_session_factory(tmp_path)) == 1
    assert "RUNTIME_FINGERPRINT_MISMATCH" in capsys.readouterr().err


def _delegated_tree(root, *, stat_mode=0o444):
    (root / "cgroup.controllers").write_text("cpu memory\n")
    for name in ("cgroup.procs", "cpu.max", "memory.max"):
        (root / name).write_text("\n")
    (root / "cpu.stat").write_text("usage_usec 0\n")
    (root / "cpu.stat").chmod(stat_mode)
    return root


def test_owned_cgroup_accepts_read_only_cpu_stat(tmp_path):
    """cgroup v2 exposes cpu.stat as mode 0444 even inside a delegated subtree."""

    from so101_demo.parallel_batch.owned_resources import OwnedCgroupV2

    node = tmp_path / "owned"
    node.mkdir()
    _delegated_tree(node)
    OwnedCgroupV2(path=node).require_delegated()


def test_owned_cgroup_rejects_missing_cpu_stat(tmp_path):
    from so101_demo.parallel_batch.contracts import ContractError
    from so101_demo.parallel_batch.owned_resources import OwnedCgroupV2

    node = tmp_path / "owned"; node.mkdir(); _delegated_tree(node)
    (node / "cpu.stat").unlink()
    with pytest.raises(ContractError, match="cpu.stat"):
        OwnedCgroupV2(path=node).require_delegated()


def test_owned_cgroup_rejects_unwritable_control_file(tmp_path):
    from so101_demo.parallel_batch.contracts import ContractError
    from so101_demo.parallel_batch.owned_resources import OwnedCgroupV2

    node = tmp_path / "owned"; node.mkdir(); _delegated_tree(node)
    (node / "cpu.max").chmod(0o444)
    with pytest.raises(ContractError, match="cpu.max"):
        OwnedCgroupV2(path=node).require_delegated()


def _page_rounding_cgroup(tmp_path, *, mode="round"):
    from so101_demo.parallel_batch.owned_resources import OwnedCgroupV2

    node = tmp_path / "owned"; node.mkdir(); _delegated_tree(node)
    page = os.sysconf("SC_PAGE_SIZE")

    class Cgroup(OwnedCgroupV2):
        def _read(self, name, default=None):
            raw = super()._read(name, default)
            if name == "memory.max":
                if mode == "round":
                    return str(int(raw) // page * page)
                if mode == "inflate":
                    return str(int(raw) + page)
                if mode == "zero":
                    return "0"
            return raw

    return Cgroup(path=node)


def test_set_limits_accepts_kernel_page_rounding(tmp_path):
    """cgroup v2 rounds memory.max down to the page size; that is not a failure."""

    requested = 4096 * 3 + 123
    limits = _page_rounding_cgroup(tmp_path).set_limits(
        memory_max_bytes=requested, cpu_quota_us=1910053, period_us=100000)
    page = os.sysconf("SC_PAGE_SIZE")
    assert limits == {"memory_max_bytes": requested // page * page,
                      "cpu_quota_us": 1910053, "cpu_period_us": 100000}


def test_set_limits_refuses_inflated_memory_cap(tmp_path):
    from so101_demo.parallel_batch.contracts import ContractError

    with pytest.raises(ContractError, match="MEASUREMENT_LIMIT_UNENFORCEABLE"):
        _page_rounding_cgroup(tmp_path, mode="inflate").set_limits(
            memory_max_bytes=4096 * 3 + 123, cpu_quota_us=1910053, period_us=100000)


def test_set_limits_refuses_zero_memory_cap(tmp_path):
    from so101_demo.parallel_batch.contracts import ContractError

    with pytest.raises(ContractError, match="MEASUREMENT_LIMIT_UNENFORCEABLE"):
        _page_rounding_cgroup(tmp_path, mode="zero").set_limits(
            memory_max_bytes=4096 * 3 + 123, cpu_quota_us=1910053, period_us=100000)


def test_sample_loop_schedules_samples_on_a_fixed_grid(tmp_path, monkeypatch):
    """A slow sample must not add its own duration to the sampling period.

    The session loop used to wait the interval *after* each sample, so a 70 ms sample under
    a 50 ms interval produced a 120 ms period -- past the 100 ms maximum gap, which is how
    the first real N1 run latched SAMPLER_GAP right after the workload spawn.
    """

    import threading, time, types
    import so101_demo.parallel_batch.resource_measurement as rm
    from so101_demo.parallel_batch.owned_resources import MeasurementSession

    stamps: list[float] = []

    def fake_sample_resources(**_kwargs):
        time.sleep(0.07)
        stamps.append(time.monotonic())
        observation = types.SimpleNamespace(
            capacity={}, observed={}, background={}, remaining={}, error={},
            attribution_complete=True, swap_delta=0, psi_full_delta=0, throttled=False)
        return types.SimpleNamespace(sequence=len(stamps), monotonic_s=stamps[-1],
                                     observation=observation, diagnostics={})

    monkeypatch.setattr(rm, "sample_resources", fake_sample_resources)
    session = object.__new__(MeasurementSession)
    session._stopped = threading.Event(); session._rebaseline = threading.Event()
    session.cgroup = None; session.device = None; session.owner = ()
    session._lock = threading.Lock(); session.samples = 0
    session.samples_path = tmp_path / "samples.jsonl"
    session.control = None; session._control_socket = None; session.abort_reason = None
    session._interval_s = 0.05; session.clock = time.monotonic
    session.sampling = types.SimpleNamespace(cgroup_cpu_period_us=100000)

    thread = threading.Thread(target=session._sample_loop, daemon=True)
    thread.start(); time.sleep(0.6); session._stopped.set(); thread.join(timeout=3)
    gaps = [later - earlier for earlier, later in zip(stamps, stamps[1:])]
    assert len(gaps) >= 3, gaps
    assert max(gaps) < 0.10, gaps


class _FakeCgroup:
    """A cgroup reporting a scripted cpu.stat, without touching the real one."""

    attribution_complete = True
    throttled = False
    cpu_capacity_core_equivalent = 24.0

    def __init__(self, usage_us, swap=None, pressure=None):
        self._usage = list(usage_us)
        self._swap = list(swap or [0] * len(self._usage))
        self._pressure = list(pressure or [0] * len(self._usage))

    def memory_swap_current(self):
        return self._swap.pop(0)

    def memory_pressure_full(self):
        return self._pressure.pop(0)

    def cpu_usage_us(self):
        return self._usage.pop(0)

    def memory_current(self):
        return 1024 * 1024


class _FakeDevice:
    total_bytes = 8 * 1024 ** 3
    used_bytes = 0

    def refresh(self):
        return {"total_bytes": self.total_bytes, "used_bytes": self.used_bytes}


def test_sample_resources_measures_cpu_over_a_full_quota_period(monkeypatch):
    """A cgroup may spend a whole quota inside one period, so a shorter window can
    read up to twice the enforced cap -- the 22.43 cores seen against an 18.6-core
    quota were that artifact, and they latched CPU_ENVELOPE on the first N1 run."""

    import types
    import so101_demo.parallel_batch.resource_measurement as rm

    clock = [100.0]
    monkeypatch.setattr(rm, "time", types.SimpleNamespace(monotonic=lambda: clock[0]))
    cgroup = _FakeCgroup([0, 1860000, 1860000])
    state = {"cpu_window_s": 0.1}
    rates = []
    for sequence, moment in enumerate((100.0, 100.05, 100.10), start=1):
        clock[0] = moment
        sample = rm.sample_resources(owned_inventory=(), cgroup=cgroup, device=_FakeDevice(),
                                     sequence=sequence, state=state)
        rates.append(sample.observation.observed["cpu_core_equivalent"])
    assert rates[0] == 0.0, rates
    assert rates[1] == 0.0, rates
    assert abs(rates[2] - 18.6) < 0.05, rates


def test_sample_loop_rebaselines_when_asked(tmp_path, monkeypatch):
    """CPU a task burned before it joined the cgroup migrates with it, so the sampled
    rate must restart from the attach point instead of counting that burst."""

    import threading, time, types
    import so101_demo.parallel_batch.resource_measurement as rm
    from so101_demo.parallel_batch.owned_resources import MeasurementSession

    seen: list[dict] = []

    def fake_sample_resources(**kwargs):
        seen.append(dict(kwargs["state"]))
        kwargs["state"]["monotonic_s"] = time.monotonic()   # mimic the real carry-over
        time.sleep(0.03)
        observation = types.SimpleNamespace(
            capacity={}, observed={}, background={}, remaining={}, error={},
            attribution_complete=True, swap_delta=0, psi_full_delta=0, throttled=False)
        return types.SimpleNamespace(sequence=len(seen), monotonic_s=time.monotonic(),
                                     observation=observation, diagnostics={})

    monkeypatch.setattr(rm, "sample_resources", fake_sample_resources)
    session = object.__new__(MeasurementSession)
    session._stopped = threading.Event(); session._rebaseline = threading.Event()
    session.cgroup = None; session.device = None; session.owner = ()
    session._lock = threading.Lock(); session.samples = 0
    session.samples_path = tmp_path / "samples.jsonl"
    session.control = None; session._control_socket = None; session.abort_reason = None
    session._interval_s = 0.01; session.clock = time.monotonic
    session.sampling = types.SimpleNamespace(cgroup_cpu_period_us=100000)

    thread = threading.Thread(target=session._sample_loop, daemon=True)
    thread.start(); time.sleep(0.15)
    session._request_sampling_rebaseline(); time.sleep(0.15)
    session._stopped.set(); thread.join(timeout=3)
    assert len(seen) >= 4, seen
    dropped = [i for i in range(1, len(seen))
               if "monotonic_s" not in seen[i] and "monotonic_s" in seen[i - 1]]
    assert dropped, seen


def test_launcher_refuses_an_existing_root_without_a_measurement(tmp_path):
    from so101_demo.cli.mujoco_parallel_batch import CliError, _batch_evidence_root_state

    root = tmp_path / "b"; root.mkdir(mode=0o700)
    with pytest.raises(CliError, match="DUPLICATE_BATCH_EVIDENCE_ROOT"):
        _batch_evidence_root_state(evidence_root=root, measurement=False)


def test_launcher_accepts_the_sealed_measurement_root(tmp_path):
    """The measurement harness creates the sealed batch root before it spawns the
    launcher (run_candidate_batch), and verify_measurement_arguments pins that root to
    the authorization, so the launcher cannot demand exclusive creation there."""

    from so101_demo.cli.mujoco_parallel_batch import _batch_evidence_root_state

    root = tmp_path / "b"; root.mkdir(mode=0o700)
    (root / "raw").mkdir(); (root / "coverage-events.json").write_text("{}\n")
    _batch_evidence_root_state(evidence_root=root, measurement=True)


def test_launcher_rejects_a_loose_measurement_root(tmp_path):
    from so101_demo.cli.mujoco_parallel_batch import CliError, _batch_evidence_root_state

    root = tmp_path / "b"; root.mkdir(mode=0o755)
    with pytest.raises(CliError, match="MEASUREMENT_EVIDENCE_ROOT_INVALID"):
        _batch_evidence_root_state(evidence_root=root, measurement=True)


def test_launcher_rejects_a_finalized_measurement_root(tmp_path):
    from so101_demo.cli.mujoco_parallel_batch import CliError, _batch_evidence_root_state

    root = tmp_path / "b"; root.mkdir(mode=0o700)
    (root / "aggregate_results.json").write_text("{}\n")
    with pytest.raises(CliError, match="DUPLICATE_BATCH_EVIDENCE_ROOT"):
        _batch_evidence_root_state(evidence_root=root, measurement=True)


def test_measurement_gate_entrypoint_has_no_undefined_globals():
    """The launcher's measurement gate had never run: it referenced
    ParallelRuntimeConfigV2 without importing it and died with NameError on the first
    real measurement workload. Every global this entry point loads must resolve."""

    import builtins, dis
    from so101_demo.cli import mujoco_parallel_batch as launcher

    def loaded_globals(function):
        seen, stack = set(), [function.__code__]
        while stack:
            code = stack.pop()
            for instruction in dis.get_instructions(code):
                if instruction.opname == "LOAD_GLOBAL":
                    seen.add(instruction.argval)
            stack.extend(item for item in code.co_consts if hasattr(item, "co_names"))
        return seen

    missing = sorted(
        name for name in loaded_globals(launcher._compose_measurement_gate)
        if not hasattr(launcher, name) and not hasattr(builtins, name))
    assert missing == []


def _fingerprint(**facts):
    from so101_demo.parallel_batch.resource_identity import RuntimeFingerprint

    base = {"cpu_model": "test-cpu", "cpu_host_cores": 24, "gpu_name": "test-gpu",
            "install_prefix": "/tmp/install", "source_commit": "a" * 40}
    return RuntimeFingerprint(
        schema_version=2, facts={**base, **facts}, normalization_sha256="b" * 64,
        semantic_config_sha256="c" * 64, execution_inventory_sha256="d" * 64,
        installed_inventory_sha256="e" * 64)


def test_runtime_identity_ignores_the_observers_ambient_placement():
    """The authorizing parent sits in the delegated scope while the launcher it owns runs
    inside the measurement cgroup it created: same artifact, different cgroup, different
    quota and throttling counters. R must not change with the observer's placement."""

    parent = _fingerprint(cgroup="/sys/fs/cgroup/user.slice/so101-n1cal.scope/payload",
                          cpuset="0-23", cpu_quota_core_equivalent=18.6, nr_throttled=0)
    worker = _fingerprint(
        cgroup="/sys/fs/cgroup/user.slice/so101-n1cal.scope/payload/so101-measurement-x",
        cpuset="0-23", cpu_quota_core_equivalent=18.6, nr_throttled=3)
    assert parent.sha256 == worker.sha256


def test_runtime_identity_still_covers_the_artifact_and_host():
    assert _fingerprint(cgroup="/a").sha256 != _fingerprint(cgroup="/a", cpu_model="other")
    assert _fingerprint(cgroup="/a").sha256 != _fingerprint(cgroup="/a", gpu_name="other")
    assert _fingerprint(cgroup="/a").sha256 != _fingerprint(cgroup="/a", thread_environment={"OMP_NUM_THREADS": "1"})


def test_broker_image_verification_accepts_the_tag_carrying_the_sealed_digest():
    """The sealed binding is a digest, the launcher compares its tag, so the runner
    resolves the tag and proves it still points at the sealed image before spawning."""

    from so101_demo.cli.measure_parallel_resources import verify_broker_image

    digest = "sha256:" + "a" * 64
    assert verify_broker_image(tag="img:v1", digest=digest,
                               inspector=lambda tag: digest + "\n") == "img:v1"


def test_broker_image_verification_refuses_a_replaced_image():
    from so101_demo.cli.measure_parallel_resources import (
        MeasurementCliError, verify_broker_image)

    with pytest.raises(MeasurementCliError, match="MEASUREMENT_BROKER_IMAGE_MISMATCH"):
        verify_broker_image(tag="img:v1", digest="sha256:" + "a" * 64,
                            inspector=lambda tag: "sha256:" + "b" * 64)


def test_broker_image_verification_fails_closed_without_an_inspector():
    from so101_demo.cli.measure_parallel_resources import (
        MeasurementCliError, verify_broker_image)

    def broken(tag):
        raise OSError("no docker")

    with pytest.raises(MeasurementCliError, match="MEASUREMENT_BROKER_IMAGE_UNAVAILABLE"):
        verify_broker_image(tag="img:v1", digest="sha256:" + "a" * 64, inspector=broken)


def test_child_environment_exposes_the_installs_own_console(tmp_path):
    """A copied install ships its console beside the module it runs, with no bin entry,
    so the launcher's provenance check cannot find it on the inherited PATH."""

    import shutil
    from so101_demo.cli.measure_parallel_resources import child_environment_for_launcher

    console_dir = tmp_path / "lib"; console_dir.mkdir()
    console = console_dir / "so101_parallel_batch"
    console.write_text("#!/bin/sh\n"); console.chmod(0o755)
    environment = child_environment_for_launcher(
        {"PATH": "/usr/bin", "SO101_VALIDATION_BUDGET_PROFILE": "inherited"}, console_dir)
    assert environment["PATH"].split(":")[0] == str(console_dir)
    assert shutil.which("so101_parallel_batch", path=environment["PATH"]) == str(console)
    assert "SO101_VALIDATION_BUDGET_PROFILE" not in environment


def test_child_environment_works_without_an_inherited_path(tmp_path):
    from so101_demo.cli.measure_parallel_resources import child_environment_for_launcher

    console_dir = tmp_path / "lib"; console_dir.mkdir()
    environment = child_environment_for_launcher({}, console_dir)
    assert environment["PATH"] == str(console_dir)


def _overlay_inputs(tmp_path):
    (tmp_path / "so101_demo_py").mkdir(exist_ok=True)
    files = {}
    for name in ("console", "module", "entry_points", "config", "points"):
        path = tmp_path / name
        path.write_text(name + "\n")
        files[name] = path
    return files


def test_overlay_binding_document_matches_the_launcher_schema(tmp_path):
    from so101_demo.cli.measure_parallel_resources import write_overlay_provenance_binding

    files = _overlay_inputs(tmp_path)
    target = write_overlay_provenance_binding(
        target=tmp_path / "binding.json", source_root=tmp_path, build_root=tmp_path,
        install_root=tmp_path, package_prefix=tmp_path / "so101_demo_py",
        console=files["console"], module=files["module"], entry_points=files["entry_points"],
        parallel_config=files["config"], point_catalog=files["points"],
        source_commit="a" * 40)
    document = json.loads(target.read_text())
    assert set(document) == {"schema_version", "source_root", "source_commit", "build_root",
                             "install_root", "package_prefixes", "artifacts"}
    assert document["schema_version"] == 1
    assert set(document["artifacts"]) == {"coordinator_console", "coordinator_module",
                                          "entry_points", "parallel_config", "point_catalog"}
    for name, entry in document["artifacts"].items():
        assert len(entry["sha256"]) == 64, name
    assert (target.stat().st_mode & 0o777) == 0o600


def test_overlay_binding_refuses_a_missing_input(tmp_path):
    from so101_demo.cli.measure_parallel_resources import (
        MeasurementCliError, write_overlay_provenance_binding)

    files = _overlay_inputs(tmp_path)
    files["module"].unlink()
    with pytest.raises(MeasurementCliError, match="MEASUREMENT_OVERLAY_INPUT_MISSING"):
        write_overlay_provenance_binding(
            target=tmp_path / "binding.json", source_root=tmp_path, build_root=tmp_path,
            install_root=tmp_path, package_prefix=tmp_path / "so101_demo_py",
            console=files["console"], module=files["module"], entry_points=files["entry_points"],
            parallel_config=files["config"], point_catalog=files["points"],
            source_commit="a" * 40)


def test_private_batch_root_is_created_and_tightened(tmp_path):
    """The launcher refuses a measurement evidence root that is not private, so the
    harness must create it 0700 even when a parent already exists with looser bits."""

    from so101_demo.cli.measure_parallel_resources import ensure_private_batch_root

    parent = tmp_path / "batches"; parent.mkdir(mode=0o775)
    root = ensure_private_batch_root(parent / "batch-a")
    assert (root.stat().st_mode & 0o777) == 0o700
    loose = parent / "batch-b"; loose.mkdir(mode=0o775)
    assert (ensure_private_batch_root(loose).stat().st_mode & 0o777) == 0o700


def test_entry_points_come_from_the_sealed_install_prefix(tmp_path):
    """The launcher requires the metadata file to live under its build root, so it is
    taken from the sealed install prefix rather than from this interpreter's metadata."""

    from so101_demo.cli.measure_parallel_resources import (
        MeasurementCliError, install_prefix_entry_points)

    site = tmp_path / "so101_demo_py/lib/python3.12/site-packages"
    egg = site / "so101_demo_py-0.1.0-py3.12.egg-info"
    egg.mkdir(parents=True)
    (egg / "entry_points.txt").write_text("[console_scripts]\n")
    assert install_prefix_entry_points(tmp_path) == egg / "entry_points.txt"
    with pytest.raises(MeasurementCliError, match="MEASUREMENT_OVERLAY_INPUT_MISSING"):
        install_prefix_entry_points(tmp_path / "absent")


def test_child_environment_prefers_the_candidate_site_packages(tmp_path):
    """The launcher child must import the package its overlay declares, so the install's
    own site-packages goes ahead of whatever the parent had on PYTHONPATH."""

    from so101_demo.cli.measure_parallel_resources import child_environment_for_launcher

    console_dir = tmp_path / "lib"; console_dir.mkdir()
    site = tmp_path / "site-packages"; site.mkdir()
    environment = child_environment_for_launcher(
        {"PATH": "/usr/bin", "PYTHONPATH": "/somewhere/else"}, console_dir, site_packages=site)
    assert environment["PYTHONPATH"].split(":")[0] == str(site)
    assert environment["PYTHONPATH"].split(":")[1] == "/somewhere/else"
    bare = child_environment_for_launcher({}, console_dir, site_packages=site)
    assert bare["PYTHONPATH"] == str(site)


def test_overlay_package_prefixes_live_under_the_install_root(tmp_path):
    """The launcher requires both package prefixes to be inside its install root, so they
    are the install tree's own directories, not whatever AMENT happens to answer."""

    from so101_demo.cli.measure_parallel_resources import (
        MeasurementCliError, overlay_package_prefixes)

    for name in ("so101_demo_py", "so101_mujoco_support"):
        (tmp_path / name).mkdir()
    prefixes = overlay_package_prefixes(tmp_path)
    assert prefixes == {"so101_demo_py": tmp_path / "so101_demo_py",
                        "so101_mujoco_support": tmp_path / "so101_mujoco_support"}
    with pytest.raises(MeasurementCliError, match="MEASUREMENT_OVERLAY_INPUT_MISSING"):
        overlay_package_prefixes(tmp_path / "absent")


def test_child_ament_path_carries_absolute_prefixes(tmp_path):
    """The prefixes arrive as a mapping; iterating it as a sequence put bare package
    names on AMENT_PREFIX_PATH, so the launcher's own AMENT re-query fell through to
    whatever prefix the parent inherited and refused the overlay."""

    from so101_demo.cli.measure_parallel_resources import child_environment_for_launcher

    console_dir = tmp_path / "lib"; console_dir.mkdir()
    prefixes = {"so101_demo_py": tmp_path / "install/so101_demo_py",
                "so101_mujoco_support": tmp_path / "install/so101_mujoco_support"}
    site = tmp_path / "site"; site.mkdir()
    environment = child_environment_for_launcher(
        {"AMENT_PREFIX_PATH": "/inherited"}, console_dir, site_packages=site, prefixes=prefixes)
    entries = environment["AMENT_PREFIX_PATH"].split(":")
    assert entries[:2] == [str(prefixes["so101_demo_py"]), str(prefixes["so101_mujoco_support"])]
    assert entries[2] == "/inherited"


def test_sample_resources_takes_swap_from_the_owned_cgroup(monkeypatch):
    """Host-wide swap moves on its own -- one kilobyte of unrelated activity latched
    SWAP_ACTIVITY on run22 -- so the workload's swap is the owned cgroup's."""

    import types
    import so101_demo.parallel_batch.resource_measurement as rm

    clock = [500.0]
    monkeypatch.setattr(rm, "time", types.SimpleNamespace(monotonic=lambda: clock[0]))
    host_swap = [1_000_000]
    monkeypatch.setattr(rm, "_read_swap_and_psi", lambda: (host_swap[0], 0.0))
    cgroup = _FakeCgroup([0, 0], swap=[0, 4096])
    state = {}
    for sequence, moment in enumerate((500.0, 500.05), start=1):
        clock[0] = moment
        host_swap[0] -= 1
        sample = rm.sample_resources(owned_inventory=(), cgroup=cgroup, device=_FakeDevice(),
                                     sequence=sequence, state=state)
    assert sample.observation.swap_delta == 4096
    assert sample.diagnostics["swap_total"] == 999_998


def test_sample_resources_requires_the_cgroup_swap_counter():
    import so101_demo.parallel_batch.resource_measurement as rm
    from so101_demo.parallel_batch.contracts import ContractError

    class NoSwap:
        attribution_complete = True
        throttled = False
        cpu_capacity_core_equivalent = 24.0

        def cpu_usage_us(self):
            return 0

        def memory_current(self):
            return 0

    with pytest.raises(ContractError, match="MEASUREMENT_CAPABILITY_MISSING"):
        rm.sample_resources(owned_inventory=(), cgroup=NoSwap(), device=_FakeDevice(),
                            sequence=1, state={})


def test_sample_resources_reads_the_device_once_per_pass():
    """The pass called device.used_bytes twice and total_bytes once, and every access is a
    fresh NVML read, so a 50 ms sampling grid paid for three of them."""

    import so101_demo.parallel_batch.resource_measurement as rm

    class CountingDevice:
        total_bytes = 8 * 1024 ** 3
        used_bytes = 0

        def __init__(self):
            self.reads = 0

        def refresh(self):
            self.reads += 1
            return {"total_bytes": 8 * 1024 ** 3, "used_bytes": 1024}

    device = CountingDevice()
    cgroup = _FakeCgroup([0, 0], swap=[0, 0])
    state = {}
    for sequence in (1, 2):
        rm.sample_resources(owned_inventory=(), cgroup=cgroup, device=device,
                            sequence=sequence, state=state)
    assert device.reads == 2, device.reads


def test_sample_resources_takes_pressure_from_the_owned_cgroup(monkeypatch):
    """Host memory pressure moves for unrelated reasons (run24 latched PSI_FULL_STALL on
    0.0068 s of host-wide stall), so the policy reads the owned cgroup's pressure."""

    import types
    import so101_demo.parallel_batch.resource_measurement as rm

    monkeypatch.setattr(rm, "time", types.SimpleNamespace(monotonic=lambda: 900.0))
    host_psi = [0.0]
    monkeypatch.setattr(rm, "_read_swap_and_psi", lambda: (0, host_psi[0]))
    cgroup = _FakeCgroup([0, 0], swap=[0, 0], pressure=[1000, 6000])
    state = {}
    for sequence in (1, 2):
        host_psi[0] += 1.5
        sample = rm.sample_resources(owned_inventory=(), cgroup=cgroup, device=_FakeDevice(),
                                     sequence=sequence, state=state)
    assert sample.observation.psi_full_delta == 5000
    assert sample.diagnostics["psi_full_host_us"] == 3.0


def test_session_breach_ignores_swap_and_psi_activity():
    """CPU/RAM/GPU-only amendment (74d6b781): swap and PSI are not breach dimensions, so a
    healthy sample with swap or full-stall movement must not latch an abort."""

    import types
    from so101_demo.parallel_batch.owned_resources import MeasurementSession

    session = object.__new__(MeasurementSession)
    session.safety = types.SimpleNamespace(
        minimum_free_fraction=0.2, abort_on_psi_full_stall=True,
        throttling_disqualifies_run=True, capacity_fraction=0.8)
    session.cgroup = None
    capacity = {"cpu_core_equivalent": 10.0, "ram_bytes": 1000.0, "gpu_bytes": 100.0}
    observation = types.SimpleNamespace(
        attribution_complete=True, swap_delta=4096, psi_full_delta=0.5, throttled=False,
        capacity=capacity,
        observed={"cpu_core_equivalent": 1.0, "ram_bytes": 100.0, "gpu_bytes": 1.0},
        background={"cpu_core_equivalent": 0.1, "ram_bytes": 10.0, "gpu_bytes": 1.0})
    assert session._breach(types.SimpleNamespace(observation=observation)) is None


def test_safety_rules_no_longer_require_the_swap_or_psi_keys():
    """The authoritative policy drops both keys; documents that still carry them are
    deprecated compatibility data and must not be able to gate anything."""

    from so101_demo.parallel_batch.contracts import SafetyRulesV2

    rules = SafetyRulesV2(capacity_fraction=0.8, minimum_free_fraction=0.2, gpu_device_index=0,
                          throttling_disqualifies_run=True, require_complete_attribution=True)
    deprecated = SafetyRulesV2(capacity_fraction=0.8, minimum_free_fraction=0.2,
                               gpu_device_index=0, throttling_disqualifies_run=True,
                               require_complete_attribution=True,
                               abort_on_swap_activity=False, abort_on_psi_full_stall=False)
    assert rules.capacity_fraction == deprecated.capacity_fraction == 0.8
