"""The Teacher's perception model per rig: side-wrist-indoor uses the indoor fine-tuned YOLO weights, every other rig keeps the old ones.

The campaign config names the Teacher model (`teacher_service.model`: id, weights path and sha256). A rig that has its own model must be
run with exactly that model, and no other rig may be run with it; a rig without an override is checked against nothing new, so the
head-wrist and side-wrist freezes, identities and digests are what they were.
"""

import copy

import pytest

from so101_demo.act import teacher_model
from so101_demo.act.rig_profile import HEAD_WRIST_RIG, SIDE_WRIST_INDOOR_RIG, SIDE_WRIST_RIG

OLD_SHA = "f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781"
INDOOR_SHA = "f9cce63b17b1a3d2a32cd6d841c25a7482f1db87b8f96cd31bd4e03149dfcfee"


def _campaign(sha, model_id="plastic-cup-yolo11n-seg-v1"):   # the model id is the controlled runtime's for every rig
    return {"teacher_service": {"model": {"model_id": model_id, "classes": {"0": "plastic_cup"}, "score_threshold": 0.25,
                                         "weights": {"path": "/x/best.pt", "sha256": sha}}}}


def test_only_the_indoor_rig_has_a_teacher_model_of_its_own():
    assert teacher_model.TEACHER_MODEL_OVERRIDES == {"side-wrist-indoor": teacher_model.INDOOR_TEACHER_MODEL}
    model = teacher_model.INDOOR_TEACHER_MODEL
    assert model.weights_sha256 == INDOOR_SHA
    assert teacher_model.teacher_model_override(SIDE_WRIST_INDOOR_RIG) is model
    assert teacher_model.teacher_model_override("side-wrist-indoor") is model
    assert teacher_model.teacher_model_override(SIDE_WRIST_RIG) is None and teacher_model.teacher_model_override(HEAD_WRIST_RIG) is None
    assert teacher_model.teacher_model_override(None) is None
    # the old weights stay the frozen identity every other contract names
    from so101_demo.parallel_batch.frozen_models import FROZEN_YOLO_WEIGHTS_SHA256
    assert FROZEN_YOLO_WEIGHTS_SHA256 == OLD_SHA != INDOOR_SHA


def test_the_indoor_campaign_must_run_the_indoor_model_and_nothing_else():
    teacher_model.verify_campaign_teacher_model(_campaign(INDOOR_SHA), SIDE_WRIST_INDOOR_RIG)
    for config in (_campaign(OLD_SHA), _campaign("0" * 64), {}, {"teacher_service": {}}):
        with pytest.raises(ValueError, match="TEACHER_MODEL_RIG_MISMATCH"):
            teacher_model.verify_campaign_teacher_model(config, SIDE_WRIST_INDOOR_RIG)


@pytest.mark.parametrize("rig", [HEAD_WRIST_RIG, SIDE_WRIST_RIG], ids=lambda rig: rig.rig)
def test_the_other_rigs_keep_their_old_weights_and_refuse_the_indoor_ones(rig):
    teacher_model.verify_campaign_teacher_model(_campaign(OLD_SHA), rig)
    # a config of another weights (a test fixture, an older campaign) is not checked by this module: nothing about those rigs changed
    teacher_model.verify_campaign_teacher_model(_campaign("a" * 64), rig)
    teacher_model.verify_campaign_teacher_model({}, rig)
    with pytest.raises(ValueError, match="TEACHER_MODEL_RIG_MISMATCH"):
        teacher_model.verify_campaign_teacher_model(_campaign(INDOOR_SHA), rig)


def test_the_check_does_not_modify_the_campaign_config():
    config = _campaign(OLD_SHA)
    before = copy.deepcopy(config)
    teacher_model.verify_campaign_teacher_model(config, SIDE_WRIST_RIG)
    assert config == before
