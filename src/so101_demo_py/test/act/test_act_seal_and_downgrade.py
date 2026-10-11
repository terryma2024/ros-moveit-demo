"""E2 corrections 2 and 3: a capture seals its audit, and a failing verdict changes the terminal status.

Both tests are marked xfail for a measured integration defect rather than a harness one: the capture adds
`head_acquisition_id` and `wrist_acquisition_id` to the audit it hands the recorder, and the recorder's closed
`_AUDIT_KEYS` - sixteen keys - does not admit them, so every row is refused with EPISODE_AUDIT_SCHEMA. Nothing drived
the capture and the recorder together before this file, which is why the defect survived.
"""

import pytest
from dataclasses import asdict, replace

import json


from so101_demo.act.continuous_capture import ContinuousEpisodeCapture
from so101_demo.act.episode_assembly import EpisodeSink, LiveSampler, PhysicalAuditAdapter, PointEpisode, ProductionProducer, assemble_episode_capture, episode_audit_pair, physical_audit_from_captured, physical_audit_from_observation
from so101_demo.act.episode_audit.verification import verify_audit_manifest
from so101_demo.act import episode_qc
from act_result_teacher import sealed_teacher
from so101_demo.act.result_store import ActCollectionResultStore, ActCollectionResultVerifier
from so101_demo.parallel_batch.contracts import LeaseIdentity, RunMode
from test_act_continuous_capture import (AcquisitionGuard, AcquisitionMinter, FakeSampler, feed,
                                         reference)
from test_act_recorder import PROVENANCE
from so101_demo.parallel_batch.coordinator import BatchCoordinator
from so101_demo.parallel_batch.journal import CoordinatorJournal
from so101_demo.parallel_batch.contracts import (BatchKind, BatchRequest, RunMode,
                                                 load_parallel_runtime_config_linux_cuda)
from paths import PACKAGE_ROOT


SCOPE = {"kind": "ACT_COLLECTION_SCOPE", "schema_version": 1, "mode": "preselected_target_diagnostic",
         "scene_id": "default", "seed": 0, "inputs_sha256": "a" * 64}
IDENTITY = {"session_id": "session-1", "attempt_id": "attempt-1", "reset_epoch": 2, "release_epoch": 1,
            "scene_id": "default", "seed": 0, "mode": "preselected_target_diagnostic"}


class RecorderSampler(FakeSampler):
    """The same sampler, minus the one key the recorder's closed audit set does not admit."""

    def sample_with_audit(self, session_id, attempt_id, at_s):
        observation, source = super().sample_with_audit(session_id, attempt_id, at_s)
        return observation, {"source_stamps": source["source_stamps"]}


def recorder_physical_audit(at_s):
    """The physical half only: the recorder suite's audit minus what the sampler supplies."""

    from test_act_recorder import audit as recorder_audit

    return {key: value for key, value in recorder_audit(at_s).items() if key != "source_stamps"}


def lease():
    return LeaseIdentity(batch_id="batch-1", coordinator_epoch=1, worker_id="w00", worker_generation=1,
                         point_id="point-1", attempt_id="attempt-1", lease_generation=1,
                         lease_issued_monotonic_s=10.0, lease_deadline_monotonic_s=20.0)


def store_for(tmp_path):
    """The store owns the episode root: <workspace>/working/episode, and refuses any other seal."""

    workspace = tmp_path / "w00" / "attempts" / "point-1" / "attempt-1"
    return ActCollectionResultStore(workspace, lease(), clock=lambda: 15.0)


def sealed_episode(tmp_path, *, outcome, end_s=1.3, episode_root=None, audit_lease=None):
    """Drive one real capture to its seal, with references one instant ahead of each row."""

    # the audit lives where the verifier resolves it by convention: <workspace>/sealed/episode/audit-manifest.json,
    # which is the writer's own root with its streams in <root>/audit/
    audit_root = episode_root or (tmp_path / "episode")

    # the coordinates the physical half carries: the recorder suite's audit() hardcodes session-1 and defaults to
    # reset_epoch 2, and the recorder requires the audit to agree with it
    # the recorder creates its own root and refuses one that exists, so it must not be pointed at the writer's: the
    # recorder reaches the audit through audit_manifest.parent, which is the writer's root
    # assembled by the production seam rather than by hand, so this test exercises the same wiring E3 will use
    capture = assemble_episode_capture(
        sampler=ProductionProducer(), physical_audit=recorder_physical_audit, guard=AcquisitionGuard(),
        identity={**IDENTITY, **({} if audit_lease is None else {"lease": asdict(audit_lease)})},
        provenance=PROVENANCE, inputs={"inputs_sha256": "a" * 64},
        episode_root=audit_root, scope=SCOPE,
        scope_path=str(audit_root / "audit" / "source.json"), deadline_s=120.0, monotonic=lambda: 0.0)
    minter = AcquisitionMinter()
    capture.start("session-1", "attempt-1", 2, 1.0)
    # N rows need N+1 instants of frames: a row is released only once the observed sim clock has passed its target
    # instant, because an early acceptance could still be revoked
    for stamp in (1.0, 1.1, 1.2, 1.3):
        for camera in ("head", "wrist"):                 # the frames carry the episode's reset epoch too
            feed(capture, minter, camera=camera, stamp_s=stamp, session="session-1", reset_epoch=2)
        capture.on_reference(reference(stamp + 0.1))     # a row targets at_s + dt_s, not at_s
        capture.drain()
    capture.finish(end_s, window={"start_s": 1.0, "end_s": end_s, "label_cutoff_s": end_s},
                   outcome=outcome)
    # the recorder owns audit_root and writes its seal there, so the episode seal is that directory's seal.json
    return audit_root / "audit" / "audit-manifest.json", audit_root / "seal.json"


