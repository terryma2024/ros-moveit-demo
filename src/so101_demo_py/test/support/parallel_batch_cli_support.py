"""Fixtures and helpers shared by the parallel batch command tests."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys

from paths import PACKAGE_ROOT
import pytest

from so101_demo.parallel_batch.contracts.common import (
    PointStatus,
    RunMode,
)
from so101_demo.parallel_batch.contracts.identity import BatchSummary

PACKAGE = PACKAGE_ROOT


POINTS = PACKAGE / "config/mujoco/moveit_expert_validation_points.yaml"


CONFIG = PACKAGE / "config/mujoco/parallel_batch_linux_cuda.yaml"


ADAPTIVE_CONFIG = PACKAGE / "config/mujoco/adaptive_worker_pool.yaml"


YOLO_SHA = "f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781"


GROUNDED_SHA = "b55bb601d311407df8f9f25d9da18649f6bd78ac1299148bde0d07f7cfdfed05"


def _scratch_root():
    """Keep fixed-name integration fixtures short and isolated per xdist worker."""

    root = Path(os.environ["TMPDIR"]) / f"p{os.getpid():x}"
    root.mkdir(mode=0o700, exist_ok=True)
    return root


def _socket_fixture_root(tmp_path: Path, label: str) -> Path:
    """Use pytest's normal path unless Darwin needs a shorter AF_UNIX address."""

    if sys.platform != "darwin":
        return tmp_path
    suffix = hashlib.sha256(str(tmp_path).encode()).hexdigest()[:8]
    root = _scratch_root() / f"{label}-{suffix}"
    root.mkdir(mode=0o700, exist_ok=True)
    return root


class SyntheticAdmissionGate:
    """Offline test entry: admit every exact N without a real promoted profile."""

    execution_identity_sha256 = "a" * 64

    def __init__(self, code=None):
        self.code = code
        self.requests = []

    def admit(self, request):
        from so101_demo.parallel_batch.resource_budget import ResourceBudgetAdmission
        self.requests.append(request)
        admitted = self.code is None
        return ResourceBudgetAdmission(
            admitted=admitted,
            reason_codes=() if admitted else (self.code,),
            worker_count=request.worker_count,
            profile_sha256="b" * 64,
            qualification_sha256="c" * 64,
            execution_identity_sha256=request.execution_identity_sha256,
            observation_monotonic_s=1.0)


def _refusing_gate(code):
    return SyntheticAdmissionGate(code=code)


def _local_guard_check(self, policy, scope):
    """Run the real guard decision against real host reads, without spawning a helper.

    Only the probe *process* boundary is replaced. The snapshot still comes from the real
    cgroup/meminfo/NVML reads through ``probe_snapshot`` and the decision is still the real
    ``evaluate_snapshot``; the helper process itself is proven in
    ``test_parallel_start_guard_probe.py`` and in the CLI-level composition test.
    """

    import dataclasses as _dataclasses
    import time as _time

    from so101_demo.parallel_batch import start_guard as _guard

    started = _time.monotonic()
    ports = _dataclasses.replace(_guard.host_ports(), busy_window_s=0.0)
    if sys.platform == "darwin":
        class MacTestGpu:
            def devices(self):
                return (_guard.GpuDevice(0, "GPU-MACOS-TEST", 16 << 30, 8 << 30),)

        ports = _dataclasses.replace(ports, nvml=MacTestGpu())
    try:
        snapshot = _guard.probe_snapshot(policy, scope, started + policy.timeout_s, ports=ports)
        return _guard.evaluate_snapshot(snapshot, policy, scope, started_monotonic_s=started,
                                        completed_monotonic_s=_time.monotonic())
    except _guard.ProbeError as error:
        return _guard.GuardResult(
            scope=scope, status=_guard.FAIL, started_monotonic_s=started,
            completed_monotonic_s=_time.monotonic(),
            checks={"probe": _guard.GuardCheck(_guard.FAIL, error.reason, None, None, "state")},
            snapshot=None, cleanup_state="CLEAR")


@pytest.fixture(autouse=True)
def local_start_guard(monkeypatch, tmp_path_factory):
    """Offline seam: real reads and the real decision, no helper process per test."""

    from so101_demo.parallel_batch.start_guard_probe import ProbeCoordinator

    monkeypatch.setenv("SO101_TASK_ROOT", str(tmp_path_factory.mktemp("guard-root")))
    monkeypatch.setattr(ProbeCoordinator, "check", _local_guard_check)


