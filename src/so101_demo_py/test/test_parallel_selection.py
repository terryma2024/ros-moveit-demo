"""Immutable selection bindings for the macOS service campaign (design section 8).

The service must write one binding before a campaign starts, and the adapter must accept only
that binding: no default points, no "first two of the catalog", no full-catalog traversal by a
Worker. These tests drive the RED/GREEN boundary of plan Task 2. The module under test is
imported lazily so a missing implementation is reported as a failed assertion instead of a
collection error.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
from pathlib import Path

import pytest

ANCHOR_IDS = (
    "task_start",
    "cup_test_forward_5cm",
    "cup_test_left_5cm",
    "cup_test_right_5cm",
)
SAMPLE_IDS = tuple(f"sample_{index:02d}_near_center" for index in range(1, 17))
ALL_IDS = ANCHOR_IDS + SAMPLE_IDS

CONFIG_SHA = "c" * 64
CLOSURE_SHA = "d" * 64


def _selection_module():
    spec = importlib.util.find_spec("so101_demo.parallel_batch.selection")
    assert spec is not None, "so101_demo.parallel_batch.selection is not implemented yet"
    return importlib.import_module("so101_demo.parallel_batch.selection")


def _catalog_document() -> dict:
    points = []
    for index, point_id in enumerate(ALL_IDS):
        points.append(
            {
                "id": point_id,
                "label": point_id.replace("_", " "),
                "source": "anchor" if point_id in ANCHOR_IDS else "generated",
                "stratum": "anchor" if point_id in ANCHOR_IDS else "near/center",
                "cup_position_world_m": [0.01 * index, -0.28, 0.165],
            }
        )
    return {"schema_version": 1, "points": points}


def _write_catalog(tmp_path: Path) -> Path:
    import yaml

    path = tmp_path / "moveit_expert_validation_points_v1.yaml"
    path.write_text(yaml.safe_dump(_catalog_document(), sort_keys=False), encoding="utf-8")
    return path


def _first_pass(module, catalog: Path, point_ids, **overrides):
    arguments = {
        "catalog_path": catalog,
        "point_ids": tuple(point_ids),
        "campaign_id": "campaign-a",
        "batch_id": "batch-a",
        "config_sha256": CONFIG_SHA,
        "runtime_closure_sha256": CLOSURE_SHA,
    }
    arguments.update(overrides)
    return module.build_first_pass_selection(**arguments)


# --------------------------------------------------------------------------------------
# First-pass binding: 4-20 points including the four fixed anchors
# --------------------------------------------------------------------------------------


def test_first_pass_binding_accepts_anchors_plus_samples(tmp_path: Path) -> None:
    module = _selection_module()
    catalog = _write_catalog(tmp_path)
    point_ids = ANCHOR_IDS + SAMPLE_IDS[:3]

    binding = _first_pass(module, catalog, point_ids)

    assert binding.selected_point_ids == point_ids
    assert binding.catalog_schema_version == 1
    assert binding.coordinate_frame == "world"
    assert len(binding.selection_sha256) == 64
    assert binding.catalog_sha256 == module.load_point_catalog(catalog).sha256
    assert [point.point_id for point in binding.points] == list(point_ids)
    assert all(len(point.point_sha256) == 64 for point in binding.points)
    assert binding.campaign_id == "campaign-a" and binding.batch_id == "batch-a"
    assert binding.config_sha256 == CONFIG_SHA
    assert binding.runtime_closure_sha256 == CLOSURE_SHA


def test_first_pass_binding_refuses_a_point_count_outside_four_to_twenty(
    tmp_path: Path,
) -> None:
    module = _selection_module()
    catalog = _write_catalog(tmp_path)

    with pytest.raises(module.SelectionError) as too_few:
        _first_pass(module, catalog, ANCHOR_IDS[:3])
    assert too_few.value.code == "SELECTION_POINT_COUNT"

    with pytest.raises(module.SelectionError) as too_many:
        _first_pass(module, catalog, ALL_IDS + ALL_IDS[:1])
    assert too_many.value.code == "SELECTION_POINT_COUNT"


def test_first_pass_binding_requires_every_anchor(tmp_path: Path) -> None:
    module = _selection_module()
    catalog = _write_catalog(tmp_path)

    with pytest.raises(module.SelectionError) as error:
        _first_pass(module, catalog, ANCHOR_IDS[:3] + SAMPLE_IDS[:1])
    assert error.value.code == "SELECTION_ANCHOR_MISSING"
    assert error.value.detail


def test_first_pass_binding_accepts_the_anchors_in_any_order(tmp_path: Path) -> None:
    module = _selection_module()
    catalog = _write_catalog(tmp_path)
    reordered = (ANCHOR_IDS[2], ANCHOR_IDS[0], SAMPLE_IDS[0], ANCHOR_IDS[3], ANCHOR_IDS[1])

    binding = _first_pass(module, catalog, reordered)

    assert binding.selected_point_ids == reordered


def test_first_pass_binding_refuses_unknown_and_duplicate_points(tmp_path: Path) -> None:
    module = _selection_module()
    catalog = _write_catalog(tmp_path)

    with pytest.raises(module.SelectionError) as unknown:
        _first_pass(module, catalog, ANCHOR_IDS + ("not_in_catalog",))
    assert unknown.value.code == "SELECTION_POINT_UNKNOWN"

    with pytest.raises(module.SelectionError) as duplicate:
        _first_pass(module, catalog, ANCHOR_IDS + (SAMPLE_IDS[0], SAMPLE_IDS[0]))
    assert duplicate.value.code == "SELECTION_POINT_DUPLICATE"


# --------------------------------------------------------------------------------------
# Catalog and selection hashes are the binding's identity
# --------------------------------------------------------------------------------------


def test_catalog_drift_and_tampering_are_refused(tmp_path: Path) -> None:
    module = _selection_module()
    catalog = _write_catalog(tmp_path)
    frozen = module.load_point_catalog(catalog).sha256

    with pytest.raises(module.SelectionError) as drift:
        _first_pass(
            module,
            catalog,
            ANCHOR_IDS + SAMPLE_IDS[:1],
            expected_catalog_sha256="e" * 64,
        )
    assert drift.value.code == "SELECTION_CATALOG_DRIFT"

    binding = _first_pass(
        module,
        catalog,
        ANCHOR_IDS + SAMPLE_IDS[:1],
        expected_catalog_sha256=frozen,
    )
    assert binding.catalog_sha256 == frozen

    document = _catalog_document()
    document["points"][4]["cup_position_world_m"] = [9.9, 9.9, 9.9]
    import yaml

    catalog.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    with pytest.raises(module.SelectionError) as replaced:
        _first_pass(
            module,
            catalog,
            ANCHOR_IDS + SAMPLE_IDS[:1],
            expected_catalog_sha256=frozen,
        )
    assert replaced.value.code == "SELECTION_CATALOG_DRIFT"


def test_selection_hash_covers_order_and_the_run_identity(tmp_path: Path) -> None:
    module = _selection_module()
    catalog = _write_catalog(tmp_path)
    point_ids = ANCHOR_IDS + SAMPLE_IDS[:2]

    base = _first_pass(module, catalog, point_ids)
    reordered = _first_pass(module, catalog, tuple(reversed(point_ids)))
    other_batch = _first_pass(module, catalog, point_ids, batch_id="batch-b")
    other_config = _first_pass(module, catalog, point_ids, config_sha256="f" * 64)
    other_closure = _first_pass(module, catalog, point_ids, runtime_closure_sha256="0" * 64)

    hashes = {
        base.selection_sha256,
        reordered.selection_sha256,
        other_batch.selection_sha256,
        other_config.selection_sha256,
        other_closure.selection_sha256,
    }
    assert len(hashes) == 5
    assert base.points[0].point_sha256 == reordered.points[-1].point_sha256


def test_invalid_hash_arguments_are_refused(tmp_path: Path) -> None:
    module = _selection_module()
    catalog = _write_catalog(tmp_path)

    with pytest.raises(module.SelectionError) as config:
        _first_pass(module, catalog, ANCHOR_IDS + SAMPLE_IDS[:1], config_sha256="short")
    assert config.value.code == "SELECTION_HASH_INVALID"

    with pytest.raises(module.SelectionError) as closure:
        _first_pass(module, catalog, ANCHOR_IDS + SAMPLE_IDS[:1], runtime_closure_sha256="")
    assert closure.value.code == "SELECTION_HASH_INVALID"


def test_binding_document_is_canonical_json(tmp_path: Path) -> None:
    module = _selection_module()
    catalog = _write_catalog(tmp_path)
    binding = _first_pass(module, catalog, ANCHOR_IDS + SAMPLE_IDS[:1])

    document = binding.as_document()

    assert json.loads(json.dumps(document, sort_keys=True)) == document
    assert document["catalog_sha256"] == binding.catalog_sha256
    assert [point["point_id"] for point in document["points"]] == list(
        binding.selected_point_ids
    )
    assert document["selection_sha256"] == binding.selection_sha256


# --------------------------------------------------------------------------------------
# Retry binding: exactly one committed business failure, with its source chain
# --------------------------------------------------------------------------------------


def _retry(module, catalog: Path, point_id: str, **overrides):
    arguments = {
        "catalog_path": catalog,
        "point_id": point_id,
        "original_selection_sha256": "1" * 64,
        "original_result_sha256": "2" * 64,
        "original_outcome": "FAILED",
        "campaign_id": "campaign-retry",
        "batch_id": "batch-retry",
        "config_sha256": CONFIG_SHA,
        "runtime_closure_sha256": CLOSURE_SHA,
    }
    arguments.update(overrides)
    return module.build_retry_selection(**arguments)


def test_retry_binding_takes_one_business_failed_point_without_anchor_rules(
    tmp_path: Path,
) -> None:
    module = _selection_module()
    catalog = _write_catalog(tmp_path)

    binding = _retry(module, catalog, SAMPLE_IDS[7])

    assert binding.point.point_id == SAMPLE_IDS[7]
    assert binding.original_selection_sha256 == "1" * 64
    assert binding.original_result_sha256 == "2" * 64
    assert binding.original_outcome == "FAILED"
    document = binding.as_document()
    assert document["point"]["point_id"] == SAMPLE_IDS[7]
    assert len(binding.selection_sha256) == 64


def test_retry_binding_refuses_a_non_business_failure(tmp_path: Path) -> None:
    module = _selection_module()
    catalog = _write_catalog(tmp_path)

    for outcome in ("PASSED", "INDETERMINATE", "INVALID", "UNRUN"):
        with pytest.raises(module.SelectionError) as error:
            _retry(module, catalog, SAMPLE_IDS[0], original_outcome=outcome)
        assert error.value.code == "RETRY_ORIGINAL_NOT_FAILED", outcome


def test_retry_binding_requires_the_full_source_chain(tmp_path: Path) -> None:
    module = _selection_module()
    catalog = _write_catalog(tmp_path)

    with pytest.raises(module.SelectionError) as selection:
        _retry(module, catalog, SAMPLE_IDS[0], original_selection_sha256="")
    assert selection.value.code == "RETRY_SOURCE_CHAIN_REQUIRED"

    with pytest.raises(module.SelectionError) as result:
        _retry(module, catalog, SAMPLE_IDS[0], original_result_sha256="not-a-hash")
    assert result.value.code == "RETRY_SOURCE_CHAIN_REQUIRED"


def test_retry_binding_refuses_an_unknown_point(tmp_path: Path) -> None:
    module = _selection_module()
    catalog = _write_catalog(tmp_path)

    with pytest.raises(module.SelectionError) as error:
        _retry(module, catalog, "not_in_catalog")
    assert error.value.code == "SELECTION_POINT_UNKNOWN"


def test_catalog_loader_refuses_a_malformed_document(tmp_path: Path) -> None:
    module = _selection_module()
    import yaml

    duplicate = _catalog_document()
    duplicate["points"].append(dict(duplicate["points"][0]))
    catalog = tmp_path / "catalog.yaml"
    catalog.write_text(yaml.safe_dump(duplicate, sort_keys=False), encoding="utf-8")
    with pytest.raises(module.SelectionError) as error:
        module.load_point_catalog(catalog)
    assert error.value.code == "SELECTION_CATALOG_INVALID"

    missing = tmp_path / "schema.yaml"
    missing.write_text(yaml.safe_dump({"points": []}, sort_keys=False), encoding="utf-8")
    with pytest.raises(module.SelectionError) as schema:
        module.load_point_catalog(missing)
    assert schema.value.code == "SELECTION_CATALOG_INVALID"