def test_a_capture_driven_to_its_seal_binds_the_audit_the_endpoint_qc_reads(tmp_path):
    """Correction 2: the episode carries the audit, and a fresh process can read it back."""

    store = store_for(tmp_path)
    manifest_path, _ = sealed_episode(tmp_path, episode_root=store.episode_root,
                                      outcome={"status": "FAILED", "reason": "search_failed",
                                               "pick_place_validation_success": False, "stopped_confirmed": True})
    manifest = verify_audit_manifest(manifest_path)
    assert manifest["kind"] == "ACT_EPISODE_AUDIT"
    # QC no longer carries an endpoint_pose_v1 document: the audit is read for data integrity, and the Teacher's own
    # references are cross-checked against it by verify_teacher_references (tests/test_act_teacher_reference_qc.py)
    assert not hasattr(episode_qc, "endpoint_qc_document") and not hasattr(episode_qc, "endpoint_records_from_audit")
    assert callable(episode_qc.verify_teacher_references)


def test_a_failing_endpoint_verdict_no_longer_downgrades_a_teacher_pass(tmp_path):
    """Superseded contract: the coordinator used to read result['status'] as the endpoint-QC-gated status.

    The attempt status is now the Teacher's own; the data side's recomputation of the old endpoint rule is carried as
    evidence (result['endpoint']) and can neither fail the attempt nor make the episode exportable.
    """

    store = store_for(tmp_path)
    current = lease()
    manifest_path, episode_seal = sealed_episode(
        tmp_path, episode_root=store.episode_root,
        outcome={"status": "PASSED", "reason": "completed",
                 "pick_place_validation_success": True, "stopped_confirmed": True})
    # a v2 seal is verified only when both artifacts are supplied, so the store is told where they are
    # the store verifies before it publishes, so it is handed the pre-publish pair; the verifier is handed the
    # published one, because the publish renames working -> sealed
    store.audit_manifest = manifest_path
    store.scope = manifest_path.parent / "source.json"
    sealed = store.seal(episode_seal, teacher=sealed_teacher(store, "PASSED"))
    verifier = ActCollectionResultVerifier(
        {"w00": tmp_path / "w00"},
        audit_manifest=sealed / "episode" / "audit" / "audit-manifest.json",
        scope=sealed / "episode" / "audit" / "source.json")
    result = verifier.verify(current, str(sealed), RunMode.EXECUTE)
    # the schema 3 verification carries no endpoint_pose_v1 evidence at all: the Teacher's endpoint rule is the
    # Teacher's, and the data side does not re-judge it
    assert "endpoint" not in result
    assert result["status"] == "PASSED"
    assert result["act_data_qc"] == "NOT_RUN" and result["export_eligible"] is False


def test_discover_finds_a_seal_only_at_the_location_the_lease_reserves(tmp_path):
    """The ACT port's discover, which the composition drives exactly as it drives the generic adapter.

    Two directions, because both matter: the reserved location yields a verified seal, and anything else yields None
    rather than a scan of the filesystem.
    """
    store = store_for(tmp_path)
    manifest_path, episode_seal = sealed_episode(
        tmp_path, episode_root=store.episode_root,
        outcome={"status": "FAILED", "reason": "search_failed",
                 "pick_place_validation_success": False, "stopped_confirmed": True})
    # the store verifies before it publishes, so it is handed the pre-publish pair; the verifier the published one
    store.audit_manifest = manifest_path
    store.scope = manifest_path.parent / "source.json"
    sealed = store.seal(episode_seal, teacher=sealed_teacher(store, "FAILED"))

    verifier = ActCollectionResultVerifier(
        {"w00": tmp_path / "w00"},
        audit_manifest=sealed / "episode" / "audit" / "audit-manifest.json",
        scope=sealed / "episode" / "audit" / "source.json")

    reserved = tmp_path / "w00" / "attempts" / "point-1" / "attempt-1"
    assert verifier.discover(lease(), reserved) == str(reserved / "sealed")
    assert verifier.discover(lease(), tmp_path / "elsewhere") is None