def argv(root: Path, **changes):
    values = {
        "points": str(POINTS),
        "config": str(CONFIG),
        "batch_id": "batch-1",
        "worker_count": "1",
        "evidence_root": str(root),
        "broker_image": "so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1",
        "yolo_weights": "/models/yolo.pt",
        "yolo_weights_sha256": YOLO_SHA,
        "grounded_root": "/models/grounded",
        "grounded_manifest_sha256": GROUNDED_SHA,
        "run_mode": "dry_run",
    }
    values.update(changes)
    result = []
    for key, value in values.items():
        if key == "point_id":
            for item in value:
                result += ["--point-id", item]
        else:
            result += ["--" + key.replace("_", "-"), str(value)]
    return result


def adaptive_argv(root: Path, **changes):
    values = {
        "points": str(POINTS),
        "config": str(CONFIG),
        "adaptive_config": str(ADAPTIVE_CONFIG),
        "batch_id": "a001",
        "evidence_root": str(root),
        "broker_image": "so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1",
        "yolo_weights": "/models/yolo.pt",
        "yolo_weights_sha256": YOLO_SHA,
        "grounded_root": "/models/grounded",
        "grounded_manifest_sha256": GROUNDED_SHA,
        "run_mode": "dry_run",
    }
    values.update(changes)
    result = ["--adaptive-workers"]
    for key, value in values.items():
        if value is None:
            continue
        if key == "point_id":
            for item in value:
                result += ["--point-id", item]
        else:
            result += ["--" + key.replace("_", "-"), str(value)]
    return result


def verified(_spec):
    return {"source_commit": "a" * 40, "models_verified": True, "image_verified": True}


