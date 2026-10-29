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


def validate_mount_build(document):
    """The shape of the `mount_build` key: `{commit: 40 hex, root: <canonical absolute dir named by the commit's first 12 hex>}`."""
    _keys(document, ("commit", "root"))
    _text(document["commit"])
    _require(re.fullmatch(r"[0-9a-f]{40}", document["commit"]) is not None)
    root = _absolute(document["root"])
    _require(root.name == document["commit"][:12] and ".." not in root.parts and str(root) == document["root"])


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
# In-campaign retry of INVALID scenes: 0 (absent) to 3 extra rounds. Like `batch_hard_timeout_s` it is not part of the controlled
# identity (`unified.admission._collection_identity` reads only gpu_uuid and the images), so a qualification stays valid across values.
# Its low bound is 0, unlike every `_INT_LIMITS` entry.
_RETRY_INVALID_MAX_ROUNDS = "retry_invalid_max_rounds"
RETRY_INVALID_MAX_ROUNDS_LIMITS = (0, 3)
# The rig the campaign collects under, as the sha256 of its rig profile (`act.rig_profile.RigProfile.profile_sha256`). Absent = rig v1,
# the rig of every campaign config written before profiles existed. Unlike the keys above it IS part of the controlled identity
# (`unified.admission._collection_identity`, present only when named here), and the frozen inputs of the campaign must bind the same
# profile (`case_inputs.campaign_binding`), so data of different rigs cannot be mixed under one qualification.
_RIG_PROFILE_SHA256 = "rig_profile_sha256"
# The Teacher execution policy the campaign runs under, as the sha256 of the loaded policy (`policy_sha256`; R3-a: a schema 6 policy holds the
# diversity distributions and the campaign seed). Absent for every campaign that does not pin one. Like the rig it IS part of the controlled
# identity when named (`unified.admission._collection_identity`), which is what `collection_qualification_recompute` requires of a schema 6 freeze,
# and the frozen inputs must bind the same policy (`case_inputs.campaign_binding`).
_TEACHER_POLICY_SHA256 = "teacher_execution_policy_sha256"
# The GPU model the campaign declares (environment class: recorded in the qualification report, not part of the identity).
_GPU_MODEL = "gpu_model"
# Mount mode (design 2026-10-21, mount-build images; default off = absent): the containers run one dependency-only base image and get
# the host-built install and source trees of one commit as read-only bind mounts at `<root>/install` and `<root>/source`. The key is
# class L: it is part of the controlled identity (`unified.admission._collection_identity`) beside the images, whose `digest` is then the
# base image and whose two hashes are the sha256 of the trees' BUILD-COMMIT records (`container_campaign.mount_build`).
_MOUNT_BUILD = "mount_build"
# CPU partition mode (default off = absent): `container_campaign.cpuset`.
_SHARD_CPUSET = "shard_cpuset"
_OPTIONAL_LIMITS = (_GPU_MODEL, _MOUNT_BUILD, _SHARD_CPUSET, _RECORDING_CAP, _TASKS_IN_FLIGHT, _ASSIGNMENT_GAP, _BATCH_HARD_TIMEOUT_S, _RETRY_INVALID_MAX_ROUNDS,
                    _RIG_PROFILE_SHA256, _TEACHER_POLICY_SHA256, *_INT_LIMITS)


# The keys a campaign run takes from its runtime document (design 2026-10-19, class R): none of them changes what the data is.
# A version 1 campaign config may still carry them; a version 2 one may not.
RUNTIME_DOCUMENT_KEYS = (_PROCESSOR_COUNT, _PROCESSING_MAX_ATTEMPTS, _PROCESSING_RESERVE_S, _COLLECT_TIMEOUT_S, _PROCESS_TIMEOUT_S,
                         _VERIFICATION_RESERVE_S, _PROCESSING_TASK_TIMEOUT_S, _BATCH_HARD_TIMEOUT_S, _RETRY_INVALID_MAX_ROUNDS)


