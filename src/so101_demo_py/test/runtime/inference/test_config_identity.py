"""Catch model operations becoming calibration identity or unpinned inputs."""

import copy
import hashlib
import importlib
import json

import pytest


def config_module():
    return importlib.import_module("so101_demo.runtime.inference.config")


def file_ref(path, content):
    path.write_bytes(content)
    return {"path": str(path), "sha256": hashlib.sha256(content).hexdigest()}


def campaign_fixture(tmp_path):
    controlled = file_ref(tmp_path / "controlled.json", b'{"sampling_hz":10,"r6":"current"}\n')
    head_weights = file_ref(tmp_path / "head.pt", b"head-weights")
    teacher_weights = file_ref(tmp_path / "teacher.pt", b"teacher-weights")
    image = {"digest": "sha256:" + "a" * 64, "package_source_sha256": "b" * 64,
             "install_sha256": "c" * 64}
    def service(model, weights):
        return {"image": copy.deepcopy(image), "model": {
            "model_id": model, "weights": weights, "classes": {"0": "plastic_cup"},
            "score_threshold": 0.25}, "instances": 3, "torch_threads": 1,
            "torch_interop_threads": 1, "max_inflight_requests": 8,
            "max_frame_bytes": 2**20, "max_image_height": 480, "max_image_width": 640,
            "queue_timeout_s": 0.5, "inference_timeout_s": 0.5}
    return {"schema_version": 1, "kind": "ACT_CONTAINER_CAMPAIGN", "evidence_root": str(tmp_path),
            "controlled_runtime": controlled, "head_service": service("head-model", head_weights),
            "teacher_service": service("teacher-model", teacher_weights),
            "shard_image": image | {"digest": "sha256:" + "d" * 64},
            "gpu_uuid": "GPU-selected", "qualification_contract": None}


def write_config(tmp_path, document):
    path = tmp_path / "campaign.json"
    path.write_text(json.dumps(document, sort_keys=True), encoding="utf-8")
    return path


def test_teacher_operations_change_campaign_hash_not_controlled_runtime(tmp_path):
    document = campaign_fixture(tmp_path)
    path = write_config(tmp_path, document)
    original = config_module().load_campaign_config(path)
    runtime_hash = config_module().calibration_runtime_hash(tmp_path / "controlled.json")
    original_bytes = path.read_bytes()
    document["teacher_service"]["model"].update(model_id="replacement-model", score_threshold=0.75,
        weights=file_ref(tmp_path / "replacement.pt", b"replacement-weights"))
    document["teacher_service"]["instances"] = 5
    changed = config_module().load_campaign_config(write_config(tmp_path, document))
    assert changed["teacher_service"]["instances"] == 5
    assert changed["head_service"] == original["head_service"]
    assert changed["teacher_service"]["image"] == original["teacher_service"]["image"]
    assert config_module().calibration_runtime_hash(tmp_path / "controlled.json") == runtime_hash
    assert hashlib.sha256(path.read_bytes()).digest() != hashlib.sha256(original_bytes).digest()
    (tmp_path / "controlled.json").write_bytes(b'{"sampling_hz":10,"r6":"changed"}\n')
    assert config_module().calibration_runtime_hash(tmp_path / "controlled.json") != runtime_hash
    with pytest.raises(ValueError, match="CAMPAIGN_CONFIG_INVALID"):
        config_module().load_campaign_config(path)


@pytest.mark.parametrize("mutation", ["extra", "version", "relative_root", "head_limit", "zero_instances",
    "bool_instances", "threshold_nan", "threshold_range", "image_mismatch", "bad_class", "cpu", "hash"])
def test_campaign_rejects_invalid_or_unpinned_config(tmp_path, mutation):
    document = campaign_fixture(tmp_path)
    service = document["teacher_service"]
    if mutation == "extra": document["allow_legacy"] = True
    elif mutation == "version": document["schema_version"] = 2
    elif mutation == "relative_root": document["evidence_root"] = "relative"
    elif mutation == "head_limit": document["head_service"]["max_inflight_requests"] = 16
    elif mutation == "zero_instances": service["instances"] = 0
    elif mutation == "bool_instances": service["instances"] = True
    elif mutation == "threshold_nan": service["model"]["score_threshold"] = float("nan")
    elif mutation == "threshold_range": service["model"]["score_threshold"] = 1.1
    elif mutation == "image_mismatch": service["image"]["digest"] = "sha256:" + "e" * 64
    elif mutation == "bad_class": service["model"]["classes"] = {"-1": "cup"}
    elif mutation == "cpu": service["allow_cpu_fallback"] = True
    elif mutation == "hash": service["model"]["weights"]["sha256"] = "f" * 64
    with pytest.raises(ValueError, match="CAMPAIGN_CONFIG_INVALID"):
        config_module().load_campaign_config(write_config(tmp_path, document))


def test_measurement_does_not_load_unused_teacher_weights(tmp_path):
    document = campaign_fixture(tmp_path)
    document["teacher_service"]["model"]["weights"] = {
        "path": str(tmp_path / "not-loaded.pt"), "sha256": "e" * 64}
    path = write_config(tmp_path, document)
    loaded = config_module().load_campaign_config(path, roles=("head",))
    assert loaded["teacher_service"]["model"]["weights"]["path"].endswith("not-loaded.pt")
    with pytest.raises(ValueError, match="CAMPAIGN_CONFIG_INVALID"):
        config_module().load_campaign_config(path)


def test_path_symlinks_and_duplicate_keys_are_rejected(tmp_path):
    document = campaign_fixture(tmp_path)
    link = tmp_path / "alias"
    link.symlink_to(tmp_path, target_is_directory=True)
    document["controlled_runtime"]["path"] = str(link / "controlled.json")
    with pytest.raises(ValueError, match="CAMPAIGN_CONFIG_INVALID"):
        config_module().load_campaign_config(write_config(tmp_path, document))
    path = tmp_path / "duplicate.json"
    path.write_text('{"schema_version":1,"schema_version":1}')
    with pytest.raises(ValueError, match="CAMPAIGN_CONFIG_INVALID"):
        config_module().load_campaign_config(path)


def test_published_campaign_schema_rejects_authority_and_old_format(tmp_path):
    import jsonschema
    from paths import PACKAGE_ROOT
    schema = json.loads((PACKAGE_ROOT / "config/act/campaign-runtime-schema.json").read_text())
    document = campaign_fixture(tmp_path)
    jsonschema.validate(document, schema)
    for invalid in (document | {"schema_version": 2}, document | {"lease": {}}):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(invalid, schema)
