"""The development runtime document (the user-authorized empirical bounds): its closed schema and its refusals."""

from __future__ import annotations

import pytest
import yaml

from so101_demo.act.endpoint_pose_acceptance import load_development_runtime
from paths import PACKAGE_ROOT

RUNTIME = PACKAGE_ROOT / "config/act/endpoint_pose_development_runtime.yaml"


def test_the_authorized_runtime_defaults_load_exactly():
    """Section 5.1's values are what the installed file carries, and they come back unchanged."""

    runtime = load_development_runtime(RUNTIME)
    assert runtime["path_policy"] == {"path_step_s": 0.002, "path_clearance_m": 0.002}
    assert runtime["rgb_sync"] == {"max_age_s": 0.1, "max_skew_s": 0.1}
    assert runtime["safety_release"] == {"support_distance_max_m": 0.002}
    assert runtime["hard_stops"] == {"rtf_min": 0.90, "disk_free_min_bytes": 53687091200}


def _runtime_document() -> dict:
    return {
        "kind": "ACT_ENDPOINT_DEVELOPMENT_RUNTIME", "schema_version": 1,
        "path_policy": {"path_step_s": 0.002, "path_clearance_m": 0.002},
        "rgb_sync": {"max_age_s": 0.1, "max_skew_s": 0.1},
        "safety_release": {"support_distance_max_m": 0.002},
        "hard_stops": {"rtf_min": 0.90, "disk_free_min_bytes": 53687091200},
    }


@pytest.mark.parametrize("patch", [
    {"extra_section": {"a": 1}},
    {"path_policy": {"path_step_s": 0.002}},
    {"hard_stops": {"rtf_min": True, "disk_free_min_bytes": 53687091200}},
    {"hard_stops": {"rtf_min": 0.90, "disk_free_min_bytes": 5.5e10}},
    {"rgb_sync": {"max_age_s": -0.1, "max_skew_s": 0.1}},
    {"kind": "OTHER"},
    {"rgb_sync": {"max_age_s": float("inf"), "max_skew_s": 0.1}},
])
def test_bad_development_runtimes_are_refused_by_name(tmp_path, patch):
    document = {**_runtime_document(), **patch}
    path = tmp_path / "runtime.yaml"
    path.write_text(yaml.safe_dump(document))
    with pytest.raises(ValueError, match="DEVELOPMENT_RUNTIME_INVALID"):
        load_development_runtime(path)