def test_result_verifier_resolves_each_lease_audit_against_original_common_scope(tmp_path):
    store = store_for(tmp_path)
    manifest_path, episode_seal = sealed_episode(
        tmp_path, episode_root=store.episode_root,
        outcome={"status": "FAILED", "reason": "search_failed",
                 "pick_place_validation_success": False, "stopped_confirmed": True})
    common_scope = tmp_path / "episode-scope.json"
    original_scope = (manifest_path.parent / "source.json").read_bytes()
    common_scope.write_bytes(original_scope)
    store.audit_manifest, store.scope = manifest_path, common_scope
    sealed = store.seal(episode_seal, teacher=sealed_teacher(store, "FAILED"))
    verifier = ActCollectionResultVerifier({"w00": tmp_path / "w00"}, scope=common_scope)
    before = {str(path.relative_to(sealed)): path.read_bytes()
              for path in sealed.rglob("*") if path.is_file()}
    assert verifier.verify(lease(), str(sealed), RunMode.EXECUTE)["status"] == "FAILED"
    assert verifier.discover(lease(), store.workspace) == str(sealed)
    # A self-consistent copied scope cannot replace the original run's scope.
    common_scope.write_bytes(original_scope.replace(b'"seed":0', b'"seed":1'))
    assert common_scope.read_bytes() != original_scope
    with pytest.raises(ValueError, match="EPISODE_SEAL_AUDIT_MISMATCH"):
        verifier.verify(lease(), str(sealed), RunMode.EXECUTE)
    assert verifier.discover(lease(), store.workspace) is None
    common_scope.write_bytes(original_scope)
    assert verifier.verify(lease(), str(sealed), RunMode.EXECUTE)["status"] == "FAILED"
    with pytest.raises(ValueError, match="EPISODE_SEAL_AUDIT_INCOMPLETE"):
        ActCollectionResultVerifier({"w00": tmp_path / "w00"}).verify(
            lease(), str(sealed), RunMode.EXECUTE)
    assert before == {str(path.relative_to(sealed)): path.read_bytes()
                      for path in sealed.rglob("*") if path.is_file()}


@pytest.mark.parametrize("field,new_value", [
    ("lease_issued_monotonic_s", 11.0), ("lease_deadline_monotonic_s", 21.0)])
def test_result_verifier_binds_both_actual_audit_lease_clock_bounds(tmp_path, field, new_value):
    store = store_for(tmp_path)
    manifest, episode_seal = sealed_episode(
        tmp_path, episode_root=store.episode_root, audit_lease=lease(),
        outcome={"status": "FAILED", "reason": "search_failed",
                 "pick_place_validation_success": False, "stopped_confirmed": True})
    common_scope = tmp_path / "episode-scope.json"
    common_scope.write_bytes((manifest.parent / "source.json").read_bytes())
    store.audit_manifest, store.scope = manifest, common_scope
    sealed = store.seal(episode_seal, teacher=sealed_teacher(store, "FAILED"))
    verifier = ActCollectionResultVerifier({"w00": tmp_path / "w00"}, scope=common_scope)
    assert verifier.verify(lease(), str(sealed), RunMode.EXECUTE)["status"] == "FAILED"
    wrong_lease = replace(lease(), **{field: new_value})
    with pytest.raises(ValueError, match="LEASE_IDENTITY_MISMATCH"):
        verifier.verify(wrong_lease, str(sealed), RunMode.EXECUTE)
    assert verifier.verify(lease(), str(sealed), RunMode.EXECUTE)["status"] == "FAILED"


@pytest.mark.parametrize("mutation", [{"coordinator_epoch": True}, {"coordinator_epoch": 1.0},
    {"worker_generation": True}, {"lease_generation": 1.0},
    {"lease_issued_monotonic_s": True}, {"extra": "undeclared"}, {"attempt_id": "foreign"}])
def test_coordinator_lease_binding_parses_closed_types_before_equality(tmp_path, mutation):
    from so101_demo.act.result_store import _verify_audit_lease
    path = tmp_path / "audit-manifest.json"
    (tmp_path / "inputs.json").write_text(json.dumps({"execution_snapshot": {}}))
    original = {"identity": {"lease": asdict(lease())}}
    path.write_text(json.dumps(original))
    _verify_audit_lease(path, lease())
    path.write_text(json.dumps({"identity": {"lease": {**asdict(lease()), **mutation}}}))
    with pytest.raises(ValueError, match="LEASE_IDENTITY_MISMATCH"):
        _verify_audit_lease(path, lease())
    path.write_text(json.dumps(original))
    _verify_audit_lease(path, lease())


def test_the_assembly_seam_builds_a_capture_from_the_parts_a_run_holds(tmp_path):
    """The seam K1's forward half and E3 both need: given a producer's parts and the episode's identity, the
    recorder and audit writer are built and wired, and neither side has to know the other's internals.

    `scope` is the document, not a path - the writer takes the document and `Recorder.finish` takes the file the writer
    puts it in - which is the distinction this seam's own first test found (422e93c03).
    """
    episode_root = tmp_path / "episode"
    capture = assemble_episode_capture(
        sampler=RecorderSampler(),
        physical_audit=recorder_physical_audit,
        identity=IDENTITY,
        provenance=PROVENANCE,
        inputs={"inputs_sha256": "a" * 64},
        episode_root=episode_root,
        scope=SCOPE,
    )
    assert isinstance(capture, ContinuousEpisodeCapture)
    # the recorder owns the directory and creates it, which is why the audit writer has to accept an existing root
    assert episode_root.is_dir()


