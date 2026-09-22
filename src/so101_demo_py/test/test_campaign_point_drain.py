"""The campaign body drains the durable shared queue: one lease, one point (design section 8).

Task 11's live gate found the gap this module exists to close. The campaign reported
`W2_CAMPAIGN_PASS` / `N1_CAMPAIGN_PASS` while `per_slot_pick_place.*.executed_points` was `[]` and
every Worker reported `pick_place.requested=false` with `error=POINTS_PATH_MISSING`: the lease the
campaign wrote carried no `points_path`/`points_sha256`, so `single_point_input.pick_place_request`
refused it and no point was ever executed. Nothing in the campaign body leased a point from the
durable queue at all.

These tests pin the wiring that closes it:

* the campaign-body lease is the queue's lease, with the single-point input the Worker reads back;
* a two-Worker drain executes every selected point exactly once and nothing else, and the journal
  carries the canonical committed events under a published watermark;
* a point whose evidence chain is incomplete is recorded as an infrastructure failure rather than
  committed as a business result or silently skipped;
* a v5 retry binding can only lease the one business `FAILED` point it references.

The module under test is imported lazily so a missing implementation is reported as a failed
assertion instead of a collection error.
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import time
from pathlib import Path

import pytest

import yaml

from test_parallel_point_queue import _queue_module  # noqa: F401 - shared queue helpers
from test_parallel_selection import (  # noqa: F401 - shared catalog fixtures
    ANCHOR_IDS,
    _first_pass,
    _selection_module,
)

from so101_demo.parallel_batch.w1_composition import exact_w1_slots
from so101_demo.parallel_batch.w2_composition import exact_w2_slots

#: The Task 11 selection ids, plus the anchors the first-pass binding contract requires.
TASK11_IDS = ("cup_test_left_5cm", "sample_07_mid_center", "sample_12_far_left",
              "sample_16_far_right")


def _drain_module():
    spec = importlib.util.find_spec("so101_demo.parallel_batch.point_drain")
    assert spec is not None, (
        "so101_demo.parallel_batch.point_drain is not implemented yet: the campaign body still "
        "does not lease points from the durable queue"
    )
    return importlib.import_module("so101_demo.parallel_batch.point_drain")


def _input_module():
    spec = importlib.util.find_spec("so101_demo.parallel_batch.single_point_input")
    assert spec is not None, "single_point_input is not implemented yet"
    return importlib.import_module("so101_demo.parallel_batch.single_point_input")


def _cli():
    spec = importlib.util.find_spec("so101_demo.cli.macos_w2_campaign")
    assert spec is not None, "the W2 campaign entry point is not implemented yet"
    return importlib.import_module("so101_demo.cli.macos_w2_campaign")


def _batch_binary(tmp_path: Path) -> Path:
    binary = tmp_path / "so101_mujoco_rgbd_batch"
    binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    binary.chmod(0o755)
    return binary


def _selected(point_ids=TASK11_IDS) -> tuple[str, ...]:
    """The Task 11 ids, ordered after the four anchors the first-pass binding requires."""

    return ANCHOR_IDS + tuple(point_id for point_id in point_ids if point_id not in ANCHOR_IDS)


def _catalog_copy(tmp_path: Path) -> Path:
    """The installed 20-point catalog, so the selection ids are the real ones."""

    source = (Path(__file__).resolve().parents[1]
              / "config/mujoco/moveit_expert_validation_points_v1.yaml")
    target = tmp_path / source.name
    target.write_bytes(source.read_bytes())
    return target


def _binding_and_queue(tmp_path: Path, point_ids=None):
    selection = _selection_module()
    queue_module = _queue_module()
    catalog = _catalog_copy(tmp_path)
    binding = _first_pass(selection, catalog, _selected() if point_ids is None else point_ids)
    queue = queue_module.DurablePointQueue(root=tmp_path / "queue", binding=binding)
    return binding, queue, catalog


class _Plan:
    """The capacity-only plan the campaign body records; it owns no point."""

    slots = exact_w2_slots()
    selected_point_ids = _selected()
    execution_profile = "MPS_W2_FIRST_PASS"
    batch_kind = "FIRST_PASS"
    schema_version = 4


class _W1Plan(_Plan):
    slots = exact_w1_slots()
    execution_profile = "MPS_W1_FIRST_PASS"
    batch_kind = "FIRST_PASS"
    schema_version = 6


# --------------------------------------------------------------------------------------
# The gap, reproduced at the boundary the Worker reads
# --------------------------------------------------------------------------------------


def test_a_lease_without_a_single_point_input_is_refused_by_name(tmp_path: Path) -> None:
    """`POINTS_PATH_MISSING` is what the Task 11 leases produced, and it is never a pass.

    This is the exact refusal the live campaign hid behind a `*_CAMPAIGN_PASS`: the Worker reads
    `points_path`/`points_sha256` back out of its lease document, and a lease without them cannot
    execute anything.
    """

    module = _input_module()
    request = module.pick_place_request(
        lease_document={"point_id": "p1", "attempt_id": "p1-attempt-1"},
        batch_binary=_batch_binary(tmp_path), session_id="station", evidence_root=tmp_path,
    )

    assert request == {"requested": False, "error": "POINTS_PATH_MISSING"}


# --------------------------------------------------------------------------------------
# The campaign body leases from the durable queue
# --------------------------------------------------------------------------------------


def test_campaign_lease_builder_leases_executable_points_from_the_queue(tmp_path: Path) -> None:
    """Every lease the campaign body builds carries one hash-bound, executable point.

    RED on the pre-fix tree: the capacity lease builder takes no queue at all, so the campaign
    leases zero points, and every lease it does write is refused with `POINTS_PATH_MISSING`.
    """

    cli = _cli()
    binding, queue, _catalog = _binding_and_queue(tmp_path)
    binary = _batch_binary(tmp_path)
    arguments = {
        "plan": _Plan(), "batch_id": binding.batch_id, "evidence_root": tmp_path,
        "input_sha256": "a" * 64, "binding": binding, "queue": queue,
    }

    leases = cli.build_worker_leases(**arguments)

    assert sorted(leases) == ["w1", "w2"]
    snapshot = queue.snapshot()
    assert len(snapshot.active_leases) == 2, (
        "the campaign body leased no point from the durable queue"
    )
    assert {lease.point_id for lease in snapshot.active_leases} == {
        lease["point_id"] for lease in leases.values()}
    for document in leases.values():
        request = _input_module().pick_place_request(
            lease_document=document, batch_binary=binary, session_id="station-a",
            evidence_root=tmp_path / "evidence")
        assert request["requested"] is True, request
        points = yaml.safe_load(Path(request["points"]).read_text(encoding="utf-8"))["points"]
        assert [point["id"] for point in points] == [document["point_id"]]
        assert document["points_sha256"] == hashlib.sha256(
            Path(request["points"]).read_bytes()).hexdigest()
        assert "rgbd_task_points.yaml" not in " ".join(request["argv"])

    # Asking again for the same slots and generation returns the same lease: a Worker re-spawned
    # into the same generation can never execute a second, different point.
    again = cli.build_worker_leases(**arguments)
    assert {document["point_id"] for document in again.values()} == {
        document["point_id"] for document in leases.values()}
    assert len(queue.snapshot().active_leases) == 2

    # Once those two leases are committed, a new generation for one slot leases the next pending
    # point - and only a selected one.
    committed = {lease.point_id for document in leases.values() for lease in []}
    for lease in snapshot.active_leases:
        queue.commit_result(
            lease, _queue_module().CommittedResult(
                point_id=lease.point_id, attempt_id=lease.attempt_id, outcome="PASSED",
                evidence_sha256="e" * 64, result_sha256="f" * 64),
            worker=_queue_module().WorkerIdentity(
                worker_id=lease.worker_id, slot_id=lease.slot_id, generation=lease.generation))
        committed.add(lease.point_id)
    third = cli.build_worker_leases(**{**arguments, "worker_ids": ("w1",), "generation": 2})
    assert third["w1"]["point_id"] not in committed
    assert third["w1"]["point_id"] in binding.selected_point_ids


# --------------------------------------------------------------------------------------
# The drain: every selected point exactly once, nothing else
# --------------------------------------------------------------------------------------


def _fabricate_worker_evidence(*, pick_root: Path, batch_id: str, point_id: str,
                               status: str = "SUCCEEDED", failure_code=None,
                               dynamic: bool = True) -> dict:
    """Write the evidence tree a real batch run produces, and report it the way it does.

    The shape mirrors `application/task_batch.py`: one batch root, one point root under it, a
    `point-result.json` terminal document, and the dynamic execution manifest beside it.
    """

    point_root = pick_root / "batches" / batch_id / "points" / f"01-{point_id}"
    point_root.mkdir(parents=True, exist_ok=True)
    manifest = point_root / "point-result.json"
    manifest.write_text(json.dumps({
        "id": point_id, "status": status, "failure_code": failure_code,
        "reachability_status": "REACHABLE" if dynamic else None, "reset_epoch": 1,
        "artifacts": [{"kind": "workflow", "path": "dynamic/dynamic-execute-manifest.json"}],
        "manifest_path": "dynamic/dynamic-execute-manifest.json"}), encoding="utf-8")
    relative = manifest.relative_to(pick_root).as_posix()
    dynamic_sha = None
    if dynamic:
        dynamic_manifest = point_root / "dynamic" / "dynamic-execute-manifest.json"
        dynamic_manifest.parent.mkdir(parents=True, exist_ok=True)
        dynamic_manifest.write_text(json.dumps({
            "current_state": "DONE" if status == "SUCCEEDED" else "FAILED",
            "failure": None if status == "SUCCEEDED" else {"code": failure_code},
            "final_samples": [{"simulation_step": 33, "table_contact": True,
                               "maximum_normal_force_n": 0.233}]}), encoding="utf-8")
        dynamic_sha = hashlib.sha256(dynamic_manifest.read_bytes()).hexdigest()
    return {
        "requested": True, "exit_code": 0 if status == "SUCCEEDED" else 1,
        "point_id": point_id, "evidence_root": str(pick_root),
        "points_sha256": "b" * 64,
        "evidence_manifest_relative_path": relative,
        "evidence_manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        "dynamic_manifest_sha256": dynamic_sha,
    }


def _fake_spawn(*, drain, binding, evidence_root: Path, binary: Path, calls: list,
                status: str = "SUCCEEDED", with_evidence: bool = True):
    """A stand-in for `cli/macos_w2_worker.py`: it reads the lease and writes its result.

    It performs the same readback the Worker performs (`pick_place_request`), refuses a lease it
    cannot execute, and writes its result document - so a drain driven through it is driven
    through the real contract rather than a mock of it.
    """

    def spawn(worker_id: str, slot_id: str, generation: int, lease_document: dict):
        request = _input_module().pick_place_request(
            lease_document=lease_document, batch_binary=binary,
            session_id=f"{worker_id}-station", evidence_root=evidence_root / "pick",
            mujoco_pid=4242)
        assert request["requested"] is True, request
        assert request["point_id"] == lease_document["point_id"]
        calls.append((worker_id, slot_id, generation, lease_document["point_id"]))
        station_root = drain.station_root_for(
            evidence_root=evidence_root, worker_id=worker_id,
            attempt_id=lease_document["attempt_id"])
        pick_root = station_root / "pick"
        if with_evidence:
            pick_place = _fabricate_worker_evidence(
                pick_root=pick_root, batch_id=binding.batch_id,
                point_id=lease_document["point_id"], status=status,
                failure_code=None if status == "SUCCEEDED" else "TERMINAL_CAPTURE_FAILED")
        else:
            pick_place = {"requested": True, "exit_code": 1, "evidence_root": str(pick_root)}
        result_path = evidence_root / f"{worker_id}-result-{lease_document['attempt_id']}.json"
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(json.dumps({
            "worker_id": worker_id, "pid": 1000 + len(calls),
            "station_record": {"requested": True, "ready": {
                "ready": True, "exit_code": 0, "ros_domain_id": "181"}},
            "pick_place": pick_place, "results": [],
            "execution_profile": lease_document.get("execution_profile"),
            "batch_kind": lease_document.get("batch_kind"),
            "schema_version": lease_document.get("schema_version")}), encoding="utf-8")
        return drain.WorkerRun(
            worker_id=worker_id, slot_id=slot_id, generation=generation, pid=1000 + len(calls),
            status="ACTIVE", result_path=result_path, station_root=str(station_root))

    return spawn


def _drain(tmp_path: Path, *, point_ids=None, worker_ids=("w1", "w2"),
           slot_ids=("slot-0", "slot-1"), journal=None, max_points=None, status="SUCCEEDED",
           with_evidence=True):
    """Drive the real drain over a real queue with a stand-in Worker process."""

    drain = _drain_module()
    cli = _cli()
    binding, queue, _catalog = _binding_and_queue(tmp_path, point_ids)
    evidence_root = tmp_path / "campaign"
    binary = _batch_binary(tmp_path)
    drain.write_selection_document(evidence_root=evidence_root, binding=binding,
                                   catalog_path=_catalog)
    calls: list = []
    report = drain.drain_point_queue(
        queue=queue, binding=binding, worker_ids=worker_ids, slot_ids=slot_ids,
        evidence_root=evidence_root, journal=journal, max_points=max_points,
        lease_point=lambda worker_id, slot_id, generation: cli.lease_worker_execution(
            queue=queue, binding=binding, worker_id=worker_id, slot_id=slot_id,
            generation=generation, evidence_root=evidence_root, input_sha256="a" * 64,
            lease_name=f"{worker_id}-lease-{int(generation):02d}.json"),
        spawn_worker=_fake_spawn(drain=drain, binding=binding, evidence_root=evidence_root,
                                 binary=binary, calls=calls, status=status,
                                 with_evidence=with_evidence),
        release_worker=lambda worker_id, slot_id: "EXITED")
    return drain, binding, queue, evidence_root, report, calls


def test_two_worker_drain_executes_every_selected_point_exactly_once(tmp_path: Path) -> None:
    """Two Workers drain one queue: each selected point once, both slots used, no extra point."""

    from so101_demo.parallel_batch.journal import CoordinatorJournal

    journal = CoordinatorJournal.create(tmp_path / "journal", "batch-a")
    try:
        _drain_module_, binding, queue, _evidence_root, report, calls = _drain(
            tmp_path, journal=journal)
        watermark = journal.read_watermark()
    finally:
        journal.close()

    summary = report.summary(selected_point_ids=binding.selected_point_ids)
    assert report.stop_reason is None, report.stop_reason
    assert summary["complete"] is True, summary
    assert summary["committed"] == {point_id: "PASSED"
                                    for point_id in binding.selected_point_ids}
    assert summary["unexecuted_point_ids"] == []
    assert summary["unselected_attempts"] == []
    assert summary["duplicate_attempts"] == []
    assert set(summary["workers"]) == {"w1", "w2"}
    assert sorted(point_id for _worker, _slot, _generation, point_id in calls) == sorted(
        binding.selected_point_ids)
    snapshot = queue.snapshot()
    assert snapshot.pending_point_ids == ()
    assert len(snapshot.results) == len(binding.selected_point_ids)
    assert snapshot.active_leases == ()

    # The canonical committed events are in the journal, and the published watermark covers them.
    assert watermark is not None
    replay = CoordinatorJournal.read_committed_prefix(tmp_path / "journal", "batch-a", watermark)
    assert replay.unconfirmed_durability is False
    events = [event.type for event in replay.events]
    selected_count = len(binding.selected_point_ids)
    assert events.count("POINT_LEASED") == selected_count
    assert events.count("ATTEMPT_STARTED") == selected_count
    assert events.count("RESULT_COMMITTED") == selected_count
    assert events.count("POINT_TERMINAL") == selected_count
    terminal_points = {
        event.payload["point_id"] for event in replay.events if event.type == "POINT_TERMINAL"}
    assert terminal_points == set(binding.selected_point_ids)


def test_drain_records_an_incomplete_evidence_chain_as_infrastructure(tmp_path: Path) -> None:
    """A point whose manifest never appeared is an honest infrastructure failure, never a pass.

    It must not be committed as a business result, must not be re-leased into a second execution,
    and must leave the campaign's own summary incomplete.
    """

    _drain_module, binding, queue, _evidence_root, report, _calls = _drain(
        tmp_path, worker_ids=("w1",), slot_ids=("slot-0",), with_evidence=False)

    summary = report.summary(selected_point_ids=binding.selected_point_ids)
    assert report.stop_reason == "POINT_EVIDENCE_MISSING"
    assert summary["complete"] is False
    assert summary["infrastructure_failures"][0]["point_id"] == binding.selected_point_ids[0]
    assert summary["committed"] == {}
    assert summary["unexecuted_point_ids"] == list(binding.selected_point_ids)
    # nothing was committed as a business result and nothing was executed twice
    assert queue.snapshot().results == ()
    assert len(report.attempts) == 1


def test_drain_commits_a_business_failure_with_its_evidence(tmp_path: Path) -> None:
    """A failed point is a legitimate terminal outcome - and it keeps its manifest."""

    _drain_module, binding, queue, evidence_root, report, _calls = _drain(
        tmp_path, worker_ids=("w1",), slot_ids=("slot-0",), status="FAILED", max_points=1)

    summary = report.summary(selected_point_ids=binding.selected_point_ids)
    assert report.stop_reason is None
    committed = queue.snapshot().results
    assert len(committed) == 1 and committed[0].outcome == "FAILED"
    assert summary["committed"] == {committed[0].point_id: "FAILED"}
    attempt = report.attempts[0]
    assert attempt.failure_code == "TERMINAL_CAPTURE_FAILED"
    manifest = evidence_root / attempt.evidence_manifest_relative_path
    assert manifest.is_file()
    assert hashlib.sha256(manifest.read_bytes()).hexdigest() == attempt.evidence_manifest_sha256
    # the per-point committed document the retry chain reads is durable too
    committed_document = json.loads(
        (evidence_root / "point-results" / f"{attempt.point_id}.json").read_text(encoding="utf-8"))
    assert committed_document["outcome"] == "FAILED"
    assert committed_document["attempt_id"] == attempt.attempt_id


def test_drain_stops_when_a_worker_exits_without_a_result(tmp_path: Path) -> None:
    """A Worker that died before writing its result is an infrastructure failure, not a hang."""

    drain = _drain_module()
    cli = _cli()
    binding, queue, _catalog = _binding_and_queue(tmp_path)
    evidence_root = tmp_path / "campaign"
    binary = _batch_binary(tmp_path)
    drain.write_selection_document(evidence_root=evidence_root, binding=binding,
                                   catalog_path=_catalog)

    class _DeadSpawn:
        def __init__(self):
            self.runs = []

        def __call__(self, worker_id, slot_id, generation, lease_document):
            run = drain.WorkerRun(
                worker_id=worker_id, slot_id=slot_id, generation=generation, pid=4242,
                status="ACTIVE", result_path=evidence_root / "never-written.json",
                station_root=str(drain.station_root_for(
                    evidence_root=evidence_root, worker_id=worker_id,
                    attempt_id=lease_document["attempt_id"])))
            self.runs.append(run)
            return run

    report = drain.drain_point_queue(
        queue=queue, binding=binding, worker_ids=("w1",), slot_ids=("slot-0",),
        evidence_root=evidence_root,
        lease_point=lambda worker_id, slot_id, generation: cli.lease_worker_execution(
            queue=queue, binding=binding, worker_id=worker_id, slot_id=slot_id,
            generation=generation, evidence_root=evidence_root, input_sha256="a" * 64),
        spawn_worker=_DeadSpawn(), release_worker=lambda worker_id, slot_id: "EXITED",
        worker_alive=lambda run: False)

    summary = report.summary(selected_point_ids=binding.selected_point_ids)
    assert report.stop_reason == "WORKER_EXITED_WITHOUT_RESULT"
    assert summary["complete"] is False
    assert summary["infrastructure_failures"][0]["infrastructure_code"] == \
        "WORKER_EXITED_WITHOUT_RESULT"
    assert queue.snapshot().results == ()
    # The point is left leased, not re-leased into a second execution.
    assert [lease.point_id for lease in queue.snapshot().active_leases] == [
        binding.selected_point_ids[0]]


def test_a_second_lease_for_one_slot_never_replays_a_bound_request_id(tmp_path: Path) -> None:
    """The task 11 defeat: the two inference probe ids were fixed per Worker.

    The campaign binds every id in the one-time table before each spawn, so a second lease for the
    same slot that re-derived `w1-att-01` was refused with `REQUEST_DUPLICATE` and took the whole
    campaign down mid-drain. Every id one lease carries must be generation-scoped.
    """

    cli = _cli()
    drain = _drain_module()
    binding, queue, _catalog = _binding_and_queue(tmp_path)
    arguments = {"plan": _Plan(), "batch_id": binding.batch_id, "evidence_root": tmp_path,
                 "input_sha256": "a" * 64, "binding": binding, "queue": queue}

    first = cli.build_worker_leases(**arguments)
    second = cli.build_worker_leases(**{**arguments, "worker_ids": ("w1",), "generation": 2})

    first_ids = set(first["w1"]["attempt_ids"])
    second_ids = set(second["w1"]["attempt_ids"])
    assert first_ids & second_ids == set(), (first_ids, second_ids)
    # and the round-trip ids the Worker derives are generation-scoped for the same reason
    assert drain.worker_progress_request_id(worker_id="w1", generation=1, index=0) != \
        drain.worker_progress_request_id(worker_id="w1", generation=2, index=0)
    assert drain.worker_probe_attempt_id(worker_id="w1", generation=1, index=1) in first_ids
    assert len(first_ids) == len(first["w1"]["attempt_ids"])


def test_a_station_that_outlived_its_worker_is_stopped_by_its_own_argv(tmp_path: Path) -> None:
    """A killed Worker never runs its `finally`, so its station must be reconciled exactly."""

    cli = _cli()
    root = tmp_path / "w1-station" / "task_start-attempt-1"
    other = tmp_path / "someone-elses-station"
    lines = [
        f"  101  101 /usr/bin/python ros2 launch so101_demo_py "
        f"so101_mujoco_task_station.launch.py task_evidence_root:={root} include_teleop:=false",
        f"  102  101 /usr/bin/python ros2_control_node --params-file {root}/params.yaml",
        f"  201  201 /usr/bin/python ros2 launch so101_demo_py "
        f"so101_mujoco_task_station.launch.py task_evidence_root:={other}",
    ]

    class _Completed:
        stdout = "\n".join(lines)

    def runner(_command):
        return _Completed()

    matches = cli.station_processes(str(root), ps_runner=runner)
    # only the launch that declares *this* station root is a match; its child is not a launcher
    assert matches == [{"pid": 101, "pgid": 101, "command": matches[0]["command"]}]
    assert "task_evidence_root:=" + str(root) in matches[0]["command"]

    signalled: list[tuple[int, int]] = []
    alive = {"station": True}

    def sender(target, number):
        signalled.append((target, number))
        alive["station"] = False

    def ps_runner(_command):
        if alive["station"]:
            return _Completed()
        class _Empty:
            stdout = ""
        return _Empty()

    stopped = cli.stop_station_residue(str(root), ps_runner=ps_runner, signal_sender=sender,
                                       sleep=lambda _seconds: None)
    assert stopped["clear"] is True
    assert stopped["stopped"] == [101]
    # the group leader is signalled as a group (its station's own group), never a stranger
    assert signalled and signalled[0] == (-101, __import__("signal").SIGINT)
    assert all(target != 201 and target != -201 for target, _number in signalled)


def test_every_served_response_is_admitted_immediately_so_the_table_stays_bounded() -> None:
    """The one-time table bounds *outstanding* requests; a drain must not fill it and stop.

    The first seven-point W2 drain issued six leases and then failed with `REGISTRY_CAPACITY`: every
    response was admitted only at the end of the campaign, so the pending set grew with every spawn.
    Admitting each response as it is served keeps the table's semantics and its bound.
    """

    cli = _cli()
    from so101_demo.parallel_batch.inference_registry import InferenceRegistry

    class _Campaign:
        """`MacosW2Campaign.admit_response`, over a real registry with a tiny capacity."""

        def __init__(self):
            self.registry = InferenceRegistry(campaign_id="c", capacity=2)

        def admit_response(self, request_id, *, broker_pid, broker_birth_identity, **_kwargs):
            return self.registry.consume_result(
                request_id, broker_pid=broker_pid, broker_birth_identity=broker_birth_identity)

        def bind(self, request_id):
            return self.registry.register_request(
                request_id=request_id, slot_id="slot-0", point_id="p1", attempt=1,
                model_id="yolo", input_sha256="a" * 64,
                deadline_monotonic_ns=time.monotonic_ns() + 60_000_000_000,
                broker_pid=4242, broker_birth_identity=17)

    campaign = _Campaign()
    served: list = []
    for index in range(6):
        request_id = f"w1-att-g{index:02d}-01-yolo"
        campaign.bind(request_id)
        assert cli.serve_and_admit(campaign, request_id=request_id, candidates=1, device="mps",
                                   served=served, broker_pid=4242,
                                   broker_birth_identity=17) is None
    admitted, refused = cli.served_admission_split(served)
    assert len(admitted) == 6 and refused == []

    # a response the table will not admit is refused to the caller, never recorded as admitted
    campaign.bind("late-yolo")
    campaign.registry.consume_result("late-yolo", broker_pid=4242, broker_birth_identity=17)
    refusal = cli.serve_and_admit(campaign, request_id="late-yolo", candidates=1, device="mps",
                                  served=served, broker_pid=4242, broker_birth_identity=17)
    assert refusal["error"]["code"] == "RESULT_NOT_ADMITTED"
    admitted, refused = cli.served_admission_split(served)
    assert [entry["request_id"] for entry in refused] == ["late-yolo"]


def test_the_per_slot_summary_reads_the_per_attempt_station_evidence(tmp_path: Path) -> None:
    """One station root per lease: the slot summary must read them, not a single fixed `pick` root."""

    cli = _cli()
    root = tmp_path
    for attempt, point_id in (("task_start-attempt-1", "task_start"),
                              ("cup_test_left_5cm-attempt-2", "cup_test_left_5cm")):
        point_root = (root / "w1-station" / attempt / "pick" / "batches" / "b1" / "points"
                      / f"01-{point_id}")
        (point_root / "dynamic").mkdir(parents=True)
        (point_root / "dynamic" / "dynamic-execute-manifest.json").write_text(json.dumps(
            {"current_state": "DONE", "failure": None,
             "final_samples": [{"simulation_step": 33, "table_contact": True,
                                "maximum_normal_force_n": 0.233}]}))
        (point_root / "point-result.json").write_text(json.dumps(
            {"id": point_id, "status": "SUCCEEDED", "failure_code": None}))

    summary = cli.summarize_per_slot_pick_place(evidence_root=root, workers=("w1",))

    assert summary["w1"]["manifests"] == 2
    assert summary["w1"]["point_results"] == 2
    assert summary["w1"]["executed_points"] == ["01-cup_test_left_5cm", "01-task_start"]
    assert {contact["point_id"] for contact in summary["w1"]["contacts"]} == {
        "task_start", "cup_test_left_5cm"}


def test_the_worker_reads_its_lease_before_it_uses_it() -> None:
    """The Worker is a script; a lease read placed after its first use is a NameError at runtime.

    That is exactly how the first re-run died: the station came up, the Worker crashed on
    `lease_document`, and its station was left running. The read must precede the identity it
    fills, and the whole post-station body must sit under one `try/finally`.
    """

    source = (Path(__file__).resolve().parents[1] / "src/cli/macos_w2_worker.py").read_text()
    assignment = source.index("lease_document = json.loads(")
    first_use = source.index("lease_identity = {name: lease_document.get(name)")
    assert assignment < first_use
    station_shutdown = source.index("station.shutdown()")
    guard = source.index("\ntry:\n    infer_results = []")
    assert guard < station_shutdown, "the infer block must be inside the station's try/finally"
    assert "worker_progress_request_id" in source


# --------------------------------------------------------------------------------------
# The v5 retry binding can only lease the one business FAILED point it references
# --------------------------------------------------------------------------------------


def _committed_failed_point(tmp_path: Path):
    return _drain(tmp_path, worker_ids=("w1",), slot_ids=("slot-0",), status="FAILED",
                  max_points=1)


def test_retry_source_requires_a_committed_business_failure(tmp_path: Path) -> None:
    drain = _drain_module()
    _drain_module_, binding, _queue, prior_root, report, _calls = _committed_failed_point(tmp_path)
    point_id = report.attempts[0].point_id

    source = drain.read_retry_source(
        prior_root=prior_root, point_id=point_id,
        selection_document_path=prior_root / "selection-binding.json")

    assert source["original_outcome"] == "FAILED"
    assert source["original_selection_sha256"] == binding.selection_sha256
    assert source["original_result_sha256"] == hashlib.sha256(
        (prior_root / "point-results" / f"{point_id}.json").read_bytes()).hexdigest()

    # A selected point that never produced a committed result cannot be retried ...
    unrun = binding.selected_point_ids[1]
    with pytest.raises(drain.PointDrainError) as uncommitted:
        drain.read_retry_source(
            prior_root=prior_root, point_id=unrun,
            selection_document_path=prior_root / "selection-binding.json")
    assert uncommitted.value.code == "RETRY_POINT_NOT_COMMITTED"
    # ... and neither can a point that was never part of the selection at all.
    with pytest.raises(drain.PointDrainError) as unselected:
        drain.read_retry_source(
            prior_root=prior_root, point_id="sample_20_never_selected",
            selection_document_path=prior_root / "selection-binding.json")
    assert unselected.value.code == "RETRY_POINT_NOT_SELECTED"


def test_a_retry_selection_document_projects_the_original_chain(tmp_path: Path) -> None:
    """The retry's own selection document must record the chain it references, not crash.

    The first v5 retry attempt died with `AttributeError: 'RetrySelectionBinding' object has no
    attribute 'catalog_sha256'`: the campaign's selection projection and the document writer were
    written for a first pass only. Both now go through one function, and the retry document carries
    the original catalog/selection/result hashes a later reader needs.
    """

    cli = _cli()
    drain = _drain_module()
    _module, _binding, _queue, prior_root, report, _calls = _committed_failed_point(tmp_path)
    point_id = report.attempts[0].point_id
    source = drain.read_retry_source(
        prior_root=prior_root, point_id=point_id,
        selection_document_path=prior_root / "selection-binding.json")
    selection_document = json.loads(
        (prior_root / "selection-binding.json").read_text(encoding="utf-8"))
    catalog_path = Path(selection_document["catalog_path"])
    retry = drain.retry_binding(
        source=source, catalog_path=catalog_path, campaign_id="retry-campaign",
        batch_id="retry-batch", config_sha256="c" * 64, runtime_closure_sha256="d" * 64)

    written = drain.write_selection_document(
        evidence_root=tmp_path / "retry", binding=retry, catalog_path=catalog_path)
    document = json.loads(written.read_text(encoding="utf-8"))
    assert document["kind"] == "FULL_RESTART_RETRY"
    assert document["catalog_sha256"] == selection_document["catalog_sha256"]
    assert document["original_selection_sha256"] == source["original_selection_sha256"]
    assert document["original_result_sha256"] == source["original_result_sha256"]
    assert document["original_outcome"] == "FAILED"
    assert document["selected_point_ids"] == [point_id]

    # the campaign's own projection is the same shape, for either binding kind
    projected = cli.selection_document(retry, catalog_path=catalog_path)
    assert projected["catalog_sha256"] == document["catalog_sha256"]
    assert projected["original_result_sha256"] == source["original_result_sha256"]
    first_pass_projection = cli.selection_document(_binding, catalog_path=catalog_path)
    assert first_pass_projection["kind"] == "FIRST_PASS"
    assert first_pass_projection["selected_point_ids"] == list(_binding.selected_point_ids)


def test_retry_binding_leases_only_the_bound_failed_point(tmp_path: Path) -> None:
    drain = _drain_module()
    _drain_module_, _binding, _queue, prior_root, report, _calls = _committed_failed_point(tmp_path)
    point_id = report.attempts[0].point_id
    selection_document = json.loads(
        (prior_root / "selection-binding.json").read_text(encoding="utf-8"))

    source = drain.read_retry_source(
        prior_root=prior_root, point_id=point_id,
        selection_document_path=prior_root / "selection-binding.json")
    retry = drain.retry_binding(
        source=source, catalog_path=Path(selection_document["catalog_path"]),
        campaign_id="retry-campaign", batch_id="retry-batch",
        config_sha256="c" * 64, runtime_closure_sha256="d" * 64)
    queue = _queue_module().DurablePointQueue(root=tmp_path / "retry-queue", binding=retry)

    assert retry.selected_point_ids == (point_id,)
    lease = queue.lease_next(_queue_module().WorkerIdentity(
        worker_id="w1", slot_id="slot-0", generation=1))
    assert lease is not None and lease.point_id == point_id
    assert queue.lease_next(_queue_module().WorkerIdentity(
        worker_id="w2", slot_id="slot-1", generation=1)) is None
    assert queue.snapshot().pending_point_ids == ()


# --------------------------------------------------------------------------------------
# The verdict may not claim a pass over an unexecuted selection
# --------------------------------------------------------------------------------------


class _Attempt:
    """The part of a point attempt the summary reads."""

    def __init__(self, point_id, attempt_id, state="COMMITTED", outcome="PASSED",
                 manifest="points/p.json", sha="e" * 64, physical=True):
        self.point_id = point_id
        self.attempt_id = attempt_id
        self.state = state
        self.outcome = outcome
        self.evidence_manifest_relative_path = manifest
        self.evidence_manifest_sha256 = sha
        self.physical_evidence = physical
        self.infrastructure_code = None
        self.worker_id = "w1"
        self.slot_id = "slot-0"

    def as_document(self):
        return {"point_id": self.point_id, "attempt_id": self.attempt_id,
                "state": self.state, "outcome": self.outcome}


def test_point_execution_summary_requires_exactly_one_committed_result_per_point() -> None:
    drain = _drain_module()
    point_ids = ("a", "b")

    complete = drain.point_execution_summary(
        selected_point_ids=point_ids,
        attempts=[_Attempt("a", "a-1"), _Attempt("b", "b-1")])
    assert complete["complete"] is True

    for attempts in (
        [_Attempt("a", "a-1")],                                              # never executed
        [_Attempt("a", "a-1"), _Attempt("a", "a-2"), _Attempt("b", "b-1")],  # twice
        [_Attempt("a", "a-1"), _Attempt("b", "b-1", state="INFRA_FAILED")],
        [_Attempt("a", "a-1"), _Attempt("b", "b-1", physical=False)],
        [_Attempt("a", "a-1"), _Attempt("b", "b-1"), _Attempt("c", "c-1")],  # unselected
    ):
        summary = drain.point_execution_summary(selected_point_ids=point_ids, attempts=attempts)
        assert summary["complete"] is False, summary
        assert (summary["unexecuted_point_ids"] or summary["duplicate_attempts"]
                or summary["infrastructure_failures"] or summary["unselected_attempts"]
                or summary["missing_physical_evidence"])
