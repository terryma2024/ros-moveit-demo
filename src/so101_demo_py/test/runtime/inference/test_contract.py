"""Catch authority leakage, malformed candidates and misleading service readiness."""

import copy
import importlib

import pytest


def request_document():
    return {"schema_version": 1, "kind": "inference_request", "request_id": "unique-r",
            "image": {"format": "RGB8", "byte_length": 18, "shape": [2, 3, 3],
                      "source_stamp_ns": 7, "source_frame_id": "head"},
            "query_class_id": "plastic_cup", "deadline_monotonic_ns": 1000}


def response_document():
    return {"schema_version": 1, "kind": "inference_response", "request_id": "unique-r",
            "service_generation": "g1", "source_stamp_ns": 7, "source_frame_id": "head",
            "outcome": "DETECTED", "reason": "", "timing": {
                "received_monotonic_ns": 10, "queued_monotonic_ns": 11,
                "started_monotonic_ns": 12, "completed_monotonic_ns": 13},
            "batch": {"model_id": "cup-model", "weights_sha256": "a" * 64,
                      "runtime_device": "cuda", "inference_latency_ms": 0.1,
                      "shape": [2, 3, 3], "source_stamp_ns": 7, "source_frame_id": "head",
                      "candidates": [{"instance_id": "cup-0", "class_id": "plastic_cup",
                                      "confidence": 0.9, "bbox_xyxy": [0, 0, 3, 2],
                                      "segmentation_quality": None,
                                      "mask_rle": {"shape": [2, 3], "counts": [0, 2, 4]}}]}}


def contract():
    return importlib.import_module("so101_demo.runtime.inference.contract")


def test_valid_request_has_no_authority_or_transport_files():
    assert contract().validate_inference_request(request_document()) == request_document()


@pytest.mark.parametrize("change", [
    {"kind": "broker_call"}, {"schema_version": 2}, {"schema_version": True},
    {"lease": {}}, {"token": "secret"}, {"worker_id": "w00"},
    {"start_identity": {}}, {"deadline_monotonic_ns": 0},
    {"deadline_monotonic_ns": True}, {"query_class_id": ""}, {"request_id": ""},
])
def test_request_rejects_old_contract_and_bad_identity(change):
    document = request_document() | change
    with pytest.raises(ValueError, match="INFERENCE_REQUEST_INVALID"):
        contract().validate_inference_request(document)


@pytest.mark.parametrize("change", [
    {"path": "/tmp/rgb.npy"}, {"sha256": "a" * 64}, {"format": "BGR8"},
    {"shape": [0, 3, 3]}, {"shape": [2, 3, 4]}, {"shape": [True, 3, 3]},
    {"byte_length": 17}, {"source_stamp_ns": 0}, {"source_frame_id": ""},
])
def test_request_rejects_bad_image_metadata(change):
    document = request_document()
    document["image"].update(change)
    with pytest.raises(ValueError, match="INFERENCE_REQUEST_INVALID"):
        contract().validate_inference_request(document)


def test_detected_response_requires_lossless_valid_candidates():
    assert contract().validate_inference_response(response_document()) == response_document()


@pytest.mark.parametrize("mutation", [
    "empty", "mask_missing", "mask_total", "negative_run", "empty_mask", "mask_shape",
    "bbox", "confidence_nan", "confidence_bool", "quality", "duplicate", "source",
    "cpu", "latency", "old_outcome", "unknown_field", "timing_reverse", "timing_gap",
])
def test_detected_response_rejects_invalid_candidates_and_provenance(mutation):
    document = response_document()
    batch = document["batch"]
    candidate = batch["candidates"][0]
    if mutation == "empty": batch["candidates"] = []
    elif mutation == "mask_missing": del candidate["mask_rle"]
    elif mutation == "mask_total": candidate["mask_rle"]["counts"] = [0, 2, 3]
    elif mutation == "negative_run": candidate["mask_rle"]["counts"] = [0, -1, 7]
    elif mutation == "empty_mask": candidate["mask_rle"]["counts"] = [6]
    elif mutation == "mask_shape": candidate["mask_rle"]["shape"] = [3, 2]
    elif mutation == "bbox": candidate["bbox_xyxy"] = [0, 0, 4, 2]
    elif mutation == "confidence_nan": candidate["confidence"] = float("nan")
    elif mutation == "confidence_bool": candidate["confidence"] = True
    elif mutation == "quality": candidate["segmentation_quality"] = 1.1
    elif mutation == "duplicate": batch["candidates"].append(copy.deepcopy(candidate))
    elif mutation == "source": batch["source_stamp_ns"] = 8
    elif mutation == "cpu": batch["runtime_device"] = "cpu"
    elif mutation == "latency": batch["inference_latency_ms"] = -1
    elif mutation == "old_outcome": document["outcome"] = "QUALIFIED"
    elif mutation == "unknown_field": document["accepted_total"] = 1
    elif mutation == "timing_reverse": document["timing"]["started_monotonic_ns"] = 14
    elif mutation == "timing_gap": document["timing"]["queued_monotonic_ns"] = None
    with pytest.raises(ValueError, match="INFERENCE_RESPONSE_INVALID"):
        contract().validate_inference_response(document)


@pytest.mark.parametrize("outcome", ["NOT_DETECTED", "INPUT_INVALID", "QUEUE_FULL",
    "QUEUE_TIMEOUT", "INFERENCE_TIMEOUT", "MODEL_ERROR", "INFRA_ERROR"])
def test_failure_response_cannot_carry_success_batch(outcome):
    document = response_document() | {"outcome": outcome, "reason": outcome}
    with pytest.raises(ValueError, match="INFERENCE_RESPONSE_INVALID"):
        contract().validate_inference_response(document)
    document["batch"] = None
    assert contract().validate_inference_response(document)["outcome"] == outcome


@pytest.mark.parametrize("kind", ["service_ready", "service_health"])
def test_queries_use_only_current_closed_fields(kind):
    document = {"schema_version": 1, "kind": kind, "request_id": "q"}
    assert contract().validate_service_query(document) == document
    for bad in (document | {"lease": {}}, document | {"kind": "service_state"}):
        with pytest.raises(ValueError, match="SERVICE_QUERY_INVALID"):
            contract().validate_service_query(bad)


def test_readiness_cannot_claim_ready_with_missing_instances():
    document = {"schema_version": 1, "kind": "service_ready", "request_id": "q",
                "service_generation": "g", "image_digest": "sha256:" + "a" * 64,
                "package_source_sha256": "b" * 64, "model_id": "cup-model",
                "weights_sha256": "c" * 64, "service_config_sha256": "d" * 64,
                "gpu_uuid": "GPU-selected", "configured_instances": 3,
                "loaded_instances": 3, "ready": True}
    assert contract().validate_service_response(document) == document
    document["loaded_instances"] = 2
    with pytest.raises(ValueError, match="SERVICE_RESPONSE_INVALID"):
        contract().validate_service_response(document)


def test_published_inference_schema_accepts_only_current_wire_messages():
    import json
    import jsonschema
    from paths import PACKAGE_ROOT
    schema = json.loads((PACKAGE_ROOT / "config/act/inference-contract-schema.json").read_text())
    jsonschema.validate(request_document(), schema)
    jsonschema.validate(response_document(), schema)
    for invalid in (request_document() | {"lease": {}}, request_document() | {"kind": "broker_call"},
                    response_document() | {"outcome": "QUALIFIED"}):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(invalid, schema)