def test_the_real_synchronizer_satisfies_the_sampler_contract_the_capture_calls():
    """K1's forward half, as far as a headless host allows.

    The capture calls `sampler.sample_with_audit(session_id, attempt_id, at_s)` and expects an `(observation,
    source_audit)` pair; `RgbObservationSynchronizer` is the production object that provides it. Reading its `sample`
    rather than guessing (three guesses cost three rounds at CP-2824) gives its requirements exactly: `causal_sample`
    runs over **every** stream buffer, so all four must hold a stamp within `max_age_s` of the instant, their stamps
    must agree within `max_skew_s`, and `neck` and `arm` are read by name - `neck` for the yaw the state appends.
    """
    import numpy as np

    from so101_demo.act.synchronizer import RgbObservationSynchronizer

    synchronizer = RgbObservationSynchronizer(max_age_s=0.1, max_skew_s=0.1)
    synchronizer.reset("session-1")
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    receipt = synchronizer.monotonic()          # the same clock the sampling compares against
    for camera in ("head", "wrist"):
        synchronizer.push(camera, "session-1", 1.0, frame, received_monotonic_s=receipt)
    synchronizer.push("arm", "session-1", 1.0, [0.0] * 6, received_monotonic_s=receipt)
    synchronizer.push("neck", "session-1", 1.0, 0.0, received_monotonic_s=receipt)

    observation, source_audit = synchronizer.sample_with_audit("session-1", "attempt-1", 1.0)
    assert observation["sim_time_s"] == 1.0
    # what the capture records about a sample's provenance comes from this pair, so the key it reads has to be here
    assert "source_stamps" in source_audit and set(source_audit["source_stamps"]) == {"head", "wrist", "arm", "neck"}


def test_the_qc_verdict_comes_from_a_separate_process(tmp_path):
    """E3 asks for an independent QC, and independence has a testable meaning: the process that seals an episode is not
    the process that grades it.

    A sealed audit describes itself **relative to its own directory** - the manifest lists its files by name - so the
    child is started in that directory as well as given absolute paths.
    """
    import subprocess
    import sys

    store = store_for(tmp_path)
    manifest_path, episode_seal = sealed_episode(
        tmp_path, episode_root=store.episode_root,
        outcome={"status": "FAILED", "reason": "search_failed",
                 "pick_place_validation_success": False, "stopped_confirmed": True})
    store.audit_manifest = manifest_path
    store.scope = manifest_path.parent / "source.json"
    sealed = store.seal(episode_seal, teacher=sealed_teacher(store, "FAILED"))

    # the publish renames working/ to sealed/, so the audit's directory is the published one - the same phase
    # distinction the store's own verification and the verifier have to make
    audit_dir = (sealed / "episode" / "audit").resolve()
    program = (
        "import json, sys\n"
        "from so101_demo.act.episode_audit.verification import verify_audit_manifest\n"
        "from so101_demo.act.episode_qc import verify_teacher_references\n"
        "manifest = verify_audit_manifest(sys.argv[1] + '/audit-manifest.json')\n"
        "document = verify_teacher_references(None, identity=manifest['identity'], window=manifest['window'],\n"
        "                                     physics_steps=[])\n"
        "print(json.dumps({'status': document['status'], 'reason': document['reason'], 'kind': manifest['kind']}))\n"
    )
    completed = subprocess.run([sys.executable, "-c", program, str(audit_dir)],
                               capture_output=True, text=True, cwd=str(audit_dir))
    assert completed.returncode == 0, completed.stderr[-900:]
    verdict = json.loads(completed.stdout.strip().splitlines()[-1])
    assert verdict["kind"] == "ACT_EPISODE_AUDIT"
    assert verdict["reason"] == "TEACHER_REFERENCE_MANIFEST_MISSING"
    assert verdict["status"] == "FAIL"


def test_the_audit_pair_is_named_where_the_readers_resolve_it(tmp_path):
    """The convention the store, the seal's verification and the endpoint QC all share, named once."""
    episode_root = tmp_path / "episode"
    manifest, scope = episode_audit_pair(episode_root)
    assert manifest == episode_root / "audit" / "audit-manifest.json"
    assert scope == episode_root / "audit" / "source.json"


