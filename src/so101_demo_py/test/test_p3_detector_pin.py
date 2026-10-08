"""CP-3460: the broker's detector source is pinned to the image's baked tree, with its hash in the container label and the run record.

The freeze's `adapters/perception/yolo_seg.py` passes the RGB frame to Ultralytics as BGR (commit 828af7c91, 2026-09-25); the image's
09-24 file passes it as it is. On the same weights and the same inputs the corrected detector returns a second candidate (0.36) next
to the cup (0.97) and the Worker, which wants exactly one, answers BROKER_CANDIDATE_AMBIGUOUS. CP-3454, CP-3455 and the calibrated
limits were made with the baked behaviour, so the broker keeps it: the freeze's package is mounted for contracts, IPC and runtime and
the baked `yolo_seg.py` is mounted over it, read-only, from a durable copy whose sha256 is fixed in the code.
"""

import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

import so101_demo
from so101_demo.cli import parallel_perception_broker as broker_cli

from test_p3_role_provenance import PACKAGE, _container_kwargs
from test_parallel_batch_cli import local_start_guard  # noqa: F401  (autouse: the offline start-guard seam)

BAKED = b"# the baked yolo_seg.py\nCALL = 'predict(source=source)'\n"


def make_pin(tmp_path, monkeypatch, *, content=BAKED, extra=None):
    root = tmp_path / "deps" / "broker-detector-baked-3624dac7"
    (root / "perception").mkdir(parents=True)
    (root / "perception" / "yolo_seg.py").write_bytes(content)
    (root / "perception" / "__init__.py").write_text("")
    files = {name: hashlib.sha256((root / "perception" / name).read_bytes()).hexdigest() for name in ("__init__.py", "yolo_seg.py")}
    manifest = {"kind": "BROKER_DETECTOR_PIN", "schema_version": 1, "image_source_sha256": broker_cli.PINNED_IMAGE_SOURCE_SHA256,
                "mounted_file": "yolo_seg.py", "mounted_file_sha256": files["yolo_seg.py"], "files": files, **(extra or {})}
    (root / "manifest.json").write_text(json.dumps(manifest))
    monkeypatch.setattr(broker_cli, "PINNED_DETECTOR_SHA256", hashlib.sha256(BAKED).hexdigest())
    return root


# ---- the hash pin ----------------------------------------------------------------------------------------------------------------

def test_the_constants_are_the_baked_files_hash_and_the_images_source_hash():
    assert broker_cli.PINNED_IMAGE_SOURCE_SHA256 == "3624dac7c70603039f9337f9f5175f9bf8b427656bf4bf09ed6cd490308d84a2"
    assert broker_cli.PINNED_DETECTOR_SHA256 == "72d4e1fb3cbd9b0666d28f95bfc440e3756a4005e7b61532625ed1be52e4ce56"
    assert broker_cli.PINNED_DETECTOR_SHA256 != hashlib.sha256(
        (Path(so101_demo.__file__).parent / "adapters" / "perception" / "yolo_seg.py").read_bytes()).hexdigest(), \
        "the freeze's own yolo_seg.py is not the pinned one"


def test_a_pin_that_matches_returns_the_baked_file(tmp_path, monkeypatch):
    root = make_pin(tmp_path, monkeypatch)
    source = broker_cli.pinned_detector_source({"SO101_BROKER_DETECTOR_PIN_ROOT": str(root)})
    assert source == root / "perception" / "yolo_seg.py"


@pytest.mark.parametrize("fault,code", [
    ("tampered_file", "DETECTOR_PIN_MISMATCH"), ("manifest_hash", "DETECTOR_PIN_MISMATCH"), ("other_image", "DETECTOR_PIN_MISMATCH"),
    ("other_file_changed", "DETECTOR_PIN_MISMATCH"), ("manifest_missing", "DETECTOR_PIN_MISSING"), ("file_missing", "DETECTOR_PIN_MISSING"),
    ("symlink", "DETECTOR_PIN_MISMATCH"), ("garbage_manifest", "DETECTOR_PIN_MISMATCH")])
def test_a_pin_that_does_not_match_fails_closed(tmp_path, monkeypatch, fault, code):
    root = make_pin(tmp_path, monkeypatch)
    target = root / "perception" / "yolo_seg.py"
    manifest = root / "manifest.json"
    if fault == "tampered_file":
        target.write_bytes(BAKED + b"# edited\n")
    if fault == "manifest_hash":
        document = json.loads(manifest.read_text())
        document["mounted_file_sha256"] = "0" * 64
        manifest.write_text(json.dumps(document))
    if fault == "other_image":
        document = json.loads(manifest.read_text())
        document["image_source_sha256"] = "1" * 64
        manifest.write_text(json.dumps(document))
    if fault == "other_file_changed":
        (root / "perception" / "__init__.py").write_text("# edited")
    if fault == "manifest_missing":
        manifest.unlink()
    if fault == "file_missing":
        target.unlink()
    if fault == "symlink":
        target.unlink()
        (tmp_path / "elsewhere.py").write_bytes(BAKED)
        target.symlink_to(tmp_path / "elsewhere.py")
    if fault == "garbage_manifest":
        manifest.write_text("not json")
    with pytest.raises(ValueError, match=code):
        broker_cli.pinned_detector_source({"SO101_BROKER_DETECTOR_PIN_ROOT": str(root)})


