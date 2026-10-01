"""E2 corrections 2 and 3: a capture seals its audit, and a failing verdict changes the terminal status.

Both tests are marked xfail for a measured integration defect rather than a harness one (CP-2726): the capture adds
`head_acquisition_id` and `wrist_acquisition_id` to the audit it hands the recorder, and the recorder's closed
`_AUDIT_KEYS` - sixteen keys - does not admit them, so every row is refused with EPISODE_AUDIT_SCHEMA. Nothing drived
the capture and the recorder together before this file, which is why the defect survived.
"""

import pytest

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from so101_demo.act.continuous_capture import ContinuousEpisodeCapture
from so101_demo.act.episode_assembly import (LiveSampler, PhysicalAuditAdapter,
                                              ProductionProducer, assemble_episode_capture,
                                              episode_audit_pair)
from so101_demo.act.endpoint_pose_acceptance import load_endpoint_policy
from so101_demo.act.episode_audit import EpisodeAuditWriter, verify_audit_manifest
from so101_demo.act.episode_qc import endpoint_qc_document
from so101_demo.act.recorder import EpisodeRecorder
from so101_demo.act.result_store import ActCollectionResultStore, ActCollectionResultVerifier
from so101_demo.parallel_batch.contracts import LeaseIdentity, RunMode
from test_act_continuous_capture import (AcquisitionGuard, AcquisitionMinter, FakeSampler, feed,
                                         reference)
from test_act_recorder import PROVENANCE
from so101_demo.parallel_batch.coordinator import BatchCoordinator
from so101_demo.parallel_batch.journal import CoordinatorJournal
from so101_demo.parallel_batch.contracts import (BatchKindV2, BatchRequestV2, RunMode,
                                                 load_parallel_runtime_config_v2)


POLICY = Path(__file__).resolve().parents[1] / "config/act/endpoint_pose_acceptance_v1.yaml"
SCOPE = {"kind": "ACT_COLLECTION_SCOPE", "schema_version": 1, "mode": "preselected_target_diagnostic",
         "scene_id": "default", "seed": 0, "inputs_sha256": "a" * 64}
IDENTITY = {"session_id": "session-1", "attempt_id": "attempt-1", "reset_epoch": 2, "release_epoch": 1,
            "scene_id": "default", "seed": 0, "mode": "preselected_target_diagnostic"}


class RecorderSampler(FakeSampler):
    """The same sampler, minus the one key the recorder's closed audit set does not admit (CP-2723)."""

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
    """The store owns the episode root: <workspace>/working/episode, and refuses any other seal (CP-2762)."""

    workspace = tmp_path / "w00" / "attempts" / "point-1" / "attempt-1"
    return ActCollectionResultStore(workspace, lease(), clock=lambda: 15.0)


def sealed_episode(tmp_path, *, outcome, end_s=1.3, episode_root=None):
    """Drive one real capture to its seal, with references one instant ahead of each row (CP-2725)."""

    # the audit lives where the verifier resolves it by convention: <workspace>/sealed/episode/audit-manifest.json,
    # which is the writer's own root with its streams in <root>/audit/ (CP-2768)
    audit_root = episode_root or (tmp_path / "episode")

    # the coordinates the physical half carries: the recorder suite's audit() hardcodes session-1 and defaults to
    # reset_epoch 2, and the recorder requires the audit to agree with it (CP-2734)
    # the recorder creates its own root and refuses one that exists, so it must not be pointed at the writer's: the
    # recorder reaches the audit through audit_manifest.parent, which is the writer's root (CP-2769)
    # assembled by the production seam rather than by hand, so this test exercises the same wiring E3 will use
    capture = assemble_episode_capture(
        sampler=ProductionProducer(), physical_audit=recorder_physical_audit, guard=AcquisitionGuard(),
        identity=IDENTITY, provenance=PROVENANCE, inputs={"inputs_sha256": "a" * 64},
        episode_root=audit_root, scope=SCOPE,
        scope_path=str(audit_root / "audit" / "source.json"), deadline_s=120.0, monotonic=lambda: 0.0)
    minter = AcquisitionMinter()
    capture.start("session-1", "attempt-1", 2, 1.0)
    # N rows need N+1 instants of frames: a row is released only once the observed sim clock has passed its target
    # instant, because an early acceptance could still be revoked (CP-2741)
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
                                               "task8_success": False, "stopped_confirmed": True})
    manifest = verify_audit_manifest(manifest_path)
    assert manifest["kind"] == "ACT_EPISODE_AUDIT"
    document = endpoint_qc_document(manifest_path.parent, {
        "initial_target": [0.0] * 7, "final_target": [0.0] * 7,
        "endpoint_policy": load_endpoint_policy(POLICY)})
    print("EPISODE QC:", document["status"], "| checks:", sorted(document["checks"]))
    assert document["rule_version"] == "endpoint_pose_v1" and "endpoint_pose" in document["checks"]