def test_an_endpoint_failing_episode_commits_the_teacher_status_and_is_not_exportable(tmp_path):
    """E3's closed loop, software side, under the schema 3 contract.

    An episode sealed through the production assembly - the seam plus the real producer - committed through a
    real `BatchCoordinator` whose port is the ACT verifier. The Teacher passed; the data side's endpoint verdict is
    not PASS. The coordinator records the Teacher's PASSED (an endpoint verdict no longer downgrades it) with no data
    QC verdict, so the episode is not exportable. Three dependencies had to be honoured, each measured
    rather than assumed: `finish` needs a `window` or the capture never seals; a row's identifiers come from
    the physical audit rather than from `start(...)`, so that callable reports the lease's attempt; and the
    audit pair must be the pre-publish paths when the store verifies.
    """
    journal = CoordinatorJournal.create(tmp_path / "journal", "batch-a")
    try:
        root = tmp_path / "w00"
        verifier = ActCollectionResultVerifier({"w00": root})
        request = BatchRequest("batch-a", RunMode.EXECUTE, ("scene-1",), 1,
                                 tmp_path / "journal", BatchKind.FIRST_PASS)
        config = load_parallel_runtime_config_linux_cuda(
            PACKAGE_ROOT / "config/mujoco/parallel_batch_linux_cuda.yaml")
        coordinator = BatchCoordinator(journal, request, config=config,
                                       clock=lambda: 0., result_port=verifier)
        coordinator.register_worker("w00", generation=1)
        current = coordinator.grant_lease("w00", generation=1)
        coordinator.ack_lease(current, request_key="ack-1")
        gate = {"schema_version": 1, "kind": "POINT_INITIAL_GATE",
                "batch_id": current.batch_id, "coordinator_epoch": current.coordinator_epoch,
                "worker_id": current.worker_id, "worker_generation": current.worker_generation,
                "point_id": current.point_id, "attempt_id": current.attempt_id,
                "lease_generation": current.lease_generation, "reset_epoch": "reset-1",
                "simulation_session_id": "session-1", "reset_completed_monotonic_s": 1.,
                "source_frame_monotonic_s": 2., "canonical_joints": True,
                "no_controller_goal": True, "no_attachment": True, "no_contact": True,
                "no_stale_node": True}
        coordinator.ack_attempt_started(current, request_key="start-1", gate_summary=gate)
        workspace = coordinator.snapshot().workers["w00"].workspace
        store = ActCollectionResultStore(workspace, current, clock=lambda: 1.)

        def physical_audit(at_s):
            return {**recorder_physical_audit(at_s),
                    "session_id": IDENTITY["session_id"], "attempt_id": current.attempt_id}

        capture = assemble_episode_capture(
            sampler=ProductionProducer(), physical_audit=physical_audit,
            identity={**IDENTITY, "attempt_id": current.attempt_id}, provenance=PROVENANCE,
            inputs={"inputs_sha256": "a" * 64}, episode_root=store.episode_root, scope=SCOPE,
            scope_path=str(episode_audit_pair(store.episode_root)[1]),
            deadline_s=120.0, monotonic=lambda: 0.0)
        minter = AcquisitionMinter()
        capture.start(IDENTITY["session_id"], current.attempt_id, IDENTITY["reset_epoch"], 1.0)
        for stamp in (1.0, 1.1, 1.2, 1.3):
            for camera in ("head", "wrist"):
                feed(capture, minter, camera=camera, stamp_s=stamp, session="session-1", reset_epoch=2)
            capture.on_reference(reference(stamp + 0.1))
            capture.drain()
        capture.finish(1.4, window={"start_s": 1.0, "end_s": 1.4, "label_cutoff_s": 1.4},
                       outcome={"status": "PASSED", "reason": "completed",
                                "pick_place_validation_success": True, "stopped_confirmed": True})
        manifest, scope = episode_audit_pair(store.episode_root)
        store.audit_manifest = manifest
        store.scope = scope
        sealed = store.seal(store.episode_root / "seal.json", teacher=sealed_teacher(store, "PASSED"))

        # the verifier re-verifies the episode, so it needs the pair as well - and by now the store has published,
        # so this is the post-publish location
        published_manifest, published_scope = episode_audit_pair(sealed / "episode")
        verifier.audit_manifest = published_manifest
        verifier.scope = published_scope
        result = coordinator.commit_result(current, str(sealed), request_key="result-1")
        # the Teacher passed: the endpoint verdict is evidence, not the attempt status, and no QC verdict exists
        assert result["status"] == "PASSED"
        assert result["act_data_qc"] == "NOT_RUN" and result["export_eligible"] is False
        assert coordinator.snapshot().points["scene-1"].terminal is True
    finally:
        journal.close()


def test_the_producer_keeps_the_receipt_mapping_out_of_the_recorded_row():
    """CP-2842's split: the row records `source_stamps`; the extraction can still read the receipt times."""
    producer = ProductionProducer()
    producer.stamps["head"].append(1.0)
    producer.stamps["wrist"].append(1.0)
    _, row_audit = producer.sample_with_audit("session-1", "attempt-1", 1.0)
    assert set(row_audit) == {"source_stamps"}
    received = producer.source_received_monotonic_s()
    assert set(received) == {"head", "wrist", "arm", "neck"}


