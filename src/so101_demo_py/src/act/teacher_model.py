"""The Teacher's perception model per camera rig.

The Teacher localises the cup with a YOLO segmentation model and the task camera's depth. The campaign config names that model
(`teacher_service.model`: `model_id` and `weights.path` / `weights.sha256`) and its hash is part of the controlled identity. Every rig
uses the long-frozen weights (`parallel_batch.frozen_models.FROZEN_YOLO_WEIGHTS_SHA256`) except the rigs listed in
`TEACHER_MODEL_OVERRIDES`: `side-wrist-indoor` uses the weights fine-tuned on indoor renders (the old model reads the red landing ring
plus the cup's shadow in the bright indoor scene as a second cup and refuses 4 of 32 positions as ambiguous).

`verify_campaign_teacher_model` is called where a campaign config meets its rig (`case_inputs.campaign_binding` and the task
builder): a rig with an override must be run with exactly that model, and no other rig may be run with an override's weights. A rig
without an override is checked against nothing else, so the head-wrist and side-wrist campaigns, freezes and identity digests are
unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass

from .rig_files import rig_name


@dataclass(frozen=True)
class TeacherModel:
    model_id: str
    weights_sha256: str


#: weights installed at `/data/work/models/so101-perception/yolo11n-seg-plastic-cup-indoor-20261025/best.pt`, published as HF `zjumty/so101-yolo11n-seg-cup-indoor`
INDOOR_TEACHER_MODEL = TeacherModel("plastic-cup-yolo11n-seg-indoor-20261025",
                                    "f9cce63b17b1a3d2a32cd6d841c25a7482f1db87b8f96cd31bd4e03149dfcfee")
TEACHER_MODEL_OVERRIDES = {"side-wrist-indoor": INDOOR_TEACHER_MODEL}


def teacher_model_override(rig=None):
    """The `TeacherModel` of a rig (a profile, a name, or None) that has its own, else None (the frozen weights)."""
    return TEACHER_MODEL_OVERRIDES.get(rig_name(rig))


def verify_campaign_teacher_model(campaign_config: dict, rig) -> None:
    """Raise `ValueError("TEACHER_MODEL_RIG_MISMATCH")` unless the campaign's Teacher model suits `rig`."""
    try:
        model = campaign_config["teacher_service"]["model"]
        sha, model_id = model["weights"]["sha256"], model["model_id"]
    except (KeyError, TypeError):
        sha = model_id = None
    override = teacher_model_override(rig)
    if override is not None:
        if (model_id, sha) != (override.model_id, override.weights_sha256):
            raise ValueError("TEACHER_MODEL_RIG_MISMATCH")
        return
    if any(sha == other.weights_sha256 or model_id == other.model_id for other in TEACHER_MODEL_OVERRIDES.values()):
        raise ValueError("TEACHER_MODEL_RIG_MISMATCH")
