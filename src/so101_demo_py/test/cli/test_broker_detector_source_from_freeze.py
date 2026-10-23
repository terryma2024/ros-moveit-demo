"""The broker runs the freeze's own detector; the pin of the image's baked `yolo_seg.py` is gone.

An earlier pin mounted the image's 09-24 `yolo_seg.py` over the freeze's package because the corrected detector (commit 828af7c91: the RGB
frame reaches Ultralytics as BGR) returns a second candidate, the red landing ring (0.36), next to the cup (0.97) and the Worker wanted
exactly one. Cup geometry filtering in `CupCandidateLocalizer` (tests in `test_parallel_ros_runtime_*.py`) keeps the candidate that localizes as a cup and
spans >= 0.05 m in z, so the pin is no longer needed. What stays: the freeze's package is mounted for contracts, IPC and runtime, its
source hash is the container label, and the run records the hash of the detector it contains.
"""

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from so101_demo.cli import parallel_perception_broker as broker_cli
from parallel_batch_cli_support import (
    local_start_guard,  # noqa: F401  (autouse: the offline start-guard seam)
)
from test_child_role_code_provenance import PACKAGE, _container_kwargs


def test_the_detector_pin_machinery_is_gone():
    for name in ("pinned_detector_source", "detector_pin_root", "detector_pin_record", "PINNED_DETECTOR_SHA256",
                 "PINNED_IMAGE_SOURCE_SHA256", "IMAGE_DETECTOR_PATH", "DETECTOR_PIN_NAME"):
        assert not hasattr(broker_cli, name), name
    with pytest.raises(TypeError):
        broker_cli.container_run_argv(Path("/x"), detector_pin=Path("/y"))


def test_the_container_mounts_only_the_freezes_package_and_labels_its_source_hash(tmp_path):
    batch, kwargs = _container_kwargs(tmp_path)
    argv = broker_cli.container_run_argv(batch, source_package=PACKAGE, **kwargs)
    package_mount = f"{PACKAGE}:{broker_cli.IMAGE_PACKAGE_PATH}:ro"
    assert argv[argv.index(package_mount) - 1] == "--volume"
    assert f"com.so101.source-sha256={broker_cli.source_hash(PACKAGE)}" in argv
    assert not any("yolo_seg" in item or item.startswith("com.so101.detector-sha256") for item in argv)
    assert sum(1 for item in argv if item.endswith(":ro") and broker_cli.IMAGE_PACKAGE_PATH in item) == 1, "one mount over the package"


def test_the_source_record_names_the_detector_of_the_package_it_mounts():
    record = broker_cli.broker_source_record(PACKAGE)
    detector = PACKAGE / "adapters" / "perception" / "yolo_seg.py"
    assert record == {"kind": "ACT_BROKER_SOURCE_PIN", "schema_version": 2, "package_root": str(PACKAGE),
                      "package_source_sha256": broker_cli.source_hash(PACKAGE), "detector_path": str(detector),
                      "detector_sha256": hashlib.sha256(detector.read_bytes()).hexdigest(), "detector_source": "freeze"}


def test_the_freezes_detector_hands_the_frame_to_ultralytics_as_bgr():
    source = (PACKAGE / "adapters" / "perception" / "yolo_seg.py").read_text()
    assert "[:, :, ::-1]" in source or "[..., ::-1]" in source, "the BGR reversal of 828af7c91 is in the detector the broker runs"


def test_the_composition_records_the_freezes_detector_in_a_qualified_run_and_nothing_outside_one(tmp_path, monkeypatch):
    from so101_demo.cli.mujoco_batch.composition import ProductionBatchComposition
    from so101_demo.cli.mujoco_batch.request import prepare_batch
    from so101_demo.parallel_batch.resource_allocation.models import (
        ResourceSnapshot,
        runtime_ipc_base,
    )
    from parallel_batch_cli_support import argv as cli_argv
    from parallel_batch_cli_support import verified

    class Probe:
        def snapshot(self):
            return ResourceSnapshot(32, 64.0, 16.0)

        def ros_domain_in_use(self, _domain):
            return False

        def socket_in_use(self, _path):
            return False

    class Supervisor:
        def __init__(self):
            self.started = []

        def start(self, role, command):
            self.started.append((role, tuple(command)))
            return SimpleNamespace(role=role)

    batch_id = "p4-detector-pin"
    monkeypatch.setenv("SO101_PARALLEL_IPC_BASE", str(runtime_ipc_base()))
    record = {**verified({}), "image_id": "sha256:" + "b" * 64}
    spec = prepare_batch(cli_argv(tmp_path / "batch", batch_id=batch_id, worker_count="1", point_id=("task_start",), run_mode="plan_only"),
                         provenance_verifier=lambda _value: record)
    captured = {}
    monkeypatch.setattr(broker_cli, "image_record", lambda _image: {"image_id": record["image_id"]})
    monkeypatch.setattr(broker_cli, "gpu_groups", lambda: [44])
    monkeypatch.setattr(broker_cli, "qualified_package_root", lambda environ=None: PACKAGE)
    monkeypatch.setattr(broker_cli, "container_run_argv", lambda root, **kw: captured.update(kw) or ("docker", "run", "broker"))
    supervisor = Supervisor()
    composition = ProductionBatchComposition(spec, resource_probe=Probe(), claim_root=tmp_path / "claims", supervisor=supervisor)
    try:
        monkeypatch.delenv("SO101_QUALIFIED_FREEZE", raising=False)
        composition._start_broker()
        assert "detector_pin" not in captured and supervisor.started
        assert not (spec.request.evidence_root / "broker-source-pin.json").exists(), "outside a qualified run nothing is recorded"
        supervisor.started.clear()
        monkeypatch.setenv("SO101_QUALIFIED_FREEZE", str(tmp_path / "freeze"))
        composition._start_broker()
        assert supervisor.started
        document = json.loads((spec.request.evidence_root / "broker-source-pin.json").read_text())
        assert document == broker_cli.broker_source_record(PACKAGE)
        assert document["detector_sha256"] == hashlib.sha256(
            (PACKAGE / "adapters" / "perception" / "yolo_seg.py").read_bytes()).hexdigest()
    finally:
        composition._release_partial()
        assert composition._release_runtime_ipc_root() is True
