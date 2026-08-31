from __future__ import annotations

from collections import Counter
from pathlib import Path

import yaml


PACKAGE_ROOT = Path(__file__).parents[1]
LOCK_PATH = PACKAGE_ROOT / "config/perception/requirements.lock"
TRAINING_PATH = PACKAGE_ROOT / "config/perception/training.yaml"


def _locked_packages() -> dict[str, str]:
    rows = []
    for raw_line in LOCK_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        assert "==" in line
        assert not any(operator in line for operator in (">=", "<=", "~=", "!=", ">", "<"))
        name, version = line.split("==", 1)
        assert name and version
        rows.append((name.lower().replace("_", "-"), version))
    counts = Counter(name for name, _version in rows)
    assert all(count == 1 for count in counts.values())
    return dict(rows)


def test_perception_application_dependencies_are_exactly_pinned() -> None:
    packages = _locked_packages()

    assert packages["torch"] == "2.13.0"
    assert packages["torchvision"] == "0.28.0"
    assert packages["ultralytics"] == "8.4.115"
    assert packages["mujoco"] == "3.12.0"


def test_training_contract_uses_local_segmentation_base_and_fixed_seed() -> None:
    document = yaml.safe_load(TRAINING_PATH.read_text(encoding="utf-8"))

    assert document["model"] == "yolo11n-seg.pt"
    assert document["task"] == "segment"
    assert document["imgsz"] == 640
    assert document["seed"] == 20260831
    assert document["deterministic"] is True
    assert document["classes"] == ["plastic_cup"]
    assert document["data"] == "dataset.yaml"
    assert document["epochs"] > 0
    assert document["device"] == "cuda"