def test_a_run_claiming_success_cannot_survive_a_failing_endpoint_verdict(tmp_path):
    """Correction 3: the coordinator reads result['status'], so a failing verdict must change it."""

    store = store_for(tmp_path)
    current = lease()
    manifest_path, episode_seal = sealed_episode(
        tmp_path, episode_root=store.episode_root,
        outcome={"status": "PASSED", "reason": "completed",
                 "task8_success": True, "stopped_confirmed": True})
    # a v2 seal is verified only when both artifacts are supplied, so the store is told where they are (CP-2765)
    # the store verifies before it publishes, so it is handed the pre-publish pair; the verifier is handed the
    # published one, because the publish renames working -> sealed (CP-2777)
    store.audit_manifest = manifest_path
    store.scope = manifest_path.parent / "source.json"
    sealed = store.seal(episode_seal)
    verifier = ActCollectionResultVerifier(
        {"w00": tmp_path / "w00"},
        audit_manifest=sealed / "episode" / "audit" / "audit-manifest.json",
        scope=sealed / "episode" / "audit" / "source.json",
        endpoint_inputs={"initial_target": [0.0] * 7, "final_target": [0.0] * 7,
                         "endpoint_policy": load_endpoint_policy(POLICY)})
    result = verifier.verify(current, str(sealed), RunMode.EXECUTE)
    print("DOWNGRADE status:", result["status"], "| endpoint:", result["endpoint"]["status"])
    assert result["endpoint"]["status"] != "PASS"
    assert result["status"] == "FAILED"


def test_discover_finds_a_seal_only_at_the_location_the_lease_reserves(tmp_path):
    """The ACT port's discover, which the composition drives exactly as it drives the generic adapter (CP-2801).

    Two directions, because both matter: the reserved location yields a verified seal, and anything else yields None
    rather than a scan of the filesystem.
    """
    store = store_for(tmp_path)
    manifest_path, episode_seal = sealed_episode(
        tmp_path, episode_root=store.episode_root,
        outcome={"status": "FAILED", "reason": "search_failed",
                 "task8_success": False, "stopped_confirmed": True})
    # the store verifies before it publishes, so it is handed the pre-publish pair; the verifier the published one
    store.audit_manifest = manifest_path
    store.scope = manifest_path.parent / "source.json"
    sealed = store.seal(episode_seal)

    verifier = ActCollectionResultVerifier(
        {"w00": tmp_path / "w00"},
        audit_manifest=sealed / "episode" / "audit" / "audit-manifest.json",
        scope=sealed / "episode" / "audit" / "source.json",
        endpoint_inputs={"initial_target": [0.0] * 7,
                         "endpoint_policy": {"rule_version": "endpoint_pose_v1", "thresholds": {}},
                         "final_target": [0.0] * 7})

    reserved = tmp_path / "w00" / "attempts" / "point-1" / "attempt-1"
    assert verifier.discover(lease(), reserved) == str(reserved / "sealed")
    assert verifier.discover(lease(), tmp_path / "elsewhere") is None


def test_the_assembly_seam_builds_a_capture_from_the_parts_a_run_holds(tmp_path):
    """The seam K1's forward half and E3 both need (CP-2822): given a producer's parts and the episode's identity, the
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
    receipt = synchronizer.monotonic()          # the same clock the sampling compares against (CP-2823)
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
    child is started in that directory as well as given absolute paths (CP-2826).
    """
    import subprocess
    import sys

    store = store_for(tmp_path)
    manifest_path, episode_seal = sealed_episode(
        tmp_path, episode_root=store.episode_root,
        outcome={"status": "FAILED", "reason": "search_failed",
                 "task8_success": False, "stopped_confirmed": True})
    store.audit_manifest = manifest_path
    store.scope = manifest_path.parent / "source.json"
    sealed = store.seal(episode_seal)

    # the publish renames working/ to sealed/, so the audit's directory is the published one - the same phase
    # distinction the store's own verification and the verifier have to make (CP-2777)
    audit_dir = (sealed / "episode" / "audit").resolve()
    program = (
        "import json, sys\n"
        "from so101_demo.act.episode_qc import endpoint_qc_document\n"
        "from so101_demo.act.endpoint_pose_acceptance import load_endpoint_policy\n"
        "inputs = {'initial_target': [0.0] * 7, 'final_target': [0.0] * 7,\n"
        "          'endpoint_policy': load_endpoint_policy(sys.argv[2])}\n"
        "document = endpoint_qc_document(sys.argv[1], inputs)\n"
        "print(json.dumps({'status': document['status'], 'checks': sorted(document['checks'])}))\n"
    )
    completed = subprocess.run([sys.executable, "-c", program, str(audit_dir), str(POLICY.resolve())],
                               capture_output=True, text=True, cwd=str(audit_dir))
    assert completed.returncode == 0, completed.stderr[-900:]
    verdict = json.loads(completed.stdout.strip().splitlines()[-1])
    assert verdict["checks"] == ["endpoint_pose"]
    assert verdict["status"] in ("PASS", "FAIL", "INCOMPLETE")