def _fixed_web_spec(tmp_path, monkeypatch, *, run_mode="dry_run"):
    from so101_demo.cli.mujoco_batch.request import prepare_batch
    from so101_demo.parallel_batch.resource_allocation.models import runtime_ipc_base

    root = _socket_fixture_root(tmp_path, "fw") / "batch"
    # Worker IPC uses the production short runtime namespace. The fixed Web
    # socket remains in the actual long durable batch root via pinned dirfd.
    ipc_base = runtime_ipc_base()
    batch_id = "fw-" + hashlib.sha256(str(tmp_path).encode()).hexdigest()[:12]
    monkeypatch.setenv("SO101_PARALLEL_IPC_BASE", str(ipc_base))
    values = {
        "SO101_FIXED_CONTROL_TOKEN": "9a" * 32,
        "SO101_FIXED_CONTROL_CAMPAIGN_ID": "campaign-a",
        "SO101_FIXED_CONTROL_EPOCH": "1",
        "SO101_FIXED_CONTROL_SOCKET": str(root / "control/control.sock"),
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    spec = prepare_batch(argv(
        root, batch_id=batch_id, worker_count="1",         point_id=("task_start",), run_mode=run_mode,
    ), provenance_verifier=verified)
    return spec, values


class _FixedWebProbe:
    def snapshot(self):
        from so101_demo.parallel_batch.resource_allocation.models import ResourceSnapshot
        return ResourceSnapshot(32, 64.0, 16.0)

    def ros_domain_in_use(self, _domain):
        return False

    def socket_in_use(self, _path):
        return False


def _cancel_fixed_cli(values, batch_id):
    import socket

    from so101_demo.parallel_batch.web_control import _bind_target

    unsigned = {
        "schema_version": 1, "command_id": "cli-cancel-1", "campaign_id": "campaign-a",
        "batch_id": batch_id, "coordinator_epoch": 1, "operation": "CANCEL_BATCH",
    }
    canonical = json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
    wire = {**unsigned, "control_token": values["SO101_FIXED_CONTROL_TOKEN"],
            "request_sha256": hashlib.sha256(canonical).hexdigest()}
    payload = json.dumps(wire, sort_keys=True, separators=(",", ":")).encode()
    path = Path(values["SO101_FIXED_CONTROL_SOCKET"])
    parent_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as peer:
            peer.settimeout(2)
            peer.connect(_bind_target(path, parent_fd))
            peer.sendall(len(payload).to_bytes(4, "big") + payload)
            peer.shutdown(socket.SHUT_WR)
            received = bytearray()
            while part := peer.recv(65536):
                received.extend(part)
        assert len(received) > 4 and int.from_bytes(received[:4], "big") == len(received) - 4
        return json.loads(received[4:])
    finally:
        os.close(parent_fd)


def summary(mode, statuses, *, cleanup=True, terminal=True):
    points = {point: PointStatus.UNRUN for point in statuses}
    validations = {}
    if mode is RunMode.EXECUTE:
        points = statuses
    else:
        validations = statuses
    return BatchSummary(
        mode,
        points,
        batch_terminal=terminal,
        validation_statuses=validations,
        batch_cleanup_complete=cleanup,
        terminal_reason="POINTS_COMPLETE" if terminal else None,
    )


class SimpleLease:
    batch_id = "batch-1"
    coordinator_epoch = 1
    worker_id = "worker-01"
    worker_generation = 1
    point_id = "task_start"
    attempt_id = "attempt-1"
    lease_generation = 1
    lease_issued_monotonic_s = 10.0
    lease_deadline_monotonic_s = 20.0


def _external_overlay_fixture(tmp_path):
    repository = tmp_path / "checkout"
    source = repository / "src/so101_demo_py/src"
    module_source = source / "cli/mujoco_parallel_batch.py"
    module_source.parent.mkdir(parents=True)
    module_source.write_text("approved = True\n", encoding="utf-8")
    build_root = tmp_path / "candidate/build"
    build_package = build_root / "so101_demo_py"
    build_package.mkdir(parents=True)
    metadata = build_package / "so101_demo_py.egg-info/entry_points.txt"
    metadata.parent.mkdir(parents=True)
    metadata.write_text(
        "[console_scripts]\n"
        "so101_parallel_batch = so101_demo.cli.mujoco_parallel_batch:main\n",
        encoding="utf-8",
    )
    install_root = tmp_path / "candidate/install"
    package_prefix = install_root / "so101_demo_py"
    module_import = (
        package_prefix
        / "lib/python3.12/site-packages/so101_demo/cli/mujoco_parallel_batch.py"
    )
    module_import.parent.mkdir(parents=True)
    module_import.write_bytes(module_source.read_bytes())
    console = package_prefix / "lib/so101_demo_py/so101_parallel_batch"
    console.parent.mkdir(parents=True)
    console.write_text(
        _canonical_console_wrapper().replace(
            "so101-demo-py'", "so101-demo-py==0.1.0'"
        ),
        encoding="utf-8",
    )
    support_prefix = install_root / "so101_mujoco_support"
    support_prefix.mkdir(parents=True)
    share = package_prefix / "share/so101_demo_py/config/mujoco"
    share.mkdir(parents=True)
    config = share / "parallel_batch_linux_cuda.yaml"
    points = share / "moveit_expert_validation_points.yaml"
    config.write_text("schema_version: 2\n", encoding="utf-8")
    points.write_text("schema_version: 1\n", encoding="utf-8")
    binding = tmp_path / "candidate/provenance-binding.json"
    binding.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "source_root": str(repository.resolve()),
                "source_commit": "a" * 40,
                "build_root": str(build_root.resolve()),
                "install_root": str(install_root.resolve()),
                "package_prefixes": {
                    "so101_demo_py": str(package_prefix.resolve()),
                    "so101_mujoco_support": str(support_prefix.resolve()),
                },
                "artifacts": {
                    "coordinator_console": {
                        "path": str(console.resolve()),
                        "sha256": hashlib.sha256(console.read_bytes()).hexdigest(),
                    },
                    "coordinator_module": {
                        "path": str(module_import.absolute()),
                        "sha256": hashlib.sha256(module_import.read_bytes()).hexdigest(),
                    },
                    "entry_points": {
                        "path": str(metadata.resolve()),
                        "sha256": hashlib.sha256(metadata.read_bytes()).hexdigest(),
                    },
                    "parallel_config": {
                        "path": str(config.resolve()),
                        "sha256": hashlib.sha256(config.read_bytes()).hexdigest(),
                    },
                    "point_catalog": {
                        "path": str(points.resolve()),
                        "sha256": hashlib.sha256(points.read_bytes()).hexdigest(),
                    },
                },
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return {
        "repository": repository,
        "module_source": module_source,
        "module_import": module_import,
        "console": console,
        "config": config,
        "points": points,
        "binding": binding,
        "package_prefix": package_prefix,
    }


def _canonical_console_wrapper():
    return """#!/usr/bin/python3
# EASY-INSTALL-ENTRY-SCRIPT: 'so101-demo-py','console_scripts','so101_parallel_batch'
import re
import sys

# for compatibility with easy_install; see #2198
__requires__ = 'so101-demo-py'

try:
    from importlib.metadata import distribution
except ImportError:
    try:
        from importlib_metadata import distribution
    except ImportError:
        from pkg_resources import load_entry_point


def importlib_load_entry_point(spec, group, name):
    dist_name, _, _ = spec.partition('==')
    matches = (
        entry_point
        for entry_point in distribution(dist_name).entry_points
        if entry_point.group == group and entry_point.name == name
    )
    return next(matches).load()


globals().setdefault('load_entry_point', importlib_load_entry_point)


if __name__ == '__main__':
    sys.argv[0] = re.sub(r'(-script\\.pyw?|\\.exe)?$', '', sys.argv[0])
    sys.exit(load_entry_point('so101-demo-py', 'console_scripts', 'so101_parallel_batch')())
"""
