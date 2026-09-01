from __future__ import annotations

from pathlib import Path

import yaml


PACKAGE_ROOT = Path(__file__).parents[1]
CONFIG_PATH = PACKAGE_ROOT / "config/perception/grounded_sam.yaml"


def test_grounded_sam_config_freezes_models_prompt_and_thresholds() -> None:
    document = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))

    assert document["schema_version"] == 1
    assert document["pipeline_id"] == "grounding-dino-tiny+sam2.1-hiera-tiny"
    assert document["models"]["detector"] == {
        "model_id": "IDEA-Research/grounding-dino-tiny",
        "revision": "a2bb814dd30d776dcf7e30523b00659f4f141c71",
        "directory": "grounding-dino-tiny",
    }
    assert document["models"]["segmenter"] == {
        "model_id": "facebook/sam2.1-hiera-tiny",
        "revision": "de431c4043854a71d8101e17995dfe596bf101a5",
        "directory": "sam2.1-hiera-tiny",
    }
    assert document["prompts"] == {"plastic_cup": "plastic cup."}
    assert document["thresholds"] == {
        "grounding_box": 0.35,
        "grounding_text": 0.25,
        "duplicate_iou": 0.85,
        "max_candidates": 16,
        "sam_quality": 0.75,
        "min_mask_pixels": 64,
        "max_mask_area_ratio": 0.50,
    }