def test_the_audit_pair_is_named_where_the_readers_resolve_it(tmp_path):
    """The convention the store, the seal's verification and the endpoint QC all share (CP-2768), named once."""
    episode_root = tmp_path / "episode"
    manifest, scope = episode_audit_pair(episode_root)
    assert manifest == episode_root / "audit" / "audit-manifest.json"
    assert scope == episode_root / "audit" / "source.json"


def test_an_endpoint_failing_episode_cannot_be_committed_as_success(tmp_path):
    """E3's closed loop, software side (CP-2827/CP-2828).

    An episode sealed through the production assembly - the seam plus the real producer - committed through a
    real `BatchCoordinator` whose port is the ACT verifier. It claims PASSED; its endpoint verdict is not
    PASS; so the coordinator must not record a success. Three dependencies had to be honoured, each measured
    rather than assumed: `finish` needs a `window` or the capture never seals; a row's identifiers come from
    the physical audit rather than from `start(...)`, so that callable reports the lease's attempt; and the
    audit pair must be the pre-publish paths when the store verifies (CP-2777).
    """
    policy = load_endpoint_policy(POLICY)
    journal = CoordinatorJournal.create(tmp_path / "journal", "batch-a")
    try:
        root = tmp_path / "w00"
        verifier = ActCollectionResultVerifier(
            {"w00": root}, endpoint_inputs={"initial_target": [0.0] * 7, "final_target": [0.0] * 7,
                                            "endpoint_policy": policy})
        request = BatchRequestV2("batch-a", RunMode.EXECUTE, ("scene-1",), 1,
                                 tmp_path / "journal", BatchKindV2.FIRST_PASS)
        config = load_parallel_runtime_config_v2(
            Path(__file__).resolve().parents[1] / "config/mujoco/parallel_batch_v2.yaml")
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
                                "task8_success": True, "stopped_confirmed": True})
        manifest, scope = episode_audit_pair(store.episode_root)
        store.audit_manifest = manifest
        store.scope = scope
        sealed = store.seal(store.episode_root / "seal.json")

        # the verifier re-verifies the episode, so it needs the pair as well - and by now the store has published,
        # so this is the post-publish location (CP-2777)
        published_manifest, published_scope = episode_audit_pair(sealed / "episode")
        verifier.audit_manifest = published_manifest
        verifier.scope = published_scope
        result = coordinator.commit_result(current, str(sealed), request_key="result-1")
        # the episode claimed PASSED and the endpoint verdict was not PASS, so this is not a success
        assert result["status"] == "FAILED"
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
    """The contract the extraction fills: thirteen keys, checked where a wiring mistake should surface (CP-2845)."""
    complete = {key: None for key in PhysicalAuditAdapter.KEYS}
    adapter = PhysicalAuditAdapter(lambda at_s: complete)
    assert set(adapter(1.0)) == set(PhysicalAuditAdapter.KEYS)

    incomplete = {key: None for key in PhysicalAuditAdapter.KEYS if key != "phase"}
    with pytest.raises(ValueError, match="PHYSICAL_AUDIT_INCOMPLETE"):
        PhysicalAuditAdapter(lambda at_s: incomplete)(1.0)


def test_the_producer_pushes_the_runs_own_frames_when_it_has_them():
    """A live run must push the frames it captured, not zeroes: the capture compares a row's pixels against its
    acquisition (`ACQUISITION_PIXEL_MISMATCH`), so the frame source is injectable and defaults to zeroes only for a
    harness (CP-2847)."""
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
    """A live run feeds the synchronizer itself, so the live sampler must not push anything (CP-2848)."""
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
                                      "task8_success": True, "stopped_confirmed": True})
    assert summary.sample_count >= 1
    assert (episode_root / "seal.json").is_file()