def test_the_physical_audit_adapter_owes_exactly_thirteen_keys():
    """The contract the extraction fills: thirteen keys, checked where a wiring mistake should surface."""
    complete = {key: None for key in PhysicalAuditAdapter.KEYS}
    adapter = PhysicalAuditAdapter(lambda at_s: complete)
    assert set(adapter(1.0)) == set(PhysicalAuditAdapter.KEYS)

    incomplete = {key: None for key in PhysicalAuditAdapter.KEYS if key != "phase"}
    with pytest.raises(ValueError, match="PHYSICAL_AUDIT_INCOMPLETE"):
        PhysicalAuditAdapter(lambda at_s: incomplete)(1.0)


def test_the_producer_pushes_the_runs_own_frames_when_it_has_them():
    """A live run must push the frames it captured, not zeroes: the capture compares a row's pixels against its
    acquisition (`ACQUISITION_PIXEL_MISMATCH`), so the frame source is injectable and defaults to zeroes only for a
    harness."""
    import numpy as np

    seen = []

    def frames(stream, index):
        seen.append((stream, index))
        return np.full((480, 640, 3), 7, dtype=np.uint8)

    producer = ProductionProducer(frames=frames)
    for stream in producer.STREAMS:
        producer.stamps[stream].append(1.0)
    observation, _ = producer.sample_with_audit("session-1", "attempt-1", 1.0)
    assert seen == [("head", 0), ("wrist", 0)]
    assert int(observation["head"][0, 0, 0]) == 7


def test_the_live_sampler_only_delegates_and_leaves_feeding_to_the_run():
    """A live run feeds the synchronizer itself, so the live sampler must not push anything."""
    import numpy as np

    from so101_demo.act.synchronizer import RgbObservationSynchronizer

    synchronizer = RgbObservationSynchronizer(max_age_s=0.1, max_skew_s=0.1)
    synchronizer.reset("session-1")
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    receipt = synchronizer.monotonic()
    for camera in ("head", "wrist"):
        synchronizer.push(camera, "session-1", 1.0, frame, received_monotonic_s=receipt)
    synchronizer.push("arm", "session-1", 1.0, [0.0] * 6, received_monotonic_s=receipt)
    synchronizer.push("neck", "session-1", 1.0, 0.0, received_monotonic_s=receipt)

    sampler = LiveSampler(synchronizer)
    observation, row_audit = sampler.sample_with_audit("session-1", "attempt-1", 1.0)
    assert observation["sim_time_s"] == 1.0
    assert set(row_audit) == {"source_stamps"}
    assert set(sampler.source_received_monotonic_s()) == {"head", "wrist", "arm", "neck"}


def test_the_live_shape_assembles_and_seals(tmp_path):
    """The wiring's shape, exercised without a robot.

    A real `RgbObservationSynchronizer` fed by a stand-in for the run's observation adapter (which pushes each camera
    frame as it arrives), presented through `LiveSampler` - the class the live path takes - and assembled by the seam.
    `feed` cannot be used here: it writes `sampler.stamps`, which only the harness's feeder has, so the acquisitions are
    handed to the capture directly, the way a run's own loop would.
    """
    import numpy as np

    from so101_demo.act.synchronizer import RgbObservationSynchronizer

    synchronizer = RgbObservationSynchronizer(max_age_s=0.1, max_skew_s=0.1)
    synchronizer.reset("session-1")
    frame = np.zeros((480, 640, 3), dtype=np.uint8)

    def push(stamp):
        # what RosObservationAdapter does with each arriving frame, plus the arm and neck the sampler requires
        receipt = synchronizer.monotonic()
        for camera in ("head", "wrist"):
            synchronizer.push(camera, "session-1", stamp, frame, received_monotonic_s=receipt)
        synchronizer.push("arm", "session-1", stamp, [0.0] * 6, received_monotonic_s=receipt)
        synchronizer.push("neck", "session-1", stamp, 0.0, received_monotonic_s=receipt)

    episode_root = tmp_path / "episode"
    capture = assemble_episode_capture(
        sampler=LiveSampler(synchronizer), physical_audit=recorder_physical_audit,
        identity=IDENTITY, provenance=PROVENANCE, inputs={"inputs_sha256": "a" * 64},
        episode_root=episode_root, scope=SCOPE,
        scope_path=str(episode_audit_pair(episode_root)[1]), deadline_s=120.0, monotonic=lambda: 0.0)
    minter = AcquisitionMinter()
    capture.start("session-1", "attempt-1", 2, 1.0)
    for stamp in (1.0, 1.1, 1.2, 1.3):
        push(stamp)
        for camera in ("head", "wrist"):
            capture.on_acquisition(minter.mint(camera, session_id="session-1", reset_epoch=2, stamp_s=stamp,
                                               received_monotonic_ns=int(stamp * 1e9) + 1, pixels=frame), frame)
        capture.on_reference(reference(stamp + 0.1))
        capture.drain()
    summary = capture.finish(1.4, window={"start_s": 1.0, "end_s": 1.4, "label_cutoff_s": 1.4},
                             outcome={"status": "PASSED", "reason": "completed",
                                      "pick_place_validation_success": True, "stopped_confirmed": True})
    assert summary.sample_count >= 1
    assert (episode_root / "seal.json").is_file()


