"""Task 8P1: the ACT collection config freezes W8 and recorder backpressure."""

import hashlib
import json
from pathlib import Path

import pytest
import yaml

from so101_demo.act.collection_config import load_collection_config

PACKAGE = Path(__file__).resolve().parents[1]
CONFIG = PACKAGE / "config/act/parallel_collection_v3.yaml"
PUBLIC = PACKAGE / "config/mujoco/parallel_batch_v3.yaml"


def _package_share(tmp_path):
    """A package share whose config/ mirrors the repository config directory."""

    share = tmp_path / "share/so101_demo_py"
    (share / "config/mujoco").mkdir(parents=True)
    (share / "config/act").mkdir(parents=True)
    (share / "config/mujoco/parallel_batch_v3.yaml").write_bytes(PUBLIC.read_bytes())
    (share / "config/act/parallel_collection_v3.yaml").write_bytes(CONFIG.read_bytes())
    return share


def test_collection_config_freezes_w8_and_recorder_backpressure(tmp_path):
    share = _package_share(tmp_path)
    value = load_collection_config(share / "config/act/parallel_collection_v3.yaml",
                                   package_share=share)
    assert value["qualification"] == {
        "functional_worker_counts": [1, 2], "load_worker_count": 8,
        "formal_worker_count": 8, "max_wave_size": 20,
        "no_auto_degrade": True,
    }
    assert value["recorder"] == {
        "sample_rate_hz": 10, "queue_capacity_samples": 16,
        "queue_high_watermark_samples": 12,
        "queue_recovery_watermark_samples": 8,
        "queue_high_watermark_hold_s": 0.2, "lossless": True,
    }
    assert value["recovery"] == {
        "business_retry_count": 0, "max_infra_attempts_per_scenario": 2,
        "resume_requires_identical_business_hashes": True,
    }
    assert value["telemetry"] == {"period_s": 1.0}


def test_loader_binds_the_public_runtime_bytes_not_a_reparse(tmp_path):
    share = _package_share(tmp_path)
    value = load_collection_config(share / "config/act/parallel_collection_v3.yaml",
                                   package_share=share)
    expected = hashlib.sha256((share / value["parallel_runtime"]["path"]).read_bytes()).hexdigest()
    assert value["parallel_runtime"]["sha256"] == expected


@pytest.mark.parametrize("mutation", [
    "absolute_path", "parent_traversal", "symlink", "outside_share", "wrong_public_hash",
])
def test_loader_rejects_unresolvable_parallel_runtime(tmp_path, mutation):
    share = _package_share(tmp_path)
    path = share / "config/act/parallel_collection_v3.yaml"
    document = yaml.safe_load(path.read_bytes())
    if mutation == "absolute_path":
        document["parallel_runtime"]["path"] = "/etc/passwd"
    elif mutation == "parent_traversal":
        document["parallel_runtime"]["path"] = "config/../../outside.yaml"
    elif mutation == "symlink":
        target = tmp_path / "elsewhere.yaml"
        target.write_bytes(PUBLIC.read_bytes())
        link = share / "config/mujoco/parallel_batch_v3.yaml"
        link.unlink()
        link.symlink_to(target)
    elif mutation == "outside_share":
        document["parallel_runtime"]["path"] = "config/act/parallel_collection_v3.yaml"
    else:
        document["parallel_runtime"]["sha256"] = "0" * 64
    path.write_text(yaml.safe_dump(document, sort_keys=False))
    with pytest.raises(ValueError):
        load_collection_config(path, package_share=share)


@pytest.mark.parametrize("mutation", [
    "cpu_device", "cpu_fallback_true", "fallback_list", "watermark_order", "extra_field",
])
def test_loader_rejects_cuda_and_recorder_violations(tmp_path, mutation):
    share = _package_share(tmp_path)
    path = share / "config/act/parallel_collection_v3.yaml"
    document = yaml.safe_load(path.read_bytes())
    if mutation == "cpu_device":
        document["parallel_runtime"]["device"] = "cpu"
    elif mutation == "cpu_fallback_true":
        document["parallel_runtime"]["allow_cpu_fallback"] = True
    elif mutation == "fallback_list":
        document["parallel_runtime"]["fallback_devices"] = ["cpu"]
    elif mutation == "watermark_order":
        document["recorder"]["queue_recovery_watermark_samples"] = 14
    else:
        document["unexpected"] = 1
    path.write_text(yaml.safe_dump(document, sort_keys=False))
    with pytest.raises(ValueError):
        load_collection_config(path, package_share=share)


def test_frozen_yaml_matches_the_approved_design():
    document = yaml.safe_load(CONFIG.read_bytes())
    assert document["schema_version"] == 1
    assert document["kind"] == "act_parallel_collection"
    assert document["parallel_runtime"]["path"] == "config/mujoco/parallel_batch_v3.yaml"
    assert document["parallel_runtime"]["sha256"] == \
        hashlib.sha256(PUBLIC.read_bytes()).hexdigest()
    schema = json.loads((PACKAGE / "config/act/parallel-collection-v3-schema.json").read_text())
    assert schema["properties"]["kind"]["const"] == "act_parallel_collection"
