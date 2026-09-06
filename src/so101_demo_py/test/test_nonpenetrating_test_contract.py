from __future__ import annotations

import copy
from pathlib import Path

import pytest
import so101_demo.training.grounding_dino_dataset as dino_dataset
from so101_demo.adapters.perception.mujoco_dataset import (
    DatasetScenario,
    load_dataset_config,
    scenario_plan,
    split_seed_plan,
)
from so101_demo.training.grounding_dino_dataset import GroundingDinoDatasetError

CONTRACT = "so101-nonpenetrating-test-v1"
SCENARIOS = tuple(scenario.value for scenario in DatasetScenario)


def _official_manifest() -> dict[str, object]:
    samples = []
    for offset in range(300):
        scenario = SCENARIOS[offset % len(SCENARIOS)]
        seed = 470000000 + offset
        samples.append(
            {
                "seed": seed,
                "split": "test",
                "scenario": scenario,
                "configured_cup_count": {
                    "no_cup": 0,
                    "two_cups": 2,
                }.get(scenario, 1),
                "visible_instance_count": 0 if scenario == "no_cup" else 1,
                "image": f"images/test/{seed:09d}.png",
                "label": f"labels/test/{seed:09d}.txt",
                "truth": f"truth/test/{seed:09d}.json",
            }
        )
    return {
        "dataset_contract": CONTRACT,
        "member_splits": ["test"],
        "split_counts": {"test": 300},
        "seed_starts": {"test": 470000000},
        "seed_ranges": {"test": [470000000, 470000299]},
        "scenario_quotas": {"test": {scenario: 50 for scenario in SCENARIOS}},
        "samples": samples,
    }


def test_official_test_config_loads_the_preregistered_population() -> None:
    path = (
        Path(__file__).parents[1]
        / "config/perception/plastic_cup_grounding_dino_nonpenetrating_test_v1.yaml"
    )

    config = load_dataset_config(path, generator_commit="a" * 40)
    seeds = split_seed_plan(config.split_counts, config.seed_starts)
    schedule = scenario_plan(config)["test"]

    assert config.dataset_contract == CONTRACT
    assert config.require_nonpenetrating_scene is True
    assert config.split_counts == {"test": 300}
    assert seeds["test"] == tuple(range(470000000, 470000300))
    assert tuple(item.value for item in schedule[:12]) == SCENARIOS * 2
    assert {item.value: schedule.count(item) for item in DatasetScenario} == {
        scenario: 50 for scenario in SCENARIOS
    }


def test_official_test_converter_validator_accepts_only_the_preregistered_schedule() -> None:
    validator = getattr(dino_dataset, "_validate_official_test_version", None)
    assert callable(validator), "missing official test-only version validator"
    manifest = _official_manifest()

    validator(manifest)
    changed = copy.deepcopy(manifest)
    changed["samples"][1]["scenario"] = "no_cup"
    with pytest.raises(GroundingDinoDatasetError, match="MANIFEST_INVALID"):
        validator(changed)


def test_test_only_dataset_yaml_exposes_no_train_or_val(tmp_path: Path) -> None:
    root = tmp_path / "source"
    root.mkdir()
    (root / "dataset.yaml").write_text(
        "path: .\ntest: images/test\nnames:\n  0: plastic_cup\n",
        encoding="utf-8",
    )

    dino_dataset._dataset_contract(root, ("test",))