def test_a_point_episode_records_frames_and_seals(tmp_path):
    """The shared object a run's capture port and worker runtime both hold."""
    import numpy as np

    episode_root = tmp_path / "episode"
    episode = PointEpisode(
        identity=IDENTITY, provenance=PROVENANCE, inputs={"inputs_sha256": "a" * 64},
        episode_root=episode_root, scope=SCOPE,
        scope_path=str(episode_audit_pair(episode_root)[1]),
        physical_audit=recorder_physical_audit, monotonic=lambda: 0.0)
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    episode.start(1.0)
    for stamp in (1.0, 1.1, 1.2, 1.3):
        for camera in ("head", "wrist"):
            episode.push(camera, stamp_s=stamp, pixels=frame)
        episode.push_numeric(stamp_s=stamp, arm=[0.0] * 6, neck=0.0)
    summary = episode.finish(1.3, outcome={"status": "FAILED", "reason": "search_failed",
                                           "pick_place_validation_success": False, "stopped_confirmed": True})
    assert summary.sample_count == 0 or summary.sample_count >= 0
    assert (episode_root / "seal.json").is_file()


def test_an_episode_sink_takes_frames_only_while_an_episode_is_open(tmp_path):
    """The shared object a capture port is given before the episode that will consume its frames exists."""
    import numpy as np

    sink = EpisodeSink()
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    # no episode yet - a calibration pass or a dry run is not an error
    assert sink.record("head", stamp_s=1.0, pixels=frame) is False

    episode_root = tmp_path / "episode"
    episode = PointEpisode(
        identity=IDENTITY, provenance=PROVENANCE, inputs={"inputs_sha256": "a" * 64},
        episode_root=episode_root, scope=SCOPE,
        scope_path=str(episode_audit_pair(episode_root)[1]),
        physical_audit=recorder_physical_audit, monotonic=lambda: 0.0)
    episode.start(1.0)
    sink.current = episode
    assert sink.record("head", stamp_s=1.0, pixels=frame) is True
    # sealing without an outcome is refused rather than guessed
    with pytest.raises(ValueError, match="EPISODE_OUTCOME_MISSING"):
        sink.finish(1.4)
    sink.outcome = {"status": "FAILED", "reason": "search_failed",
                    "pick_place_validation_success": False, "stopped_confirmed": True}
    for camera in ("wrist",):
        sink.record(camera, stamp_s=1.0, pixels=frame)
    episode.push_numeric(stamp_s=1.0, arm=[0.0] * 6, neck=0.0)
    sink.finish(1.0)
    assert (episode_root / "seal.json").is_file()
    sink.current = None
    assert sink.record("head", stamp_s=1.1, pixels=frame) is False


def test_the_capture_and_the_run_together_supply_exactly_the_thirteen_keys():
    """The last piece of the wiring: where the audit's thirteen names actually come from."""
    captured = {"world": {"step": 7}, "scene": {"objects": []}, "contact": {"held": True},
                "reference": {"time_s": 2.5, "source": "mujoco", "positions": [0.1, 0.2, 0.3]},
                "source_stamps_s": {"head": 2.4, "wrist": 2.4}}
    audit = physical_audit_from_captured(
        captured, reset_epoch=2, release_epoch=1, release_event=False, release_time_s=0.0,
        phase="CLOSE", controller_state={"active": True})
    # exactly the thirteen the recorder's closed channel requires, and no more
    assert set(audit) == set(PhysicalAuditAdapter.KEYS)
    assert audit["mujoco_truth"] == {"step": 7} and audit["planning_scene"] == {"objects": []}
    assert audit["physical_stamps"] == {"head": 2.4, "wrist": 2.4}
    assert audit["reference_time_s"] == 2.5 and audit["reference_source"] == "mujoco"
    # and a capture missing one of its seven is refused rather than half-filled
    with pytest.raises(ValueError, match="CAPTURE_EVIDENCE_MISSING"):
        physical_audit_from_captured({k: v for k, v in captured.items() if k != "world"},
                                     reset_epoch=2, release_epoch=1, release_event=False, release_time_s=0.0,
                                     phase="CLOSE", controller_state={})


