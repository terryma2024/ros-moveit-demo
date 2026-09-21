"""One Worker lease executes exactly one hash-bound point (plan Task 3, design section 8).

The full installed catalog must never reach a Worker: the campaign turns one queue lease into one
immutable single-point file, the Worker reads that file's id and digest back before it runs the
batch, and a business result may only be committed once the station, MoveIt/physics decision,
evidence manifest and cleanup ownership are all durable. A missing implementation is reported as
a failed assertion rather than a collection error.
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
from pathlib import Path

import yaml

import pytest

from test_parallel_point_queue import _queue_module, _worker  # noqa: F401
from test_parallel_selection import (  # noqa: F401
    ALL_IDS,
    ANCHOR_IDS,
    CLOSURE_SHA,
    CONFIG_SHA,
    SAMPLE_IDS,
    _first_pass,
    _selection_module,
    _write_catalog,
)


def _input_module():
    spec = importlib.util.find_spec("so101_demo.parallel_batch.single_point_input")
    assert spec is not None, (
        "so101_demo.parallel_batch.single_point_input is not implemented yet"
    )
    return importlib.import_module("so101_demo.parallel_batch.single_point_input")


def _fixture(tmp_path: Path, point_ids=ALL_IDS):
    selection = _selection_module()
    queue_module = _queue_module()
    catalog = _write_catalog(tmp_path)
    binding = _first_pass(selection, catalog, point_ids)
    root = tmp_path / "batch"
    queue = queue_module.DurablePointQueue(root=root / "queue", binding=binding)
    return selection, queue_module, binding, queue, root


def _execute(module, binding, queue, worker, root: Path):
    lease = queue.lease_next(worker)
    assert lease is not None
    execution_input = module.write_single_point_input(
        binding=binding, lease=lease, root=root
    )
    return lease, execution_input


# --------------------------------------------------------------------------------------
# One lease -> one immutable point file
# --------------------------------------------------------------------------------------


def test_single_point_file_contains_exactly_the_leased_point(tmp_path: Path) -> None:
    module = _input_module()
    _selection, _queue_module_, binding, queue, root = _fixture(tmp_path, ANCHOR_IDS + SAMPLE_IDS[:2])
    worker = _worker(_queue_module_, "w1", "slot-0", generation=3)

    lease, execution_input = _execute(module, binding, queue, worker, root)

    assert execution_input.point_id == lease.point_id
    assert execution_input.attempt_id == lease.attempt_id
    assert execution_input.relative_points_path == f"points/{lease.point_id}.yaml"
    assert execution_input.points_sha256 == hashlib.sha256(
        (root / execution_input.relative_points_path).read_bytes()
    ).hexdigest()
    document = yaml.safe_load((root / execution_input.relative_points_path).read_text(encoding="utf-8"))
    assert document["schema_version"] == 1
    assert [point["id"] for point in document["points"]] == [lease.point_id]
    assert document["points"][0]["cup_position_world_m"] == list(
        next(point for point in binding.points if point.point_id == lease.point_id).position_xyz_m
    )
    assert execution_input.point_sha256 == next(
        point.point_sha256 for point in binding.points if point.point_id == lease.point_id
    )

    # Rewriting the same lease is idempotent: the bytes stay identical.
    again = module.write_single_point_input(binding=binding, lease=lease, root=root)
    assert again.points_sha256 == execution_input.points_sha256


def test_single_point_input_refuses_a_lease_outside_the_binding(tmp_path: Path) -> None:
    module = _input_module()
    selection = _selection_module()
    queue_module = _queue_module()
    catalog = _write_catalog(tmp_path)
    binding = _first_pass(selection, catalog, ANCHOR_IDS + SAMPLE_IDS[:1])
    queue = queue_module.DurablePointQueue(root=tmp_path / "queue", binding=binding)
    root = tmp_path / "batch"

    rejected = SAMPLE_IDS[4]
    forged = queue_module.PointLease(
        campaign_id=binding.campaign_id,
        batch_id=binding.batch_id,
        point_id=rejected,
        attempt_id=f"{rejected}-attempt-1",
        generation=1,
        worker_id="w1",
        slot_id="slot-0",
        point_sha256="a" * 64,
    )
    with pytest.raises(module.SinglePointInputError) as unselected:
        module.write_single_point_input(binding=binding, lease=forged, root=root)
    assert unselected.value.code == "SINGLE_POINT_LEASE_UNSELECTED"

    lease = queue.lease_next(_worker(queue_module, "w1", "slot-0"))
    assert lease is not None
    edited = queue_module.PointLease(
        campaign_id=lease.campaign_id,
        batch_id=lease.batch_id,
        point_id=lease.point_id,
        attempt_id=lease.attempt_id,
        generation=lease.generation,
        worker_id=lease.worker_id,
        slot_id=lease.slot_id,
        point_sha256="b" * 64,
    )
    with pytest.raises(module.SinglePointInputError) as mismatch:
        module.write_single_point_input(binding=binding, lease=edited, root=root)
    assert mismatch.value.code == "SINGLE_POINT_LEASE_MISMATCH"


def test_conflicting_existing_point_file_is_refused(tmp_path: Path) -> None:
    module = _input_module()
    _selection, queue_module, binding, queue, root = _fixture(tmp_path)
    lease, execution_input = _execute(
        module, binding, queue, _worker(queue_module, "w1", "slot-0"), root
    )

    path = root / execution_input.relative_points_path
    path.write_text("schema_version: 1\npoints: []\n", encoding="utf-8")
    with pytest.raises(module.SinglePointInputError) as conflict:
        module.write_single_point_input(binding=binding, lease=lease, root=root)
    assert conflict.value.code == "SINGLE_POINT_INPUT_CONFLICT"


# --------------------------------------------------------------------------------------
# The Worker read-back gate
# --------------------------------------------------------------------------------------


def test_readback_verifies_id_and_digest(tmp_path: Path) -> None:
    module = _input_module()
    _selection, queue_module, binding, queue, root = _fixture(tmp_path)
    lease, execution_input = _execute(
        module, binding, queue, _worker(queue_module, "w1", "slot-0"), root
    )
    path = root / execution_input.relative_points_path

    document = module.read_single_point_input(
        path,
        expected_sha256=execution_input.points_sha256,
        expected_point_id=lease.point_id,
    )
    assert [point["id"] for point in document["points"]] == [lease.point_id]

    with pytest.raises(module.SinglePointInputError) as drift:
        module.read_single_point_input(
            path, expected_sha256="f" * 64, expected_point_id=lease.point_id
        )
    assert drift.value.code == "SINGLE_POINT_INPUT_DRIFT"

    with pytest.raises(module.SinglePointInputError) as wrong_point:
        module.read_single_point_input(
            path,
            expected_sha256=execution_input.points_sha256,
            expected_point_id=SAMPLE_IDS[9],
        )
    assert wrong_point.value.code == "SINGLE_POINT_POINT_MISMATCH"

    path.write_text(
        "schema_version: 1\npoints:\n- id: a\n  cup_position_world_m: [0, 0, 0]\n"
        "- id: b\n  cup_position_world_m: [0, 0, 0]\n",
        encoding="utf-8",
    )
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(module.SinglePointInputError) as shape:
        module.read_single_point_input(
            path, expected_sha256=digest, expected_point_id="a"
        )
    assert shape.value.code == "SINGLE_POINT_INPUT_SHAPE"


def test_batch_argv_points_only_at_the_single_point_file(tmp_path: Path) -> None:
    module = _input_module()
    _selection, queue_module, binding, queue, root = _fixture(tmp_path)
    _lease, execution_input = _execute(
        module, binding, queue, _worker(queue_module, "w1", "slot-0"), root
    )

    argv = module.batch_argv(
        binary=Path("/prefix/lib/so101_demo_py/so101_mujoco_rgbd_batch"),
        execution_input=execution_input,
        root=root,
        batch_id="batch-a",
        session_id="station-a",
        evidence_root=root / "evidence",
        mujoco_pid=4242,
    )

    points_argv = argv[argv.index("--points") + 1]
    assert points_argv == str(root / execution_input.relative_points_path)
    assert "rgbd_task_points.yaml" not in " ".join(argv)
    assert argv[argv.index("--mujoco-pid") + 1] == "4242"
    assert argv[argv.index("--batch-id") + 1] == "batch-a"


def test_retry_input_contains_only_the_failed_point(tmp_path: Path) -> None:
    module = _input_module()
    selection = _selection_module()
    queue_module = _queue_module()
    catalog = _write_catalog(tmp_path)
    retry = selection.build_retry_selection(
        catalog_path=catalog,
        point_id=SAMPLE_IDS[3],
        original_selection_sha256="1" * 64,
        original_result_sha256="2" * 64,
        original_outcome="FAILED",
        campaign_id="campaign-retry",
        batch_id="batch-retry",
        config_sha256=CONFIG_SHA,
        runtime_closure_sha256=CLOSURE_SHA,
    )
    root = tmp_path / "retry"
    queue = queue_module.DurablePointQueue(root=root / "queue", binding=retry)

    lease = queue.lease_next(_worker(queue_module, "w1", "slot-0"))
    assert lease is not None
    execution_input = module.write_single_point_input(binding=retry, lease=lease, root=root)

    document = yaml.safe_load((root / execution_input.relative_points_path).read_text(encoding="utf-8"))
    assert [point["id"] for point in document["points"]] == [SAMPLE_IDS[3]]
    assert execution_input.point_id == SAMPLE_IDS[3]

    forged = queue_module.PointLease(
        campaign_id=retry.campaign_id,
        batch_id=retry.batch_id,
        point_id=ANCHOR_IDS[0],
        attempt_id=f"{ANCHOR_IDS[0]}-attempt-1",
        generation=1,
        worker_id="w1",
        slot_id="slot-0",
        point_sha256="a" * 64,
    )
    with pytest.raises(module.SinglePointInputError) as unselected:
        module.write_single_point_input(binding=retry, lease=forged, root=root)
    assert unselected.value.code == "SINGLE_POINT_LEASE_UNSELECTED"


# --------------------------------------------------------------------------------------
# A business result needs the whole durability chain
# --------------------------------------------------------------------------------------


def _result_arguments(module, lease, *, complete: bool = True):
    manifest = "evidence/point-result.json"
    arguments = {
        "lease_identity": lease.identity,
        "point_id": lease.point_id,
        "attempt_id": lease.attempt_id,
        "outcome": "FAILED",
        "business_decision": "FAILED",
        "evidence_manifest_relative_path": manifest,
        "evidence_manifest_sha256": hashlib.sha256(b"manifest").hexdigest(),
        "station_ready": True,
        "moveit_executed": True,
        "cleanup_owned": True,
    }
    if not complete:
        arguments["station_ready"] = False
    return arguments


def test_business_result_requires_the_durable_chain(tmp_path: Path) -> None:
    module = _input_module()
    _selection, queue_module, binding, queue, root = _fixture(tmp_path)
    lease, _input = _execute(
        module, binding, queue, _worker(queue_module, "w1", "slot-0"), root
    )

    with pytest.raises(module.SinglePointInputError) as incomplete:
        module.PointExecutionResult(**_result_arguments(module, lease, complete=False))
    assert incomplete.value.code == "POINT_RESULT_DURABILITY_INCOMPLETE"

    with pytest.raises(module.SinglePointInputError) as invalid:
        module.PointExecutionResult(
            **{**_result_arguments(module, lease), "outcome": "INVALID"}
        )
    assert invalid.value.code == "POINT_RESULT_OUTCOME_INVALID"

    result = module.PointExecutionResult(**_result_arguments(module, lease))
    document = result.as_document()
    assert json.loads(json.dumps(document, sort_keys=True)) == document
    assert document["point_id"] == lease.point_id
    assert document["attempt_id"] == lease.attempt_id
    assert list(document["lease_identity"]) == list(lease.identity)


# --------------------------------------------------------------------------------------
# Worker wiring: the installed catalog is never an input
# --------------------------------------------------------------------------------------


def test_worker_lease_document_carries_the_single_point_input(tmp_path: Path) -> None:
    from so101_demo.cli.macos_w2_campaign import lease_worker_execution

    selection = _selection_module()
    queue_module = _queue_module()
    module = _input_module()
    catalog = _write_catalog(tmp_path)
    binding = _first_pass(selection, catalog, ANCHOR_IDS + SAMPLE_IDS[:2])
    root = tmp_path / "campaign"
    queue = queue_module.DurablePointQueue(root=root / "queue", binding=binding)

    first = lease_worker_execution(
        queue=queue, binding=binding, worker_id="w1", slot_id="slot-0",
        evidence_root=root, input_sha256="a" * 64,
    )
    second = lease_worker_execution(
        queue=queue, binding=binding, worker_id="w2", slot_id="slot-1",
        evidence_root=root, input_sha256="a" * 64,
    )

    assert first["point_id"] != second["point_id"]
    assert {first["point_id"], second["point_id"]} <= set(binding.selected_point_ids)
    for lease_document in (first, second):
        points_path = Path(lease_document["points_path"])
        assert points_path.is_file()
        assert "rgbd_task_points.yaml" not in str(points_path)
        document = yaml.safe_load(points_path.read_text(encoding="utf-8"))
        assert [point["id"] for point in document["points"]] == [lease_document["point_id"]]
        assert lease_document["points_sha256"] == hashlib.sha256(
            points_path.read_bytes()
        ).hexdigest()
        assert lease_document["attempt_id"] in lease_document["attempt_ids"]
        on_disk = json.loads(Path(lease_document["lease_path"]).read_text(encoding="utf-8"))
        assert on_disk["points_path"] == lease_document["points_path"]


def test_worker_pick_place_requires_the_single_point_input(tmp_path: Path) -> None:
    module = _input_module()
    _selection, queue_module, binding, queue, root = _fixture(tmp_path)
    lease, execution_input = _execute(
        module, binding, queue, _worker(queue_module, "w1", "slot-0"), root
    )

    binary = tmp_path / "so101_mujoco_rgbd_batch"
    binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    binary.chmod(0o755)

    request = module.pick_place_request(
        lease_document={
            "points_path": str(root / execution_input.relative_points_path),
            "points_sha256": execution_input.points_sha256,
            "point_id": execution_input.point_id,
            "attempt_id": execution_input.attempt_id,
        },
        batch_binary=binary,
        session_id="station-a",
        evidence_root=root / "evidence",
        mujoco_pid=4242,
    )
    assert request["requested"] is True
    assert request["points"] == str(root / execution_input.relative_points_path)
    assert "rgbd_task_points.yaml" not in " ".join(request["argv"])

    refused = module.pick_place_request(
        lease_document={"point_id": lease.point_id, "attempt_id": lease.attempt_id},
        batch_binary=binary,
        session_id="station-a",
        evidence_root=root / "evidence",
        mujoco_pid=4242,
    )
    assert refused["requested"] is False
    assert refused["error"] == "POINTS_PATH_MISSING"
