"""Head Search data, episode, and candidate identities must be closed and leak-free.

These three identities are what Tasks 2-4 consume: a sealed image-split partition that cannot place
one MuJoCo world state in two camera domains or two splits, three mutually disjoint episode seed
lists, and one frozen candidate identity that binds the weights to both camera-domain operating
points, the postprocess version, the tracker and the runtime. Head Search never uses Grounded-SAM,
so no document here carries a Grounded-SAM field.
"""

from __future__ import annotations

import pytest
from so101_demo.act.head_search.training import (
    CANDIDATE_IDENTITY_KEYS,
    CandidateIdentity,
    HeadSearchSplitSeal,
    validate_episode_seed_partitions,
    validate_scene_group_partition,
)
from so101_demo.perception_benchmark.contracts import OperatingPoint, canonical_sha256


def _sha(seed: str) -> str:
    return (seed * 64)[:64]


def operating_point(**overrides: object) -> OperatingPoint:
    values: dict[str, object] = {
        "min_confidence": 0.51,
        "min_bbox_aspect": 1.15,
        "min_area_px2": 120.0,
        "tracking_iou": 0.3,
    }
    values.update(overrides)
    return OperatingPoint(**values)  # type: ignore[arg-type]


def candidate_document(**overrides: object) -> dict[str, object]:
    document: dict[str, object] = {
        "candidate_id": "B",
        "weights_sha256": _sha("a"),
        "head_operating_point": operating_point().to_document(),
        "task_operating_point": operating_point(min_confidence=0.62).to_document(),
        "postprocess_sha256": _sha("b"),
        "tracker_sha256": _sha("c"),
        "runtime_sha256": _sha("d"),
    }
    document.update(overrides)
    return document


def seal_document(**overrides: object) -> dict[str, object]:
    document: dict[str, object] = {
        "camera_name": "head_camera",
        "dataset_sha256": _sha("e"),
        "counts": {"train": 800, "val": 200, "test": 200},
        "scene_groups": {
            "train": ("scene-1", "scene-2"),
            "val": ("scene-3",),
            "test": ("scene-4",),
        },
    }
    document.update(overrides)
    return document


def test_scene_group_cannot_cross_camera_splits() -> None:
    head = {"scene-7": "train"}
    task = {"scene-7": "test"}

    with pytest.raises(ValueError, match="SCENE_GROUP_SPLIT_LEAK"):
        validate_scene_group_partition(head=head, task=task)


def test_scene_group_partition_merges_domains_that_agree() -> None:
    merged = validate_scene_group_partition(
        head={"scene-1": "train", "scene-2": "val"},
        task={"scene-2": "val", "scene-3": "test"},
    )

    assert merged == {"scene-1": "train", "scene-2": "val", "scene-3": "test"}


def test_scene_group_partition_rejects_an_unknown_split_name() -> None:
    with pytest.raises(ValueError, match="SCENE_GROUP_SPLIT_INVALID"):
        validate_scene_group_partition(head={"scene-1": "training"}, task={})


def test_candidate_identity_binds_operating_point_and_tracker() -> None:
    identity = CandidateIdentity.from_document(candidate_document())

    assert identity.candidate_id == "B"
    assert identity.weights_sha256 == _sha("a")
    assert identity.head_operating_point.min_confidence == 0.51
    assert identity.task_operating_point.min_confidence == 0.62
    assert identity.postprocess_sha256 == _sha("b")
    assert identity.tracker_sha256 == _sha("c")
    assert identity.runtime_sha256 == _sha("d")
    assert identity.sha256 == canonical_sha256(identity.to_document())


def test_candidate_identity_document_keys_are_exact_and_hold_no_grounded_sam_field() -> None:
    identity = CandidateIdentity.from_document(candidate_document())

    assert tuple(CANDIDATE_IDENTITY_KEYS) == tuple(candidate_document())
    assert set(identity.to_document()) == set(CANDIDATE_IDENTITY_KEYS)
    assert not [key for key in CANDIDATE_IDENTITY_KEYS if "sam" in key or "ground" in key]


@pytest.mark.parametrize("missing", ["tracker_sha256", "head_operating_point"])
def test_candidate_identity_rejects_missing_fields(missing: str) -> None:
    document = candidate_document()
    del document[missing]

    with pytest.raises(ValueError, match="CANDIDATE_IDENTITY_FIELDS_INVALID"):
        CandidateIdentity.from_document(document)


def test_candidate_identity_rejects_an_extra_field() -> None:
    with pytest.raises(ValueError, match="CANDIDATE_IDENTITY_FIELDS_INVALID"):
        CandidateIdentity.from_document(candidate_document(grounded_sam_sha256=_sha("f")))


def test_candidate_identity_rejects_uppercase_digest_and_unknown_candidate() -> None:
    with pytest.raises(ValueError, match="weights_sha256"):
        CandidateIdentity.from_document(candidate_document(weights_sha256="A" * 64))
    with pytest.raises(ValueError, match="candidate_id"):
        CandidateIdentity.from_document(candidate_document(candidate_id="D"))


def test_candidate_identity_rejects_a_nonfinite_operating_point() -> None:
    document = candidate_document()
    document["head_operating_point"]["min_confidence"] = float("nan")  # type: ignore[index]

    with pytest.raises(ValueError, match="min_confidence"):
        CandidateIdentity.from_document(document)


