"""Task 8 live manifests freeze exact prefix and full-restart cases."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from so101_demo.act.pick_place_validation_manifest import (
    build_pick_place_validation_manifest, require_pick_place_validation_manifest, write_new_manifest,
)


ANCHORS = {
    "default": {"cup_start_m": [0.02, -0.28, 0.165], "neck_start_rad": 0.1},
    "left": {"cup_start_m": [-0.08, -0.28, 0.165], "neck_start_rad": 0.0},
    "forward": {"cup_start_m": [0.02, -0.36, 0.165], "neck_start_rad": 0.0},
}


def manifest():
    return build_pick_place_validation_manifest(
        ANCHORS, source_sha256="a" * 64, runtime_config_sha256="b" * 64,
        collection_config_sha256="c" * 64, contact_policy_fingerprint="d" * 64,
    )


def test_builder_freezes_nine_prefixes_and_five_full_restarts():
    document = manifest()
    assert len(document["prefix_cases"]) == 9
    assert [item["stop_after"] for item in document["prefix_cases"]] == [
        "SEARCH", "APPROACH", "CLOSE", "MICRO_LIFT", "TRANSPORT", "ALIGN",
        "RELEASE", "RADIAL_RETREAT", "FINAL_CHECK",
    ]
    assert len(document["full_cases"]) == 5
    assert {item["anchor"] for item in document["full_cases"]} == set(ANCHORS)
    assert all(item["lifecycle"] == "FULL_RESTART" for item in document["full_cases"])
    assert require_pick_place_validation_manifest(document) == document


@pytest.mark.parametrize("change", (
    lambda d: d["prefix_cases"].pop(),
    lambda d: d["prefix_cases"][1].update(stop_after="SEARCH"),
    lambda d: d["full_cases"][0].update(lifecycle="REUSE_STACK"),
    lambda d: d["full_cases"][0].update(anchor="unknown"),
    lambda d: d["anchors"]["left"]["cup_start_m"].__setitem__(0, 99.0),
    lambda d: d.update(source_sha256="e" * 64),
))
def test_tampering_or_missing_case_is_refused(change):
    document = deepcopy(manifest())
    change(document)
    with pytest.raises(ValueError):
        require_pick_place_validation_manifest(document)


def test_writer_never_overwrites_an_existing_manifest(tmp_path):
    path = tmp_path / "task8-live.json"
    original = manifest()
    write_new_manifest(path, original)
    first = path.read_bytes()
    with pytest.raises(FileExistsError):
        write_new_manifest(path, original)
    assert path.read_bytes() == first


def test_prepare_cli_freezes_file_hashes_and_refuses_overwrite(tmp_path):
    from so101_demo.cli.act_prepare_pick_place_validation import main

    anchors_path = tmp_path / "anchors.yaml"
    anchors_path.write_text(
        "schema_version: 1\nmeasurement_experiment: EXP-115\nanchors:\n"
        "  default: {cup_start_m: [0.02, -0.28, 0.165], neck_start_rad: 0.1}\n"
        "  left: {cup_start_m: [-0.08, -0.28, 0.165], neck_start_rad: 0.0}\n"
        "  forward: {cup_start_m: [0.02, -0.36, 0.165], neck_start_rad: 0.0}\n"
    )
    paths = []
    for name in ("source", "runtime", "collection"):
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps({"name": name}))
        paths.append(path)
    output = tmp_path / "manifest.json"
    argv = ["--anchors", str(anchors_path), "--source", str(paths[0]),
            "--runtime-config", str(paths[1]), "--collection-config", str(paths[2]),
            "--policy-fingerprint", "d" * 64, "--output", str(output)]
    assert main(argv) == 0
    document = require_pick_place_validation_manifest(json.loads(output.read_text()))
    assert document["source_sha256"] == hashlib.sha256(paths[0].read_bytes()).hexdigest()
    assert document["runtime_config_sha256"] == hashlib.sha256(paths[1].read_bytes()).hexdigest()
    assert document["collection_config_sha256"] == hashlib.sha256(paths[2].read_bytes()).hexdigest()
    before = output.read_bytes()
    with pytest.raises(FileExistsError):
        main(argv)
    assert output.read_bytes() == before


def test_checked_in_anchor_file_has_measured_exp115_values():
    import yaml

    path = Path(__file__).resolve().parents[1] / "config/act/task8-live-anchors.yaml"
    document = yaml.safe_load(path.read_text())
    assert set(document) == {"schema_version", "measurement_experiment", "anchors"}
    assert document["measurement_experiment"] == "EXP-115"
    assert document["anchors"] == ANCHORS