def test_the_pin_root_comes_from_the_environment_or_from_the_freezes_evidence_root(tmp_path):
    freeze = tmp_path / "experiments" / "nonhead-installed-freeze.X"
    assert broker_cli.detector_pin_root({"SO101_QUALIFIED_FREEZE": str(freeze)}) == tmp_path / "deps" / "broker-detector-baked-3624dac7"
    assert broker_cli.detector_pin_root({"SO101_QUALIFIED_FREEZE": str(freeze), "SO101_BROKER_DETECTOR_PIN_ROOT": "/x"}) == Path("/x")
    assert broker_cli.detector_pin_root({}) is None
    assert broker_cli.pinned_detector_source({}) is None, "outside a qualified run (development, unit tests) nothing is pinned"


def test_a_qualified_run_without_the_pin_stops(tmp_path):
    freeze = tmp_path / "experiments" / "nonhead-installed-freeze.X"
    with pytest.raises(ValueError, match="DETECTOR_PIN_MISSING"):
        broker_cli.pinned_detector_source({"SO101_QUALIFIED_FREEZE": str(freeze)})


# ---- the mount composition --------------------------------------------------------------------------------------------------------

def test_the_container_mounts_the_baked_detector_over_the_freezes_package_read_only_and_labels_its_hash(tmp_path, monkeypatch):
    root = make_pin(tmp_path, monkeypatch)
    pin = broker_cli.pinned_detector_source({"SO101_BROKER_DETECTOR_PIN_ROOT": str(root)})
    batch, kwargs = _container_kwargs(tmp_path)
    argv = broker_cli.container_run_argv(batch, source_package=PACKAGE, detector_pin=pin, **kwargs)
    package_mount = f"{PACKAGE}:{broker_cli.IMAGE_PACKAGE_PATH}:ro"
    detector_mount = f"{pin}:{broker_cli.IMAGE_DETECTOR_PATH}:ro"
    assert broker_cli.IMAGE_DETECTOR_PATH == broker_cli.IMAGE_PACKAGE_PATH + "/adapters/perception/yolo_seg.py"
    assert argv[argv.index(detector_mount) - 1] == "--volume"
    assert argv.index(package_mount) < argv.index(detector_mount) < argv.index(kwargs["image_id"]), "package first, detector over it, then the image"
    assert f"com.so101.detector-sha256={hashlib.sha256(BAKED).hexdigest()}" in argv
    assert f"com.so101.source-sha256={broker_cli.source_hash(PACKAGE)}" in argv


def test_a_detector_pin_without_the_package_or_with_a_wrong_file_is_refused(tmp_path, monkeypatch):
    root = make_pin(tmp_path, monkeypatch)
    pin = root / "perception" / "yolo_seg.py"
    batch, kwargs = _container_kwargs(tmp_path)
    with pytest.raises(ValueError, match="DETECTOR_PIN_REQUIRES_PACKAGE"):
        broker_cli.container_run_argv(batch, detector_pin=pin, **kwargs)
    pin.parent.chmod(0o755)
    pin.write_bytes(BAKED + b"x")
    with pytest.raises(ValueError, match="DETECTOR_PIN_MISMATCH"):
        broker_cli.container_run_argv(batch, source_package=PACKAGE, detector_pin=pin, **kwargs)


def test_without_a_detector_pin_the_argv_has_no_detector_mount(tmp_path):
    batch, kwargs = _container_kwargs(tmp_path)
    argv = broker_cli.container_run_argv(batch, source_package=PACKAGE, **kwargs)
    assert not any(broker_cli.IMAGE_DETECTOR_PATH in item or item.startswith("com.so101.detector-sha256") for item in argv)


# ---- the run record -----------------------------------------------------------------------------------------------------------------

def test_the_composition_pins_the_detector_in_a_qualified_run_and_records_it(tmp_path, monkeypatch):
    from test_parallel_batch_cli import argv as cli_argv, verified
    from so101_demo.cli.mujoco_parallel_batch import ProductionBatchComposition, prepare_batch
    from so101_demo.parallel_batch.resources import ResourceSnapshot, runtime_ipc_base

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
    monkeypatch.setattr(broker_cli, "container_run_argv", lambda root, **kw: captured.update(kw) or ("docker", "run", "broker"))
    supervisor = Supervisor()
    composition = ProductionBatchComposition(spec, resource_probe=Probe(), claim_root=tmp_path / "claims", supervisor=supervisor)
    try:
        composition._start_broker()
        assert captured["detector_pin"] is None, "outside a qualified run nothing is pinned"
        assert not (spec.request.evidence_root / "broker-source-pin.json").exists()
        supervisor.started.clear()
        root = make_pin(tmp_path, monkeypatch)
        monkeypatch.setenv("SO101_BROKER_DETECTOR_PIN_ROOT", str(root))
        composition._start_broker()
        assert captured["detector_pin"] == root / "perception" / "yolo_seg.py" and supervisor.started
        document = json.loads((spec.request.evidence_root / "broker-source-pin.json").read_text())
        assert document["detector_sha256"] == hashlib.sha256(BAKED).hexdigest()
        assert document["detector_path"] == str(root / "perception" / "yolo_seg.py")
        assert document["package_root"] == str(PACKAGE) and document["package_source_sha256"] == broker_cli.source_hash(PACKAGE)
        assert document["image_source_sha256"] == broker_cli.PINNED_IMAGE_SOURCE_SHA256 and document["manifest_sha256"]
        # a pin that no longer matches stops the broker before any process
        (root / "perception").chmod(0o755)
        (root / "perception" / "yolo_seg.py").write_bytes(BAKED + b"# edited")
        supervisor.started.clear()
        with pytest.raises(ValueError, match="DETECTOR_PIN_MISMATCH"):
            composition._start_broker()
        assert supervisor.started == []
    finally:
        composition._release_partial()
        assert composition._release_runtime_ipc_root() is True
