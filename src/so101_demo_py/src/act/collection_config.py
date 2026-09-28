"""The ACT collection config: W8, recovery and Recorder backpressure, frozen and resolved.

The loader returns a closed document whose ``parallel_runtime`` binding is resolved against the
installed package share and whose hash is taken over the public runtime YAML's raw bytes.
"""

from __future__ import annotations

import hashlib
import os
import re
import stat
from pathlib import Path

SCHEMA_VERSION = 1
KIND = "act_parallel_collection"
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_TOP_LEVEL = ("schema_version", "kind", "parallel_runtime", "qualification", "recovery",
              "recorder", "telemetry")
_PARALLEL_RUNTIME = {"path", "sha256", "device", "allow_cpu_fallback"}
_QUALIFICATION = {"functional_worker_counts", "load_worker_count", "formal_worker_count",
                  "max_wave_size", "no_auto_degrade"}
_RECOVERY = {"business_retry_count", "max_infra_attempts_per_scenario",
             "resume_requires_identical_business_hashes"}
_RECORDER = {"sample_rate_hz", "queue_capacity_samples", "queue_high_watermark_samples",
             "queue_recovery_watermark_samples", "queue_high_watermark_hold_s", "lossless"}
_TELEMETRY = {"period_s"}


def _regular(path: Path, code: str) -> None:
    try:
        info = path.stat(follow_symlinks=False)
    except OSError as error:
        raise ValueError(code) from error
    if not stat.S_ISREG(info.st_mode):
        raise ValueError(code)


def _parse(path: Path) -> dict:
    import yaml

    _regular(path, "COLLECTION_CONFIG_MISSING")
    try:
        document = yaml.safe_load(path.read_bytes())
    except yaml.YAMLError as error:
        raise ValueError("COLLECTION_CONFIG_INVALID") from error
    if type(document) is not dict or tuple(sorted(document)) != tuple(sorted(_TOP_LEVEL)):
        raise ValueError("COLLECTION_CONFIG_INVALID")
    if document["schema_version"] != SCHEMA_VERSION or document["kind"] != KIND:
        raise ValueError("COLLECTION_CONFIG_INVALID")
    return document


def _resolve_public(document: dict, package_share: Path) -> dict:
    binding = document["parallel_runtime"]
    if type(binding) is not dict or set(binding) != _PARALLEL_RUNTIME:
        raise ValueError("COLLECTION_CONFIG_INVALID")
    relative = binding["path"]
    if (type(relative) is not str or not relative or relative.startswith("/")
            or "\\" in relative or ".." in Path(relative).parts
            or Path(relative).is_absolute()):
        raise ValueError("COLLECTION_PARALLEL_RUNTIME_PATH_INVALID")
    share = Path(package_share).resolve()
    resolved = share / relative
    try:
        info = resolved.stat(follow_symlinks=False)
    except OSError as error:
        raise ValueError("COLLECTION_PARALLEL_RUNTIME_PATH_INVALID") from error
    if not stat.S_ISREG(info.st_mode) or resolved.is_symlink():
        raise ValueError("COLLECTION_PARALLEL_RUNTIME_PATH_INVALID")
    if not resolved.resolve().is_relative_to(share):
        raise ValueError("COLLECTION_PARALLEL_RUNTIME_PATH_INVALID")
    if binding["device"] != "cuda" or binding["allow_cpu_fallback"] is not False:
        raise ValueError("COLLECTION_PARALLEL_RUNTIME_DEVICE_INVALID")
    if document["recorder"]["sample_rate_hz"] and "fallback" in document["recorder"]:
        raise ValueError("COLLECTION_CONFIG_INVALID")
    digest = hashlib.sha256(resolved.read_bytes()).hexdigest()
    if _SHA.fullmatch(str(binding["sha256"])) is None or digest != binding["sha256"]:
        raise ValueError("COLLECTION_PARALLEL_RUNTIME_HASH_INVALID")
    return dict(binding, path=relative, sha256=digest)


def load_collection_config(path: Path, *, package_share: Path) -> dict:
    """Return the closed, resolved collection config bound to the public runtime bytes."""

    document = _parse(Path(path))
    qualification = document["qualification"]
    if (type(qualification) is not dict or set(qualification) != _QUALIFICATION
            or qualification["functional_worker_counts"] != [1, 2]
            or qualification["load_worker_count"] != 8
            or qualification["formal_worker_count"] != 8
            or qualification["max_wave_size"] != 20
            or qualification["no_auto_degrade"] is not True):
        raise ValueError("COLLECTION_QUALIFICATION_INVALID")
    recovery = document["recovery"]
    if (type(recovery) is not dict or set(recovery) != _RECOVERY
            or recovery["business_retry_count"] != 0
            or recovery["max_infra_attempts_per_scenario"] != 2
            or recovery["resume_requires_identical_business_hashes"] is not True):
        raise ValueError("COLLECTION_RECOVERY_INVALID")
    recorder = document["recorder"]
    if (type(recorder) is not dict or set(recorder) != _RECORDER
            or recorder["sample_rate_hz"] != 10
            or recorder["queue_capacity_samples"] != 16
            or recorder["queue_high_watermark_samples"] != 12
            or recorder["queue_recovery_watermark_samples"] != 8
            or recorder["queue_high_watermark_hold_s"] != 0.2
            or recorder["lossless"] is not True
            or not (0 < recorder["queue_recovery_watermark_samples"]
                    < recorder["queue_high_watermark_samples"]
                    < recorder["queue_capacity_samples"])):
        raise ValueError("COLLECTION_RECORDER_INVALID")
    telemetry = document["telemetry"]
    if type(telemetry) is not dict or set(telemetry) != _TELEMETRY or telemetry["period_s"] != 1.0:
        raise ValueError("COLLECTION_TELEMETRY_INVALID")
    document["parallel_runtime"] = _resolve_public(document, Path(package_share))
    for key in ("fallback_devices", "fallback", "device"):
        if key == "device":
            continue
        if key in document:
            raise ValueError("COLLECTION_CONFIG_INVALID")
    return document
