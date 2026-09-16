"""Contract tests for the scripted expert-validation E2E fixture stack."""

from __future__ import annotations

from pathlib import Path
import sys

import pytest
import yaml

_E2E_DIR = Path(__file__).resolve().parents[1] / "e2e"
_DEMO_SRC = Path(__file__).resolve().parents[4] / "so101_demo_py" / "src"
for _path in (str(_E2E_DIR), str(_DEMO_SRC)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from scripted_service import (  # noqa: E402
    ScenarioError,
    load_scenario,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "expert_validation_e2e"
EXPECTED_BASELINE_SHA256 = (
    "746052476af84686fccab6d9eb6497cce865b9b1e3634d9ea4c9e58e0e683691"
)


def _write_scenario(tmp_path: Path, document: dict) -> Path:
    path = tmp_path / "scenario.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(document), encoding="utf-8")
    return path


def _baseline_document() -> dict:
    return yaml.safe_load((FIXTURES / "scenarios" / "baseline.yaml").read_text("utf-8"))


def test_scenario_hash_is_canonical():
    scenario, digest = load_scenario(FIXTURES / "scenarios" / "baseline.yaml")
    assert scenario.schema_version == 1
    assert scenario.scenario_id == "baseline-sequential-4"
    assert digest == EXPECTED_BASELINE_SHA256


def test_scenario_hash_is_deterministic_and_order_independent(tmp_path):
    document = _baseline_document()
    first_path = _write_scenario(tmp_path / "a", document)
    reordered = {key: document[key] for key in reversed(list(document))}
    second_path = _write_scenario(tmp_path / "b", reordered)
    _, first_digest = load_scenario(first_path)
    scenario, second_digest = load_scenario(second_path)
    assert first_digest == second_digest
    assert scenario.scenario_id == "baseline-sequential-4"


def test_scenario_rejects_unknown_top_level_field(tmp_path):
    document = _baseline_document()
    document["surprise_field"] = True
    path = _write_scenario(tmp_path, document)
    with pytest.raises(ScenarioError, match="UNKNOWN_FIELD"):
        load_scenario(path)


def test_scenario_rejects_duplicate_event_sequence(tmp_path):
    document = _baseline_document()
    document["event_script"][1]["sequence"] = 2
    path = _write_scenario(tmp_path, document)
    with pytest.raises(ScenarioError, match="DUPLICATE_SEQUENCE"):
        load_scenario(path)


def test_scenario_requires_scenario_id(tmp_path):
    document = _baseline_document()
    del document["scenario_id"]
    path = _write_scenario(tmp_path, document)
    with pytest.raises(ScenarioError, match="SCENARIO_ID"):
        load_scenario(path)


def test_scenario_rejects_wrong_schema_version(tmp_path):
    document = _baseline_document()
    document["schema_version"] = 2
    path = _write_scenario(tmp_path, document)
    with pytest.raises(ScenarioError, match="SCHEMA_VERSION"):
        load_scenario(path)


@pytest.mark.parametrize(
    "forbidden_key",
    ["robot_pose", "joint_states", "mujoco", "physics", "tf", "planning_scene"],
)
def test_scenario_rejects_robot_truth(tmp_path, forbidden_key):
    document = _baseline_document()
    document["event_script"][0]["patch"][forbidden_key] = {"x": 0.1}
    path = _write_scenario(tmp_path, document)
    with pytest.raises(ScenarioError, match="ROBOT_TRUTH_FORBIDDEN"):
        load_scenario(path)