def test_candidate_identity_rejects_a_bare_operating_point_mapping() -> None:
    with pytest.raises(ValueError, match="head_operating_point"):
        CandidateIdentity(
            candidate_id="A",
            weights_sha256=_sha("a"),
            head_operating_point={"min_confidence": 0.5},  # type: ignore[arg-type]
            task_operating_point=operating_point(),
            postprocess_sha256=_sha("b"),
            tracker_sha256=_sha("c"),
            runtime_sha256=_sha("d"),
        )


def test_split_seal_rejects_one_scene_group_in_two_image_splits() -> None:
    document = seal_document(
        scene_groups={"train": ("scene-1", "scene-2"), "val": ("scene-2",), "test": ()}
    )

    with pytest.raises(ValueError, match="SCENE_GROUP_SPLIT_LEAK"):
        HeadSearchSplitSeal.from_document(document)


def test_split_seal_rejects_a_repeated_scene_group_inside_one_split() -> None:
    document = seal_document(scene_groups={"train": ("scene-1", "scene-1"), "val": (), "test": ()})

    with pytest.raises(ValueError, match="SCENE_GROUP_DUPLICATE"):
        HeadSearchSplitSeal.from_document(document)


def test_split_seal_rejects_missing_splits_or_nonpositive_counts() -> None:
    with pytest.raises(ValueError, match="SPLIT_COUNTS_INVALID"):
        HeadSearchSplitSeal.from_document(seal_document(counts={"train": 800, "val": 200}))
    with pytest.raises(ValueError, match="counts"):
        HeadSearchSplitSeal.from_document(
            seal_document(counts={"train": 800, "val": 0, "test": 200})
        )


def test_split_seal_rejects_an_extra_field() -> None:
    with pytest.raises(ValueError, match="SPLIT_SEAL_FIELDS_INVALID"):
        HeadSearchSplitSeal.from_document(seal_document(promotable=True))


@pytest.mark.parametrize(
    "members",
    [
        {"scene-1": {"grounded_sam_sha256": _sha("f")}},
        {"scene-1": {"score": float("nan")}},
        "scene-1",
        (value for value in ("scene-1",)),
    ],
)
def test_split_seal_never_discards_a_malformed_scene_group_payload(members: object) -> None:
    document = seal_document(
        scene_groups={"train": members, "val": ("scene-3",), "test": ("scene-4",)}
    )

    with pytest.raises(ValueError, match="SCENE_GROUP_PARTITION_INVALID"):
        HeadSearchSplitSeal.from_document(document)


def test_split_seal_rejects_an_empty_partition_for_its_own_positive_counts() -> None:
    document = seal_document(scene_groups={"train": (), "val": (), "test": ()})

    with pytest.raises(ValueError, match="SCENE_GROUP_COUNT_INVALID"):
        HeadSearchSplitSeal.from_document(document)


def test_split_seal_rejects_more_scene_groups_than_declared_images() -> None:
    document = seal_document(
        counts={"train": 1, "val": 1, "test": 1},
        scene_groups={
            "train": ("scene-1", "scene-4"),
            "val": ("scene-2",),
            "test": ("scene-3",),
        },
    )

    with pytest.raises(ValueError, match="SCENE_GROUP_COUNT_INVALID"):
        HeadSearchSplitSeal.from_document(document)


def test_split_seal_accepts_one_group_per_image_and_many_images_per_group() -> None:
    one_per_image = seal_document(
        counts={"train": 2, "val": 1, "test": 1},
        scene_groups={"train": ("scene-1", "scene-2"), "val": ("scene-3",), "test": ("scene-4",)},
    )
    many_images_per_group = seal_document(
        counts={"train": 800, "val": 200, "test": 200},
        scene_groups={"train": ("scene-1",), "val": ("scene-2",), "test": ("scene-3",)},
    )

    assert HeadSearchSplitSeal.from_document(one_per_image).counts["train"] == 2
    assert HeadSearchSplitSeal.from_document(many_images_per_group).sha256


def test_split_seal_round_trips_with_a_canonical_digest() -> None:
    document = seal_document()
    seal = HeadSearchSplitSeal.from_document(document)

    assert seal.to_document() == document
    assert seal.sha256 == canonical_sha256(document)
    assert seal == HeadSearchSplitSeal.from_document(seal.to_document())


def test_episode_seed_partitions_must_be_disjoint() -> None:
    with pytest.raises(ValueError, match="EPISODE_PARTITION_OVERLAP"):
        validate_episode_seed_partitions(calibration=(1, 2, 3), held_out=(3, 4), qualification=(5,))


def test_episode_seed_partitions_reject_a_repeated_seed_inside_one_partition() -> None:
    with pytest.raises(ValueError, match="EPISODE_SEED_DUPLICATE"):
        validate_episode_seed_partitions(calibration=(1, 1), held_out=(2,), qualification=(3,))


@pytest.mark.parametrize("seed", [True, -1, 1.5])
def test_episode_seed_partitions_reject_non_integer_seeds(seed: object) -> None:
    with pytest.raises(ValueError, match="EPISODE_SEED_INVALID"):
        validate_episode_seed_partitions(calibration=(seed,), held_out=(), qualification=())


def test_episode_seed_partitions_return_the_three_frozen_lists() -> None:
    partitions = validate_episode_seed_partitions(
        calibration=(1, 2), held_out=(3,), qualification=(4, 5, 6)
    )

    assert partitions == {"calibration": (1, 2), "held_out": (3,), "qualification": (4, 5, 6)}
