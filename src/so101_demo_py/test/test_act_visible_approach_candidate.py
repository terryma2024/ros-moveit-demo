"""A visible approach candidate cannot grant collection or motion authority."""

import json
from pathlib import Path

import pytest

from so101_demo.act.visible_approach_diagnostic import build_route_manifest
from so101_demo.act.visible_approach_candidate import (
    build_candidate_manifest,
    require_candidate_profile,
)


PACKAGE = Path(__file__).resolve().parents[1]
SCENE = PACKAGE / "assets/mujoco/act/scene.xml"
PLUGIN = PACKAGE / "config/mujoco/act/task6_route_plugins.yaml"
SOURCE = PACKAGE / "config/mujoco/act/task6_visible_approach_v1.json"
CANDIDATE = PACKAGE / "config/mujoco/act/visible_approach_candidate_v1.json"


def source_route():
    return build_route_manifest(
        scene_path=SCENE, plugin_path=PLUGIN, profile_path=SOURCE,
        session_id="offline-candidate", attempt_id="offline-candidate",
    )


def test_candidate_rechecks_all_exact_grid_prefixes_and_retains_no_authority():
    result = build_candidate_manifest(
        scene_path=SCENE, plugin_path=PLUGIN, source_profile_path=SOURCE,
        candidate_profile_path=CANDIDATE, session_id="offline-candidate",
        attempt_id="offline-candidate",
    )
    assert result["eligible_for_collection"] is False
    assert result["kind"] == "ACT_VISIBLE_APPROACH_CANDIDATE"
    assert result["source_route_sha256"] == source_route()["manifest_sha256"]
    assert len(result["segments"]) == 31
    assert result["segments"][0]["first_segment"] == 0
    assert result["segments"][-1]["last_segment"] == 245
    assert all(item["samples"] == 701 for item in result["segments"])
    assert result["segments"][0]["rows_sha256"] == (
        "56c6e5334f5c7b41ee9f7c5af592aa10738060dbf0b37fcdf83131c739d01498"
    )


def test_candidate_profile_rejects_collection_hash_and_anchor_tamper():
    route = source_route()
    profile = json.loads(CANDIDATE.read_bytes())
    require_candidate_profile(profile, route)
    with pytest.raises(ValueError):
        require_candidate_profile({**profile, "eligible_for_collection": True}, route)
    hashes = profile["row_sha256s"].copy()
    hashes[0] = "0" * 64
    with pytest.raises(ValueError):
        require_candidate_profile({**profile, "row_sha256s": hashes}, route)
    boundaries = profile["segment_last_indices"].copy()
    boundaries.remove(181)
    with pytest.raises(ValueError):
        require_candidate_profile({**profile, "segment_last_indices": boundaries,
                                   "row_sha256s": profile["row_sha256s"][:-1]}, route)


def test_candidate_source_profile_drift_refuses(tmp_path):
    changed = json.loads(SOURCE.read_bytes())
    changed["stages"][0]["end"][5] += .001
    source_copy = tmp_path / "source.json"
    source_copy.write_text(json.dumps(changed))
    with pytest.raises(ValueError):
        build_candidate_manifest(
            scene_path=SCENE, plugin_path=PLUGIN, source_profile_path=source_copy,
            candidate_profile_path=CANDIDATE, session_id="offline-candidate",
            attempt_id="offline-candidate",
        )
