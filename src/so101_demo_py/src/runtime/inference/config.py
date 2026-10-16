"""Frozen campaign configuration; calibration hashes the full controlled file."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat

from so101_demo.runtime.inference.contract import (
    _integer, _keys, _number, _require, _sha, _text,
)
from so101_demo.runtime.parallel_ipc.frames import _pairs


def _absolute(value):
    _text(value)
    path = Path(value)
    _require(path.is_absolute() and ".." not in path.parts and str(path) == value)
    return path


def _open_regular(path):
    """Pin every directory component without following symlinks."""
    path = _absolute(str(path))
    directory = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for component in path.parts[1:-1]:
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                            dir_fd=directory)
            os.close(directory)
            directory = child
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=directory)
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            os.close(fd)
            raise ValueError("regular file required")
        return os.fdopen(fd, "rb")
    finally:
        os.close(directory)


def calibration_runtime_hash(controlled_runtime_path):
    """Hash actual bytes, never a filtered/normalized subset of a runtime file."""
    digest = hashlib.sha256()
    try:
        with _open_regular(controlled_runtime_path) as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
    except (OSError, ValueError) as error:
        raise ValueError("CAMPAIGN_CONFIG_INVALID: input file") from error
    return digest.hexdigest()


def validate_file_ref(document, *, readback=True):
    _keys(document, ("path", "sha256"))
    path = _absolute(document["path"])
    _sha(document["sha256"])
    if readback:
        _require(calibration_runtime_hash(path) == document["sha256"])
    return path


def _image(image):
    _keys(image, ("digest", "package_source_sha256", "install_sha256"))
    _text(image["digest"])
    _require(image["digest"].startswith("sha256:"))
    _sha(image["digest"][7:])
    _sha(image["package_source_sha256"])
    _sha(image["install_sha256"])


def _service(service, role, *, readback):
    _keys(service, ("image", "model", "instances", "torch_threads", "torch_interop_threads",
        "max_inflight_requests", "max_frame_bytes", "max_image_height", "max_image_width",
        "queue_timeout_s", "inference_timeout_s"))
    _image(service["image"])
    model = service["model"]
    _keys(model, ("model_id", "weights", "classes", "score_threshold"))
    _text(model["model_id"])
    validate_file_ref(model["weights"], readback=readback)
    _number(model["score_threshold"], maximum=1)
    classes = model["classes"]
    _require(type(classes) is dict and bool(classes))
    for index, name in classes.items():
        _require(type(index) is str and re.fullmatch(r"0|[1-9][0-9]*", index) is not None)
        _require(type(name) is str and re.fullmatch(r"[a-z][a-z0-9_]*", name) is not None)
    _require(len(set(classes.values())) == len(classes))
    for name in ("instances", "torch_threads", "torch_interop_threads", "max_inflight_requests",
                 "max_frame_bytes", "max_image_height", "max_image_width"):
        _integer(service[name])
    _require(service["max_frame_bytes"] <= 2**32 - 1 and service["max_frame_bytes"] > 4)
    for name in ("queue_timeout_s", "inference_timeout_s"):
        _number(service[name])
        _require(service[name] > 0)
    if role == "head":
        _require(service["max_inflight_requests"] == 8)


_RECORDING_CAP = "max_concurrent_recordings"
_TASKS_IN_FLIGHT = "max_tasks_in_flight"
_ASSIGNMENT_GAP = "min_assignment_gap_s"
# Phase 2 (processing) and the time limits of the two phases. Their sum against `batch_hard_timeout_s` is checked where that value
# is known (`processing_limits.check_phase_limits`).
_PROCESSOR_COUNT = "processor_count"
_PROCESSING_MAX_ATTEMPTS = "processing_max_attempts"
_PROCESSING_RESERVE_S = "processing_reserve_s"
_COLLECT_TIMEOUT_S = "collect_timeout_s"
_PROCESS_TIMEOUT_S = "process_timeout_s"
_VERIFICATION_RESERVE_S = "verification_reserve_s"
_PROCESSING_TASK_TIMEOUT_S = "processing_task_timeout_s"
# the task timeout may not be lower than the offline processor's 1200 s plus a 60 s margin
_INT_LIMITS = {_PROCESSOR_COUNT: (1, 16), _PROCESSING_MAX_ATTEMPTS: (1, 5), _PROCESSING_RESERVE_S: (1, 86400),
               _COLLECT_TIMEOUT_S: (1, 86400), _PROCESS_TIMEOUT_S: (1, 86400), _VERIFICATION_RESERVE_S: (1, 86400),
               _PROCESSING_TASK_TIMEOUT_S: (1260, 86400)}
# The campaign total deadline as a launch parameter: when present it replaces the parallel-runtime yaml's `batch_hard_timeout_s`
# (`processing_limits.effective_batch_total_s`). It is not part of the controlled identity, so a qualification stays valid across values.
_BATCH_HARD_TIMEOUT_S = "batch_hard_timeout_s"
BATCH_HARD_TIMEOUT_MIN_S = 1800
BATCH_HARD_TIMEOUT_MAX_S = 14400
_OPTIONAL_LIMITS = (_RECORDING_CAP, _TASKS_IN_FLIGHT, _ASSIGNMENT_GAP, _BATCH_HARD_TIMEOUT_S, *_INT_LIMITS)


def load_campaign_config(path, *, roles=("head", "teacher"), expected_sha256=None):
    """Validate one format and read hashes only for roles actually launched.

    Restricted measurement loads only head. Unused Teacher configuration still
    has the same closed shape, but its weights are not a measurement prerequisite.
    Role approval and Head binding are enforced by the owning entry, before launch.
    """
    try:
        _require(type(roles) is tuple and bool(roles) and len(set(roles)) == len(roles)
                 and all(role in ("head", "teacher") for role in roles))
        with _open_regular(path) as stream:
            payload = stream.read(1024 * 1024 + 1)
        _require(len(payload) <= 1024 * 1024)
        if expected_sha256 is not None:
            _sha(expected_sha256)
            _require(hashlib.sha256(payload).hexdigest() == expected_sha256)
        document = json.loads(payload.decode("utf-8"), object_pairs_hook=_pairs,
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
        _keys({name: value for name, value in document.items() if name not in _OPTIONAL_LIMITS},
              ("schema_version", "kind", "evidence_root", "controlled_runtime",
               "head_service", "teacher_service", "shard_image", "gpu_uuid",
               "qualification_contract"))
        if _RECORDING_CAP in document:
            # How many shards may be recording (hold a phase-1 task) at once; the Host reads it, the campaign hash freezes it.
            _require(type(document[_RECORDING_CAP]) is int and 1 <= document[_RECORDING_CAP] <= 8)
        if _TASKS_IN_FLIGHT in document:
            # How many shards may hold a task at once; the Host reads it, the campaign hash freezes it.
            _require(type(document[_TASKS_IN_FLIGHT]) is int and 1 <= document[_TASKS_IN_FLIGHT] <= 8)
        if _ASSIGNMENT_GAP in document:
            # Minimum Host monotonic seconds between two assignments across shards.
            _require(type(document[_ASSIGNMENT_GAP]) in (int, float) and 0 <= document[_ASSIGNMENT_GAP] <= 3600)
        if _BATCH_HARD_TIMEOUT_S in document:
            _require(type(document[_BATCH_HARD_TIMEOUT_S]) in (int, float)
                     and BATCH_HARD_TIMEOUT_MIN_S <= document[_BATCH_HARD_TIMEOUT_S] <= BATCH_HARD_TIMEOUT_MAX_S)
        for name, (low, high) in _INT_LIMITS.items():
            if name in document:
                _require(type(document[name]) is int and low <= document[name] <= high)
        _require(type(document["schema_version"]) is int and document["schema_version"] == 1
                 and document["kind"] == "ACT_CONTAINER_CAMPAIGN")
        root = _absolute(document["evidence_root"])
        _require(root.is_dir() and root.resolve(strict=True) == root)
        validate_file_ref(document["controlled_runtime"])
        for role in ("head", "teacher"):
            _service(document[role + "_service"], role, readback=role in roles)
        _require(document["head_service"]["image"] == document["teacher_service"]["image"])
        _image(document["shard_image"])
        _text(document["gpu_uuid"])
        _require(document["gpu_uuid"].startswith("GPU-"))
        if document["qualification_contract"] is not None:
            validate_file_ref(document["qualification_contract"])
    except (OSError, ValueError, KeyError, TypeError, UnicodeError, RuntimeError) as error:
        raise ValueError("CAMPAIGN_CONFIG_INVALID") from error
    return document


def verify_head_configuration(service, *, binding, runtime_versions):
    """Verify the current bound detector in the model-owning child process.

    The current HeadSearchBinding has no configurable detector score field:
    its detector uses the source-defined 0.25 prediction cutoff. Keep that
    behavior fixed; search min_confidence remains a separate local policy.
    """
    detector = binding.detector
    if any(runtime_versions.get(name) != detector[name]
           for name in ("torch_version", "ultralytics_version")):
        raise ValueError("HEAD_SEARCH_RUNTIME_VERSION_DRIFT")
    if any(service[name] != detector[name] for name in ("torch_threads", "torch_interop_threads")):
        raise ValueError("HEAD_SEARCH_THREAD_DRIFT")
    model = service["model"]
    if (model["model_id"] != detector["model_id"]
            or model["weights"]["path"] != detector["weights_path"]
            or model["weights"]["sha256"] != detector["weights_sha256"]
            or model["score_threshold"] != 0.25):
        raise ValueError("HEAD_SEARCH_MODEL_DRIFT")
    if detector["requested_device"] != "cuda" or detector["allow_cpu_fallback"] is not False:
        raise ValueError("HEAD_SEARCH_DEVICE_DRIFT")
