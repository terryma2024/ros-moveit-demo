"""Declared deployment identities must name real image/model bytes, never policy aliases."""

import hashlib
import json

import pytest

from so101_demo.cli import act_diagnostic_episode as cli


def inputs(tmp_path):
    scene = tmp_path / "scene.xml"
    scene.write_bytes(b"fixture scene")
    weights = tmp_path / "best.pt"
    weights.write_bytes(b"fixture weights")
    grounded = tmp_path / "grounded"
    grounded.mkdir()
    manifest = grounded / "manifest.json"
    manifest.write_bytes(b'{"fixture":true}')
    digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    frozen = tmp_path / "inputs-manifest.json"
    frozen.write_text(json.dumps({"inputs_sha256": "a" * 64,
        "runtime_policy": {"sha256": "b" * 64},
        "roles": {"scene_model": {"sha256": digest(scene)}}}))
    return {"inputs_manifest": str(frozen), "inputs_manifest_sha256": digest(frozen),
        "expected_inputs_sha256": "a" * 64,
        "scene_model": str(scene), "yolo_weights": str(weights),
        "yolo_weights_sha256": digest(weights), "grounded_root": str(grounded),
        "grounded_manifest_sha256": digest(manifest), "broker_image": cli.BROKER_IMAGE}


def test_nonhead_provenance_reads_actual_image_and_model_hashes(tmp_path, monkeypatch):
    from so101_demo.cli import parallel_perception_broker
    values = inputs(tmp_path)
    calls = []
    def image_record(image):
        calls.append(image)
        return {"image_id": "sha256:010dca70ce3ce995367793642c2e5515718986253cecacc032e9f7f7ec6c5457"}
    monkeypatch.setattr(parallel_perception_broker, "image_record", image_record)
    record = cli._nonhead_provenance(values)
    assert calls == [cli.BROKER_IMAGE]
    assert record["image_id"] != "sha256:" + "b" * 64
    assert record["yolo_weights_sha256"] == values["yolo_weights_sha256"]
    assert record["grounded_manifest_sha256"] == values["grounded_manifest_sha256"]
    assert record["scene_model_sha256"] != record["yolo_weights_sha256"]


@pytest.mark.parametrize("changed", ["weights", "grounded", "image"])
def test_actual_deployment_drift_refuses(tmp_path, monkeypatch, changed):
    from pathlib import Path
    from so101_demo.cli import parallel_perception_broker
    values = inputs(tmp_path)
    if changed == "weights":
        Path(values["yolo_weights"]).write_bytes(b"different weights")
    elif changed == "grounded":
        (Path(values["grounded_root"]) / "manifest.json").write_bytes(b"{}")
    monkeypatch.setattr(parallel_perception_broker, "image_record", lambda image:
        {"image_id": "sha256:" + "c" * 64 if changed == "image" else
         "sha256:010dca70ce3ce995367793642c2e5515718986253cecacc032e9f7f7ec6c5457"})
    with pytest.raises(ValueError, match="NONHEAD_PROVENANCE"):
        cli._nonhead_provenance(values)