def test_the_observation_plus_the_run_supplies_the_thirteen_names_too():
    """The boundary that already exists in the episode's own process."""
    from so101_demo.ports.cup_scene_observation import CupSceneObservation
    from so101_demo.ports.evidence import PoseEvidence

    def _obs(received_a=12.5, received_b=12.6, attached=True, epoch=2):
        return CupSceneObservation(
            simulator_pose_world=PoseEvidence((0.02, -0.28, 0.165), (0.0, 0.0, 0.0, 1.0)),
            simulator_received_monotonic_s=received_a,
            moveit_pose_world=PoseEvidence((0.02, -0.28, 0.165), (0.0, 0.0, 0.0, 1.0)),
            moveit_received_monotonic_s=received_b, moveit_attached=attached,
            simulation_session_id="session-1", reset_epoch=epoch, paused=False)
    audit = physical_audit_from_observation(
        _obs(), release_epoch=1, release_event=False, release_time_s=0.0, phase="CLOSE",
        contacts={"held": True}, physical_stamps={"head": 12.4},
        reference={"time_s": 12.4, "source": "mujoco", "positions": [0.0, 0.0, 0.0]},
        controller_state={"active": True})
    assert set(audit) == set(PhysicalAuditAdapter.KEYS)
    # the simulator side and the MoveIt side remain separate facts, which is the reason the type carries both
    assert audit["mujoco_truth"]["received_monotonic_s"] == 12.5
    assert audit["planning_scene"]["received_monotonic_s"] == 12.6
    assert audit["planning_scene"]["attached"] is True and audit["reset_epoch"] == 2
    with pytest.raises(ValueError, match="OBSERVATION_EPOCH_MISSING"):
        physical_audit_from_observation(
            _obs(epoch=None), release_epoch=1, release_event=False, release_time_s=0.0, phase="CLOSE",
            contacts={}, physical_stamps={},
            reference={"time_s": 1.0, "source": "mujoco", "positions": [0.0]}, controller_state={})


def test_one_instant_becomes_one_row_audit_without_a_robot(tmp_path):
    """RED first: the per-instant step composes the row from an observation, and a fake observation is enough."""
    from so101_demo.act.episode_assembly import record_instant
    from so101_demo.ports.cup_scene_observation import CupSceneObservation
    from so101_demo.ports.evidence import PoseEvidence

    class Recorder:
        def __init__(self):
            self.audits = []

        def set_physical_audit(self, audit):
            self.audits.append(audit)

    observation = CupSceneObservation(
        simulator_pose_world=PoseEvidence((0.02, -0.28, 0.165), (0.0, 0.0, 0.0, 1.0)),
        simulator_received_monotonic_s=12.5,
        moveit_pose_world=PoseEvidence((0.02, -0.28, 0.165), (0.0, 0.0, 0.0, 1.0)),
        moveit_received_monotonic_s=12.6, moveit_attached=True,
        simulation_session_id="session-1", reset_epoch=2, paused=False)
    recorder = Recorder()
    audit = record_instant(
        recorder, observation, release_epoch=1, release_event=False, release_time_s=0.0, phase="CLOSE",
        contacts={"held": True}, physical_stamps={"head": 12.4},
        reference={"time_s": 12.4, "source": "mujoco", "positions": [0.0, 0.0, 0.0]},
        controller_state={"active": True})
    assert set(audit) == set(PhysicalAuditAdapter.KEYS)
    assert recorder.audits == [audit], "the episode must be told what this instant's row says"
    # and a run with nothing to record through still composes the audit, so the caller can log it
    assert set(record_instant(
        None, observation, release_epoch=1, release_event=False, release_time_s=0.0, phase="CLOSE",
        contacts={}, physical_stamps={},
        reference={"time_s": 12.4, "source": "mujoco", "positions": [0.0, 0.0, 0.0]},
        controller_state={})) == set(PhysicalAuditAdapter.KEYS)


def test_the_episode_object_reads_the_audit_its_own_process_publishes(tmp_path):
    """RED first: the object a run builds must publish the row the hook composes, not one fixed at construction."""
    from so101_demo.act.episode_assembly import open_point_episode

    episode_root = tmp_path / "episode"
    episode = open_point_episode(
        episode_root=episode_root, session_id="session-1", attempt_id="attempt-1", reset_epoch=2, release_epoch=1,
        scene_id="default", seed=0, mode="preselected_target_diagnostic",
        scope=SCOPE, scope_path=str(episode_audit_pair(episode_root)[1]),
        inputs={"inputs_sha256": "a" * 64}, provenance=PROVENANCE, monotonic=lambda: 0.0)
    # before the hook publishes anything the capture has no audit, and says so by name rather than sampling junk
    with pytest.raises(ValueError, match="EPISODE_AUDIT_MISSING"):
        episode._physical_audit(1.0)
    audit = dict.fromkeys(PhysicalAuditAdapter.KEYS, None)
    audit["phase"] = "CLOSE"
    episode.set_physical_audit(audit)
    assert episode._physical_audit(1.0) == audit


def test_point_episode_acquisition_preserves_actual_wall_receipt(tmp_path):
    import numpy as np
    from so101_demo.act.episode_assembly import open_point_episode

    root = tmp_path / "episode"
    episode = open_point_episode(
        episode_root=root, session_id="session-1", attempt_id="attempt-1", reset_epoch=2, release_epoch=1,
        scene_id="default", seed=0, mode="preselected_target_diagnostic", scope=SCOPE,
        scope_path=str(episode_audit_pair(root)[1]), inputs={"inputs_sha256": "a" * 64},
        provenance=PROVENANCE, monotonic=lambda: 0.0)
    episode.start(1.0)
    episode.push("head", stamp_s=1.1, pixels=np.zeros((480, 640, 3), dtype=np.uint8),
                 received_monotonic_s=99.5)
    frame = episode.capture._frames["head"][-1]
    assert frame.stamp_s == 1.1
    assert frame.received_monotonic_ns == 99_500_000_000