def _check_limit(name, value):
    """One optional campaign key against its closed bounds; raises ValueError."""
    if name == _RECORDING_CAP or name == _TASKS_IN_FLIGHT:
        _require(type(value) is int and 1 <= value <= 8)
    elif name == _ASSIGNMENT_GAP:
        _require(type(value) in (int, float) and 0 <= value <= 3600)
    elif name == _BATCH_HARD_TIMEOUT_S:
        _require(type(value) in (int, float) and BATCH_HARD_TIMEOUT_MIN_S <= value <= BATCH_HARD_TIMEOUT_MAX_S)
    elif name == _RETRY_INVALID_MAX_ROUNDS:
        low, high = RETRY_INVALID_MAX_ROUNDS_LIMITS
        _require(type(value) is int and low <= value <= high)
    elif name in (_RIG_PROFILE_SHA256, _TEACHER_POLICY_SHA256):
        _sha(value)
    else:
        low, high = _INT_LIMITS[name]
        _require(type(value) is int and low <= value <= high)


def load_runtime_document(path):
    """The runtime document of a campaign run: `{schema_version: 1, kind: ACT_CAMPAIGN_RUNTIME, <runtime keys>}`, every key optional.

    It is read fresh by each stage and never hashed into the campaign identity; the values a run used are recorded beside it."""
    try:
        with _open_regular(path) as stream:
            payload = stream.read(64 * 1024 + 1)
        _require(len(payload) <= 64 * 1024)
        document = json.loads(payload.decode("utf-8"), object_pairs_hook=_pairs,
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
        _require(type(document) is dict and set(document) <= {"schema_version", "kind", *RUNTIME_DOCUMENT_KEYS}
                 and {"schema_version", "kind"} <= set(document))
        _require(type(document["schema_version"]) is int and document["schema_version"] == 1
                 and document["kind"] == "ACT_CAMPAIGN_RUNTIME")
        for name in RUNTIME_DOCUMENT_KEYS:
            if name in document:
                _check_limit(name, document[name])
    except (OSError, ValueError, KeyError, TypeError, UnicodeError, RuntimeError) as error:
        raise ValueError("CAMPAIGN_RUNTIME_DOCUMENT_INVALID") from error
    return document


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
        for name in (_RECORDING_CAP, _TASKS_IN_FLIGHT, _ASSIGNMENT_GAP, _RIG_PROFILE_SHA256, _TEACHER_POLICY_SHA256, *RUNTIME_DOCUMENT_KEYS):
            if name in document:
                _check_limit(name, document[name])
        # version 2 moved the runtime-class keys out of this file into the runtime document (`load_runtime_document`): the file
        # they were in is hashed whole, so a change of a worker count or a timeout would otherwise change the campaign identity
        _require(document["schema_version"] == 1 or not any(name in document for name in RUNTIME_DOCUMENT_KEYS))
        _require(type(document["schema_version"]) is int and document["schema_version"] in (1, 2)
                 and document["kind"] == "ACT_CONTAINER_CAMPAIGN")
        root = _absolute(document["evidence_root"])
        _require(root.is_dir() and root.resolve(strict=True) == root)
        validate_file_ref(document["controlled_runtime"])
        for role in ("head", "teacher"):
            _service(document[role + "_service"], role, readback=role in roles)
        _require(document["head_service"]["image"] == document["teacher_service"]["image"])
        _image(document["shard_image"])
        if _MOUNT_BUILD in document:
            validate_mount_build(document[_MOUNT_BUILD])
            # one base image runs every role
            _require(document["shard_image"]["digest"] == document["head_service"]["image"]["digest"])
        if _SHARD_CPUSET in document:
            from so101_demo.runtime.container_campaign.cpuset import validate_cpuset
            validate_cpuset(document[_SHARD_CPUSET])
        _text(document["gpu_uuid"])
        _require(document["gpu_uuid"].startswith("GPU-"))
        if "gpu_model" in document:
            _text(document["gpu_model"])
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
