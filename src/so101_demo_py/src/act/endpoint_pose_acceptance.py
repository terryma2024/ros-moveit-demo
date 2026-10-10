"""The development runtime document: the user-authorized empirical bounds a development collection runs under.

Success of the cup task is the Teacher's own endpoint judgement (``teacher_endpoint``); this module only owns the closed
runtime document (path policy, RGB sync, release safety and the two resource hard stops) that the freezer binds into the
inputs manifest and the Teacher reads back.
"""

from __future__ import annotations

import math
from pathlib import Path

import yaml

#: the development runtime document's fixed identity and its four closed sections with their exact keys
RUNTIME_KIND = "ACT_ENDPOINT_DEVELOPMENT_RUNTIME"
RUNTIME_SCHEMA_VERSION = 1
RUNTIME_FIELDS = frozenset({"kind", "schema_version", "path_policy", "rgb_sync", "safety_release",
                            "hard_stops"})
RUNTIME_SECTIONS = {
    "path_policy": ("path_step_s", "path_clearance_m"),
    "rgb_sync": ("max_age_s", "max_skew_s"),
    "safety_release": ("support_distance_max_m",),
    "hard_stops": ("rtf_min", "disk_free_min_bytes"),
}


def load_development_runtime(path: Path) -> dict:
    """Parse the design's section 5.1 development runtime, or refuse by name.

    These are the user-authorized empirical initial values that let development proceed without measurement
    reports. Each section is closed: an unknown key, a wrong type, a non-finite or non-positive number and an
    integer field carrying a float are refused rather than merged, so a typo cannot silently become a safety
    bound. A CLI-specified run configuration still takes precedence over this installed file.
    """

    document = yaml.safe_load(Path(path).read_text())
    return validate_development_runtime(document)


def validate_development_runtime(document: dict) -> dict:
    """Validate the same runtime settings when read from the frozen input manifest."""
    if not isinstance(document, dict) or set(document) != RUNTIME_FIELDS:
        raise ValueError("DEVELOPMENT_RUNTIME_INVALID: not the closed runtime document")
    if (document["kind"] != RUNTIME_KIND or type(document["schema_version"]) is not int
            or document["schema_version"] != RUNTIME_SCHEMA_VERSION):
        raise ValueError("DEVELOPMENT_RUNTIME_INVALID: unknown kind or schema version")
    loaded = {"kind": RUNTIME_KIND, "schema_version": RUNTIME_SCHEMA_VERSION}
    for section, keys in RUNTIME_SECTIONS.items():
        body = document[section]
        if not isinstance(body, dict) or set(body) != set(keys):
            raise ValueError(f"DEVELOPMENT_RUNTIME_INVALID: {section} is not its closed key set")
        values = {}
        for key in keys:
            value = body[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"DEVELOPMENT_RUNTIME_INVALID: {section}.{key} is not a number")
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"DEVELOPMENT_RUNTIME_INVALID: {section}.{key} is not finite and positive")
            if key == "disk_free_min_bytes" and not isinstance(value, int):
                raise ValueError(f"DEVELOPMENT_RUNTIME_INVALID: {section}.{key} must be an integer")
            values[key] = value
        loaded[section] = values
    return loaded
