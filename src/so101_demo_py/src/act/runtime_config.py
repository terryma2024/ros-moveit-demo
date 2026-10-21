"""The frozen runtime settings for the inference boundary.

One request in flight, a bounded wait, and a bound on how old a reply may be before it is worthless. All
three exist so a slow model cannot stall the control loop and a late answer cannot be applied as if it
described the present.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

_CONFIG_KEYS = frozenset({"schema_version", "kind", "inference"})
_INFERENCE_KEYS = frozenset({"device", "queue_depth", "request_timeout_s", "max_reply_age_s",
                             "allow_cpu_fallback"})


def load_runtime_config(path) -> dict:
    target = Path(path)
    if not target.is_file():
        raise ValueError("RUNTIME_CONFIG_MISSING")
    try:
        document = yaml.safe_load(target.read_bytes())
    except yaml.YAMLError as error:
        raise ValueError("RUNTIME_CONFIG_INVALID") from error
    if (not isinstance(document, dict) or set(document) != _CONFIG_KEYS
            or document["schema_version"] != 1 or document["kind"] != "act_runtime"):
        raise ValueError("RUNTIME_CONFIG_INVALID")
    inference = document["inference"]
    if not isinstance(inference, dict) or set(inference) != _INFERENCE_KEYS:
        raise ValueError("RUNTIME_CONFIG_INVALID")
    if inference["device"] != "cuda" or inference["allow_cpu_fallback"] is not False:
        # inference for this campaign is CUDA-only, with no fallback path
        raise ValueError("RUNTIME_DEVICE_NOT_CUDA")
    if inference["queue_depth"] != 1:
        raise ValueError("RUNTIME_QUEUE_DEPTH_INVALID")
    for field in ("request_timeout_s", "max_reply_age_s"):
        value = inference[field]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
            raise ValueError("RUNTIME_TIMEOUT_INVALID")
    return document


#: the inference timeouts decide whether a reply is late (`PREFIX_LATE`), so a run may not have more of them than were qualified
#: (outcome-risk class); device and queue depth are runtime only. Nothing else in the file is logic but its kind and the
#: no-fallback rule.
OUTCOME_RISK_KEYS = ("request_timeout_s", "max_reply_age_s")
RUNTIME_ONLY_KEYS = ("device", "queue_depth")


def logic_document(config: dict) -> dict:
    """The part of a loaded inference runtime config that is logic: what the run identity binds (not the file bytes)."""
    return {"schema_version": config["schema_version"], "kind": config["kind"],
            "inference": {"allow_cpu_fallback": config["inference"]["allow_cpu_fallback"]}}


def logic_sha256(config: dict) -> str:
    return hashlib.sha256(json.dumps(logic_document(config), sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def runtime_values(config: dict) -> dict:
    """The outcome-risk and runtime-only values the run used: recorded for audit, never compared."""
    inference = config["inference"]
    return {"outcome_risk": {key: inference[key] for key in OUTCOME_RISK_KEYS},
            "runtime_only": {key: inference[key] for key in RUNTIME_ONLY_KEYS}}
