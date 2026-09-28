"""Task 13: the frozen runtime settings for the inference boundary.

One request in flight, a bounded wait, and a bound on how old a reply may be before it is worthless. All
three exist so a slow model cannot stall the control loop and a late answer cannot be applied as if it
described the present.
"""

from __future__ import annotations

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
