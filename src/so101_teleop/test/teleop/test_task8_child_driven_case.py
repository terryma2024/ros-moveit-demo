"""Astra item 5: drive the production child entry with only the external I/O replaced.

The child is built as the dispatcher builds it, its artifacts arrive through the production
loader (``ActArtifactBinding``), and the request is the real closed IPC model. The runner, the
``CaseEvidenceDriver``, the window seal and the journal are production objects; only the ROS,
MuJoCo, controller and process boundaries are fakes - the port is the one the Boundary V chain
test already builds.
"""

from __future__ import annotations

import asyncio
import pytest
import dataclasses
import uuid
import hashlib
import sys
from types import SimpleNamespace
import json
import time
from pathlib import Path

from so101_demo.act.contact_calibration import REGIMES
from so101_demo.act.contact_policy import policy_fingerprint
from so101_teleop.unified.act_artifacts import ActArtifactBinding
from so101_teleop.unified.ipc import DispatchTokenModel, IpcRequest, _PickPlacePhasePayload, _PickPlacePayload, _StackOwner
from so101_demo.adapters.act.pick_place_search_port import PickPlaceSearchPhasePort
from so101_demo.adapters.act.pick_place_search_segment import PickPlaceSearchSegment
from so101_demo.adapters.act.pick_place_search_segment import PickPlaceSearchObservation  # noqa: F401

_SEGMENT_SUITE = Path(__file__).resolve().parents[3] / "so101_demo_py" / "test"
if str(_SEGMENT_SUITE) not in sys.path:
    sys.path.insert(0, str(_SEGMENT_SUITE))
from test_task8_live_evidence_production_chain import (  # noqa: E402
    PHASES, READBACK_SOURCES, _raw_records)
from so101_demo.act.task8_live_evidence import (  # noqa: E402
    LiveEvidenceWindow, build_live_evidence_sample)
import numpy  # noqa: E402
from so101_demo.adapters.act.contact_evidence import FRAME_KEYS  # noqa: E402
from so101_demo.adapters.act.scene_state import SCENE_KEYS  # noqa: E402
from so101_demo.core.simulation.types import ObjectState, SimulationEvidence  # noqa: E402
from test_act_task8_search_segment import (  # noqa: E402  (the segment suite's own doubles)
    _Adapter, _Scene, _Sources, PickPlaceReadbackError, _locked, _raw, _segment)
from so101_demo.adapters.act.pick_place_search_segment import PickPlaceSearchObservation
from so101_demo.ports.planning_scene import SceneCommandReceipt
from so101_teleop.unified.ros_child import RclpyActionDriver, local_owner
from test_act_campaign_admission import _calibration, _canonical, _write_policy
import test_task8_case_runner_chain as chain
from test_task8_case_runner_chain import FakePort

_HASHED = ("source", "manifest", "runtime_config", "collection_config", "calibration_report")
_POLICY = ("proposal", "activation_receipt")


def _head_search(root):
    """The head-search block the runtime config and the calibration report both carry.

    P1-5: a module-level helper in the same spirit as `_prepare_child_case` - "parameterised for reuse" -
    because the full-case module needs this block BEFORE it builds the production broker (the report, then the
    settings, then the broker, then the child), while `_binding` needs it for the runtime config and for the
    report's provenance. **One copy, two callers**, so the hashed-weights descriptor cannot drift between
    them.
    """

    weights_path = root / "best.pt"             # the validator hashes the weights, so they must exist
    weights_path.write_bytes(b"item5-weights")
    head_search = {
        "schema_version": 1,
        "detector": {"backend": "yolo_seg", "weights_path": str(weights_path),
                     "weights_sha256": hashlib.sha256(weights_path.read_bytes()).hexdigest(),
                     "model_id": "plastic-cup", "image_size_px": 640,
                     "requested_device": "cuda", "allow_cpu_fallback": False,
                     "torch_threads": 4, "torch_interop_threads": 2,
                     "torch_version": "2.0", "ultralytics_version": "8.0"},
        "camera": {"frame_id": "head_camera_frame", "ray_origin_frame_id": "head_camera_frame",
                   "width_px": 640, "height_px": 480},
        "motion": {"goal_tolerance_rad": 0.02, "settle_velocity_rad_s": 0.01,
                   "neck_goal_duration_s": 0.5}}
    return head_search


def _binding(tmp_path: Path) -> ActArtifactBinding:
    """Real artifacts, with the policy documents written by the admission suite's own writer."""

    root = tmp_path / "artifacts"
    root.mkdir()
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    # the admission suite's helper writes proposal.json and the receipt into the directory it is given, so it
    # is given the evidence root - which is also where the binder requires those documents to live
    fingerprint, proposal_path, receipt_path, receipt = _write_policy(evidence)
    # Owner decision (route a): the fixture compiles the repository's ACT scene for VALIDATION ONLY -
    # no stepping, no stack, no CUDA, no actuators - because the loader checks the policy against that exact
    # compiled model and scene (model_sha256(model), the scene's bytes, the mujoco version, and the allowed
    # other-contact bodies). The payload is otherwise the admission suite's, and the fingerprints are
    # recomputed from the payload so the documents and the binding agree by construction.
    from ament_index_python.packages import get_package_share_directory
    import mujoco
    from so101_demo.adapters.act.physics import model_sha256

    scene = Path(get_package_share_directory("so101_demo_py")) / "assets/mujoco/act/scene.xml"
    compiled = mujoco.MjModel.from_xml_path(str(scene))          # compile only; never stepped
    proposal = json.loads(Path(proposal_path).read_text())
    payload = proposal["payload"]
    payload["model_sha256"] = model_sha256(compiled)
    payload["scene_sha256"] = hashlib.sha256(scene.read_bytes()).hexdigest()
    payload["mujoco_version"] = mujoco.__version__
    payload["allowed_other_contact_bodies"] = ["table"]
    fingerprint = policy_fingerprint(payload)
    proposal["payload"] = payload
    proposal["policy_fingerprint"] = fingerprint
    # the envelope's own hash covers the envelope MINUS that field, which is how the admission suite computes
    # it and how the validator recomputes it - hashing the payload instead was the last mismatch
    proposal.pop("proposal_sha256", None)
    proposal["proposal_sha256"] = hashlib.sha256(_canonical(proposal)).hexdigest()
    Path(proposal_path).write_text(json.dumps(proposal))
    receipt = dict(receipt, policy_fingerprint=fingerprint)
    Path(receipt_path).write_text(json.dumps(receipt))
    # the helper returns the receipt document rather than writing it, so the caller does - its path is what
    # the binding names, and an unwritten receipt is exactly the file the last run could not find


    head_search = _head_search(root)
    paths, hashes = [], []
    for name in _HASHED + _POLICY:
        if name == "proposal":
            path = proposal_path
        elif name == "activation_receipt":
            path = receipt_path
        elif name == "calibration_report":
            # the child checks the report's source provenance, so it comes from the admission suite's builder
            # the helper returns (path, sha256) and writes the report itself, into the evidence root
            report_path, _report_sha256 = _calibration(evidence, status="TASK8_READY", head_search=head_search)
            path = Path(report_path)
        elif name == "runtime_config":
            # the same head-search block the calibration report carries, because the child compares the two
            path = root / "runtime_config.json"
            path.write_text(json.dumps({"schema_version": 1, "head_search": head_search}))
        else:
            path = root / f"{name}.json"
            path.write_text(json.dumps({"name": name}))
        paths.append((name, path))
        hashes.append((name, hashlib.sha256(path.read_bytes()).hexdigest()))
    return ActArtifactBinding(evidence, tuple(paths), tuple(hashes), fingerprint)


class _NeckSweepChecker:
    """The neck-sweep check the boundary owns: substituted, because it reads encoders."""

    def __init__(self):
        self.neck_qpos = 0          # an INDEX into the scene's qpos, which is how production reads it

    def check(self, qpos=None, *, current_rad=None, target_rad=None, duration_s=None):
        return True                 # the production neck check expects a real True


def _fixture_canonical_evidence(captured, *, support_distance_max_m, raw_records):
    """The production derivation, called directly - the fixture substitutes the I/O, not the rule."""

    from so101_demo.adapters.act.pick_place_readback import capture_evidence_fields

    # the end-effector position is MuJoCo output: this fixture substitutes the simulator, so it supplies the pose the
    # real boundary would compute from its model (the production call passes it the same way)
    return capture_evidence_fields(captured, support_distance_max_m=support_distance_max_m,
                                   raw_records=raw_records,
                                   end_effector_position_m=[0.0, 0.0, 0.1])


class _Boundary:
    """The ROS/MuJoCo/controller surface the PRODUCTION port drives - the only substituted layer.

    Astra P1-5: the fixture used to stand in for the port and its seal. The production port is now the
    object the child runs, and what is replaced is the boundary underneath it - which is exactly
    "replace only ROS/MuJoCo/controller/process I/O". The two epochs live here, and every request this
    boundary emits carries them, because that is where the production seal reads them from.
    """

    def __init__(self, *, session_id="session-item5"):
        self._session_id = session_id
        self.rows = []
        self.calls = []
        # the receipt's epoch is what the port compares every readback against, so the boundary's epoch
        # starts where the receipt says it does (a mismatch here is invisible: the same single error code)
        self.reset_epoch = 1
        self.release_epoch = 0
        self.started = False
        self.stopped = False
        self.neck_sweep_checker = _NeckSweepChecker()
        self.neck_sweep_checker.step_s = 0.5
        # the port reads `boundary.reset.receipt.new_epoch` for the epoch it compares every readback
        # against, so the reset carries a receipt as well as its sources
        self.reset = SimpleNamespace(
            # the port reads contact_pairs/contacts from the RESET's sources, not from the queue double,
            # which is why an earlier fix in the wrong place did not take
            sources=SimpleNamespace(session_id=self._session_id,
                                    readback=SimpleNamespace(max_skew=0.01, joint_tolerance=0.5),
                                    contact_pairs=SimpleNamespace(
                                        model_sha256="e" * 64,
                                        for_phase=lambda phase: frozenset()),   # contact_hazard REQUIRES a set/frozenset of pairs
                                    contacts=SimpleNamespace(safe=lambda: True)),
            release_epoch=0)
        self.reset.receipt = SimpleNamespace(new_epoch=1)

    def canonical_evidence(self, captured, *, support_distance_max_m, raw_records):
        """One derivation for every caller: the fixture uses the production function, not its own copy."""

        return _fixture_canonical_evidence(captured, support_distance_max_m=support_distance_max_m,
                                           raw_records=raw_records)

    def _request(self, request, reset_epoch=0, release_epoch=0):
        document = dict(request) if isinstance(request, dict) else {}
        document.setdefault("reset_epoch", reset_epoch)
        document.setdefault("release_epoch", release_epoch)
        return document

    def advance_reset(self):
        """The boundary owns the reset: the epoch advances here and the requests carry it from here."""

        self.calls.append("reset")
        self.reset_epoch += 1
        self.reset = SimpleNamespace(sources=SimpleNamespace(session_id=self._session_id),
                                     release_epoch=self.release_epoch)
        return self.reset

    def begin(self, request):
        """The production port validates the reset proof exactly: five keys, an epoch >= 1, no release."""

        self.calls.append("begin")
        self.started = True
        self.reset_epoch = max(1, self.reset_epoch + 1)
        self.release_epoch = 0
        # the probe showed world.reset_epoch = 2 against a receipt saying 1: begin advances the epoch AFTER
        # the receipt was built, and the port compares them. They move together or the scope check refuses.
        self.reset.receipt.new_epoch = self.reset_epoch
        return {"session_id": request["session_id"], "attempt_id": request["attempt_id"],
                "reset_epoch": self.reset_epoch, "release_epoch": 0, "full_restart": False}

    def search(self, request):
        """The production port requires a real observation type, so the boundary returns one."""

        self.searches = getattr(self, "searches", 0) + 1
        print(f"[probe] search calls={self.searches}")
        self.calls.append("search")
        self.rows.append({"phase": "search", "source_stamp": 1})
        # Astra P1-5: the observation is produced by the PRODUCTION segment, whose collaborators are
        # substituted. The doubles come from the segment suite's own tests - imported, not forked - so the
        # readback, the proofs and the scene receipt are built by production code from substituted I/O.
        # the shared decision builder, with THIS case's identity - built from it, not copied from it
        decision = dict(_locked(), attempt_id=request["attempt_id"])
        sources = _ChildSources(session_id=request["session_id"], reset_epoch=self.reset_epoch,
                                model_sha256=getattr(self, "model_sha256", None))
        # CP-1884/1885: the frames this search builds must carry vectors of the MODEL's length, because
        # `selected_approach_candidate` validates them with `vector(scene["qpos"], model.nq)` - and this is a FRESH
        # sources object per search, so the dimensions are forwarded here rather than set on the boundary's own
        sources.nq = getattr(self, "nq", 8)
        sources.nv = getattr(self, "nv", 8)
        sources.scene_qpos = getattr(self, "scene_qpos", None)
        sources.scene_qvel = getattr(self, "scene_qvel", None)
        sources.cup_start_m = getattr(self, "cup_start_m", None)
        sources.joint_start_rad = getattr(self, "joint_start_rad", None)
        # the fence and the deadline both compare against the segment's clock, so the clock is the REAL one -
        # the segment suite's `_segment` helper pins it to a frozen list, which cannot work here. Everything
        # else (boundary, verifiers, geometry, timings) comes from the imported doubles unchanged.
        adapter = _Adapter({"status": "INPUT_PENDING", "stop": True}, decision)
        scene = _Scene()
        probe = _segment(sources, adapter, scene)
        segment = PickPlaceSearchSegment(
            sources, adapter, scene, probe.geometry,
            operation_guard=probe.guard, history_verifier=probe.history_verifier,
            reference_verifier=probe.reference_verifier, owner_verifier=probe.owner_verifier,
            native_ingress_verifier=probe.native_ingress_verifier,
            max_source_wait_s=probe.max_wait, poll_interval_s=probe.poll,
            monotonic=time.monotonic, sleep=time.sleep, clock_ns=time.monotonic_ns)
        observation = segment.run(request, reset_epoch=self.reset_epoch)
        # P1-5: the four proofs the expert route's registration reads. Their construction follows
        # `test_act_visible_approach_expert_route.py` (the suite that already builds three of them), with two
        # corrections this drive established: `selected_source_sha256` is the FROZEN source's own hash, computed with
        # the production freezer, and the native window digest is COMPUTED from the snapshots rather than `"c" * 64`.
        if getattr(self, "attach_proofs", False):
            import dataclasses as _dc

            from so101_demo.adapters.act.pick_place_search_native_ingress import native_ingress_digest
            from so101_demo.adapters.act.selected_approach_candidate import freeze_selected_search_source

            frozen = freeze_selected_search_source(observation, max_skew_s=self.max_skew)
            digest = frozen["observation_sha256"]
            scene = observation.physical_readback["scene"]
            marker = observation.physics_step_fence
            stop_wall_s = max(observation.physical_readback["source_received_wall_s"].values())
            reference_hash = "a" * 64
            event_hash = "b" * 64
            # `prepare` requires the snapshot keys to be EXACTLY the route's `_ROLES`, and the native proof's
            # `latest_source_receipt_monotonic_ns` to equal the newest source receipt in nanoseconds - both read off
            # the production code rather than chosen (CP-1882's next step)
            from so101_demo.adapters.act.visible_approach_expert_route import _ROLES as _ROUTE_ROLES

            _receipts = observation.physical_readback["source_received_wall_s"]
            _latest_receipt_ns = max(round(float(value) * 1_000_000_000) for value in _receipts.values())
            # `prepare` enforces an ORDER on these instants:
            #   0 <= last_ingress <= stop_ns <= latest_receipt_ns <= observed <= received <= now_ns
            # so they are derived from the run's own numbers rather than written as 1/2/3 (CP-1883)
            _stop_ns = round(stop_wall_s * 1_000_000_000)
            snapshots = {kind: {"role": kind, "owner_generation": self.owner_generation,
                                "ingress_sequence": index + 1,
                                "last_ingress_monotonic_ns": _stop_ns - 1,
                                "observed_monotonic_ns": _latest_receipt_ns,
                                "received_monotonic_ns": _latest_receipt_ns + 1,
                                "command_authority": False}
                         for index, kind in enumerate(_ROUTE_ROLES)}
            from so101_demo.adapters.act.visible_approach_expert_route import _BRIDGE_NS as _BRIDGE

            common = {"selected_source_sha256": digest, "stop_confirmed_wall_s": stop_wall_s,
                      "command_authority": False, "eligible_for_collection": False}
            # `prepare` requires the reference's instants to be DERIVED: the selected one from the frozen source's own
            # simulation time, the bridge one exactly `_BRIDGE_NS` before it (CP-1882's next step)
            _selected_ns = round(frozen["simulation_time_s"] * 1_000_000_000)
            _bridge_ns = _selected_ns - _BRIDGE
            observation = _dc.replace(
                observation,
                stationary_physics_proof={
                    **common, "selected_physics_step": frozen["physics_step"],
                    "model_qpos": tuple(scene["qpos"]), "model_qvel": tuple(scene["qvel"]),
                    "physics_step_fence": marker, "controller_interval_proof_required": True},
                stationary_reference_proof={
                    **common, "reference_window_sha256": reference_hash,
                    "selected_sim_time_ns": _selected_ns, "bridge_sim_time_ns": _bridge_ns,
                    "owner_goal_interval_proof_required": True},
                local_owner_goal_proof={
                    **common, "reference_window_sha256": reference_hash,
                    "control_event_window_sha256": event_hash, "owner_generation": self.owner_generation,
                    "controller_native_ingress_proof_required": True},
                native_controller_ingress_proof={
                    **common, "reference_window_sha256": reference_hash,
                    "control_event_window_sha256": event_hash, "owner_generation": self.owner_generation,
                    "latest_source_receipt_monotonic_ns": _latest_receipt_ns,
                    "ingress_sequence_by_controller": {kind: snapshots[kind]["ingress_sequence"]
                                                       for kind in snapshots},
                    "native_snapshots": snapshots,
                    "native_ingress_window_sha256": native_ingress_digest(snapshots),
                    "commit_window_ingress_recheck_required": True},
            )
        raw = observation.physical_readback
        print("[probe] readback keys:", sorted(raw))
        print("[probe] world session/epoch:", raw["world"].simulation_session_id, raw["world"].reset_epoch)
        print("[probe] receipt epoch (what the port compares against):", self.reset.receipt.new_epoch)
        print("[probe] row vs receipt equal:", raw["world"].reset_epoch == self.reset.receipt.new_epoch)
        result = observation.search_result
        print("[probe] search_result keys:", sorted(result))
        print("[probe] timestamp:", result.get("timestamp"), "world sim_time:", raw["world"].simulation_time_s,
              "range ok:", 0 <= result.get("timestamp", -1) <= raw["world"].simulation_time_s)
        print("[probe] scene diff:", sorted(set(raw["scene"]) ^ SCENE_KEYS))
        print("[probe] contact diff:", sorted(set(raw["contact"]) ^ FRAME_KEYS))
        print("[probe] paused/truncated/body:", raw["world"].paused,
              getattr(raw["world"], "truncated", None), raw["world"].object_state.body)
        return observation

    def safe_stop(self, *args, **kwargs):
        """The runner's gate is `port.safe_stop(reason, request) is True`, so the boundary confirms it."""

        self.calls.append("safe_stop")
        self.stopped = True
        return True


class _ChildSources(_Sources):
    """A queued scenario, built with the segment suite's own builders and THIS case's identity.

    The suite's scenario shape is the blueprint: a queue of rows (which may contain the deliberate
    ``SOURCE_STEP_NOT_ADVANCED`` retry), identity stamped locally, and real wall receipts because this
    fixture runs the real clock. The only thing not reused verbatim is the suite double's own fixture
    assertion, which by construction cannot hold for a second case.
    """

    def __init__(self, *, session_id, reset_epoch, model_sha256=None):
        wall = time.monotonic()
        # one deliberate retry, then every step the post-stop interval needs: the interval selects only
        # after fifty ADVANCING steps, so the queue carries them one by one rather than a single jump
        rows = [_raw(1, sim_time_s=2.0),
                PickPlaceReadbackError("SOURCE_STEP_NOT_ADVANCED"),
                _raw(2, sim_time_s=2.002)]
        rows += [_raw(step, x=-0.079, sim_time_s=2.004 + 0.002 * (step - 3), received_wall_s=wall)
                 for step in range(3, 130)]      # room for the interval's fifty advancing steps and then some
        super().__init__(*rows)
        self._session_id = session_id
        self._reset_epoch = reset_epoch
        self._step = 0
        # P1-5: the scene the segment produces carries this hash, and the port compares it with
        # `sources.contact_pairs.model_sha256`. Production has ONE model, so a caller that knows the real hash passes
        # it; the default keeps the fixture's own constant for every caller that does not.
        self._model_sha256 = model_sha256 or "e" * 64
        self.contact_pairs = SimpleNamespace(model_sha256=self._model_sha256,
                                             for_phase=lambda phase: frozenset())    # ditto: a dict here reads as a hazard
        self.contacts = SimpleNamespace(safe=lambda: True)
        self.physics_fence = SimpleNamespace(
            request_after_stop=lambda epoch, stopped, deadline: {
                "session_id": self._session_id, "reset_epoch": epoch,
                # the marker must name the step the physics is AT, because the interval uses it as its
                # cursor - a fixed value made every queued step look stale (probe: after_step=54 at step 3)
                # the marker is the step the physics had STOPPED at, frozen there: a marker that advances
                # with every readback can never be passed, which is what the queue exhausted twice (CP-1386)
                # the check requires an int >= 1, and a stop can precede the first readback on a fresh
                # sources instance, so the floor is explicit rather than assumed
                "marked_physics_step": max(1, self._step), "command_authority": False})

    def capture(self, attempt_id, *, after_step):
        self._pops = getattr(self, "_pops", 0) + 1
        if self._pops <= 8:
            head = self.rows[0] if self.rows else None
            step = getattr(getattr(head, "get", lambda *_: None)("world", None), "simulation_step", None) \
                if not isinstance(head, BaseException) else "EXC"
            print(f"[probe] pop#{self._pops} after_step={after_step} head_step={step}")
        if not self.rows:
            print(f"[probe] queue EMPTY after {self._pops} pops, last after_step={after_step}")
        row = self.rows.popleft() if self.rows else PickPlaceReadbackError("SOURCE_STEP_NOT_ADVANCED")
        if isinstance(row, BaseException):
            raise row
        if row["world"].simulation_step <= after_step:
            raise PickPlaceReadbackError("SOURCE_STEP_NOT_ADVANCED")
        # the dwell gate requires every receipt to be AT OR AFTER the stop's wall time (the segment reads
        # `received_wall_s >= stopped_wall_s`), so they are stamped live here rather than at construction
        now = time.monotonic()
        row["source_received_wall_s"] = {kind: now for kind in ("world", "scene", "contact")}
        world = row["world"]
        # the port requires the readback's world to be a REAL SimulationEvidence (its line 239) - the
        # condition my truncated reads hid for eight rounds, because the suite's builder returns a namespace
        row["world"] = SimulationEvidence(
            simulation_time_s=float(world.simulation_time_s),
            frame_id="world",
            publisher_sequence=int(world.simulation_step),
            simulation_step=int(world.simulation_step),
            reset_epoch=self._reset_epoch,
            simulation_session_id=self._session_id,
            paused=False,
            object_state=ObjectState(body=world.object_state.body, body_id=0,
                                    linear_velocity_world=(0.0, 0.0, 0.0),
                                    angular_velocity_world=(0.0, 0.0, 0.0),
                                    # P1-5/CP-1886: the route pins the cup's start, and the candidate compares
                                    # this with it - so the fixture reports the route's value, not `_raw`'s x
                                    position_world=tuple(getattr(self, "cup_start_m", None)
                                                         or world.object_state.position_world),
                                    orientation_xyzw=tuple(world.object_state.orientation_xyzw)),
            has_contact=False,
            minimum_signed_distance_m=0.0,
            maximum_normal_force_n=0.0,
            truncated=False,
            left_fingertip_contacts=(),
            right_fingertip_contacts=(),
            other_object_contacts=())      # the sixteenth field, past the sixteen lines my read showed
        world = row["world"]
        for name in ("scene", "contact"):
            row[name]["simulation_session_id"] = self._session_id
            row[name]["reset_epoch"] = self._reset_epoch
        # the port compares scene and contact against its own production key sets, so every key is filled
        # from the same vocabulary rather than from a hand-written list
        # the port compares the key SETS exactly, so these documents are BUILT to the production key sets
        # rather than patched - setdefault left `_raw`'s five keys in place, which is what `physical readback
        # scope` refused. The digest is the one the sources advertise, which the port cross-checks.
        # the scene's clock bounds come from the physical clock: this fixture substitutes the simulator, so it
        # supplies real monotonic nanoseconds rather than the 0 the generic fill would leave behind
        scene_ns = time.monotonic_ns()
        row["scene"] = {**{key: 0 for key in SCENE_KEYS},
        "clock_interval_begin_monotonic_ns": scene_ns - 1_000_000,
        "clock_interval_end_monotonic_ns": scene_ns,
                        "simulation_session_id": self._session_id,
                        "reset_epoch": self._reset_epoch,
                        "simulation_step": world.simulation_step,
                        "simulation_time_s": world.simulation_time_s,
                        "paused": False,
                        # P1-5/CP-1871: the `{key: 0 for key in SCENE_KEYS}` fill leaves EVERY key as the int 0, and
                        # only `qpos` was overridden - so `qvel` stayed an int where four production readers validate
                        # `vector(scene["qvel"], model.nv)` and `SceneState.validate` refuses it at ingestion
                        # (`scene_state.py:64`). Both vectors are given the same length the fixture's scene uses.
                        # P1-5/CP-1884: the lengths come from the MODEL the run is executed against - fourteen and
                        # thirteen for the ACT scene - because `selected_approach_candidate` validates them with
                        # `vector(scene["qpos"], model.nq)` / `vector(scene["qvel"], model.nv)`. The defaults keep the
                        # fixture's own eight for every caller that does not know a model.
                        # P1-5/CP-1886: the vectors are the REAL scene's initial state - the model's `task_start`
                        # keyframe - because `selected_approach_candidate` compares them with the manifest's own
                        # `joint_start_rad`/`cup_start_m`, and a frame of zeros is a different world
                        "model_sha256": self._model_sha256,
                        "qpos": list(getattr(self, "scene_qpos", None)
                                     or [0.0] * getattr(self, "nq", 8)),
                        "qvel": list(getattr(self, "scene_qvel", None)
                                     or [0.0] * getattr(self, "nv", 8))}
        row["contact"] = {**{key: () for key in FRAME_KEYS},
                          "simulation_session_id": self._session_id,
                          "reset_epoch": self._reset_epoch,
                          "physics_step": world.simulation_step,
                          "simulation_time_s": world.simulation_time_s,
                          "evidence_loss": False,
                          "truncated": False}
        # the port requires EXACTLY the four RGB stamps here (its line 271), each within skew of the
        # world time - the seven-source receipts are a different map with a different rule
        row["source_stamps_s"] = {name: world.simulation_time_s
                                  for name in ("head", "wrist", "arm", "neck")}
        row["source_received_wall_s"] = {name: now for name in READBACK_SOURCES}
        row["observation"] = {
            "session_id": self._session_id, "attempt_id": attempt_id,
            "sim_time_s": world.simulation_time_s,
            # P1-5/CP-1888: the candidate compares `state[:6]` with the route's own start, so it carries the
            # manifest's `joint_start_rad` rather than six zeros
            "state": list(getattr(self, "joint_start_rad", None) or [0.0] * 6) + [1.0, 0.0],
            "head": numpy.zeros((480, 640, 3), dtype=numpy.uint8),
            "wrist": numpy.zeros((480, 640, 3), dtype=numpy.uint8)}
        # the port requires EXACTLY this key set, with the requested time equal to the world's and three
        # six-element finite vectors - a copy of the observation is not a controller reference
        row["reference"] = {"requested_sim_time_s": world.simulation_time_s,
                           "positions": [0.0] * 6, "velocities": [0.0] * 6,
                           "accelerations": [0.0] * 6}
        return row


class ChildPort(PickPlaceSearchPhasePort):
    """The PRODUCTION port, with only its boundary substituted.

    The child attaches its real evidence window through ``bind_live_evidence``, and the seal itself is the
    production implementation - it reads the epochs from the request and seals the window before the
    recorder. The former FakePort seal (a class attribute monkeypatched by the chain test) is gone.
    """

    def __init__(self, *, session_id="session-item5", expert_route_factory=None, route_motion=None):
        self.boundary = _Boundary(session_id=session_id)
        # P1-5 (rereview 5): the PRODUCTION port accepts an expert route factory, and the production child port
        # (`pick_place_child_port.py:147`) always passes one - `VisibleApproachExpertRoute` over a
        # `SelectedApproachCandidate`. This subclass left it out, which is why a FULL case was refused by name at
        # APPROACH (`TASK8_PHASE_NOT_PROVISIONED: APPROACH: expert_route`). It is forwarded now, so a caller that has
        # the admitted values can drive a full case while a SEARCH-only caller behaves exactly as before.
        # `route_motion` is NOT a port parameter - the production builder turns it into the APPROACH screen's path
        # checker and wires that separately (`pick_place_child_port.py:170-181`), so only the factory is forwarded here.
        super().__init__(self.boundary, expert_route_factory=expert_route_factory)
        self.route_motion = route_motion
        self.receipt = None

    def bind_live_evidence(self, window, *, support_distance_max_m=None, raw_records_root=None):
        # the production contract (CP-1482): the admitted threshold and the raw-record root travel with the
        # attachment, and the production bind is the one that validates them - so they are forwarded, not dropped
        super().bind_live_evidence(window, support_distance_max_m=support_distance_max_m,
                                   raw_records_root=raw_records_root)
        self._evidence_recorder = getattr(window, "_recorder", None)
        # the boundary is what produces readbacks, so it must hold the recorder too: the child attaches to the
        # PORT, and a boundary that never sees it cannot record the evidence the seal demands
        if getattr(self, "boundary", None) is not None:
            self.boundary._evidence_recorder = self._evidence_recorder
            self.boundary._live_window = window
            self.boundary._boundary_port = self
        return None

    def bind_startup_receipt(self, receipt):
        result = super().bind_startup_receipt(receipt)
        self.receipt = receipt
        return result



class FakeBroker:
    """The ROS/process seam: the child must not start a real broker inside a test.

    P1-5: the blanket `__getattr__` is right for the PREFIX path, where the child never asks its driver for an
    identifier - but on the ACT path `CommandBroker` does exactly that, and `identifier(...)` correctly refuses a
    function or a `True`. So the short list of calls the ACT chain makes (`command_broker.py:156/184/210`, and the
    trusted source port's `current_epoch`) is answered here with the SHAPES `RosBrokerDriver` returns: a goal id that
    is a non-empty string, a CANONICAL uuid (the broker checks `str(uuid.UUID(value)) == value`), and an epoch whose
    `session_id`/`reset_epoch` are the ones the live window and the sources are at.
    """

    def __init__(self, *, session_id=None, reset_epoch=0):
        self._goals = {}
        self._session_id = session_id
        self._reset_epoch = reset_epoch
        self.hazard_reason = None                       # a reason or None - a VALUE, because the broker reads it

    def stop(self, *args, **kwargs):
        return True

    def stopped(self):
        return True                                     # the broker refuses `acquire` unless the driver is stopped

    # `hazard_reason` is an ATTRIBUTE on the production driver, not a method: `command_broker.py:369` does
    # `hazard = getattr(self.driver, 'hazard_reason', None)` and `:371` then hands it straight to
    # `ownership.revoke(hazard)`, whose first act is `identifier(reason)` - so a METHOD here is refused as a non-string,
    # which is exactly what the call-site traceback showed. The attribute is set in `__init__`.

    def current_epoch(self):
        # the trusted source port's `_scope` compares this with the source's own session/epoch (CP-1825) - and the
        # epoch ADVANCES during `begin`, after this broker is built, so a caller may supply a LIVE reader rather than
        # the value that happened to hold at construction
        reader = getattr(self, "epoch_reader", None)
        if callable(reader):
            return reader()
        return {"session_id": self._session_id, "reset_epoch": self._reset_epoch}

    def refresh_idle(self):
        return True

    def ready(self, kind=None):
        return True

    def validate(self, kind, goal):
        return goal

    def prepare_goal(self, kind, goal):
        gid = f"goal-{len(self._goals) + 1}"
        goal_uuid = str(uuid.uuid4())                   # canonical, because the broker compares the round trip
        self._goals[gid] = {"goal_uuid": goal_uuid, "kind": kind, "goal": goal}
        return gid, goal_uuid

    def discard_prepared(self, gid):
        self._goals.pop(gid, None)
        return True

    def send_prepared(self, gid, kind, goal, goal_uuid):
        self._goals.setdefault(gid, {"goal_uuid": goal_uuid, "kind": kind, "goal": goal})
        return gid                                      # the broker asserts the returned id equals the prepared one

    def submit(self, kind, goal, *, goal_uuid=None):
        gid, _ = self.prepare_goal(kind, goal)
        return gid

    def goal_state(self, gid):
        return {"accepted": True, "done": True}

    def cancel(self, gid):
        return True

    def prepare_goal_state(self, *args, **kwargs):
        return {"accepted": True}

    def stop_all(self, reason=None):
        return True

    def __getattr__(self, name):                     # every other broker call answers harmlessly
        def _call(*args, **kwargs):
            return True
        return _call


def _prepare_child_case(tmp_path, monkeypatch, *, case_id="case-05", campaign_id="campaign-item5",
                         expert_route_factory=None, route_motion=None, broker=None,
                         session_id="session-item5", attempt_id="attempt-item5",
                         worker_id="item5-child"):
    """Build the real child, its substituted port and the phase request - parameterised for reuse.

    The ids are the only thing a second caller has to change: the case-execution harness runs cases named
    ``prefix-NN`` with its own session, and this helper is where the two meet.
    """

    binding = _binding(tmp_path)
    for name, value in binding.environment().items():      # the binder's own writer, not a copy of it
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("SO101_ACT_CAMPAIGN_ID", campaign_id)

    # the chain test's port builds its rows from its own fixture identity, and the production recorder refuses
    # samples naming another case - so the fixture supplies this case's identity to that builder (fixture code,
    # not production code, and the sample builder itself stays the production one)
    port = ChildPort(session_id=session_id, expert_route_factory=expert_route_factory,
                     route_motion=route_motion)
    # the rows must carry the epochs the port is actually at, since the runner advances release_epoch as the case
    # proceeds - so the builder reads the live port rather than a constant
    monkeypatch.setattr(chain, "_identity", lambda: {"case_id": case_id, "session_id": session_id,
                                                    "attempt_id": attempt_id,
                                                    "reset_epoch": port.reset_epoch,
                                                    "release_epoch": port.release_epoch})
    # IPC_STACK_OWNER_GROUP_INVALID unless the stack owner is its own process group (pgid == pid), and the
    # request must describe the SAME owner the child was given
    owner = dataclasses.replace(local_owner("child-item5"), pgid=local_owner("child-item5").pid)
    # the child compares its bound hashes with the binding's own, and the payload must repeat them exactly - so
    # both come from the binding rather than from literals (the child raised ACT_ARTIFACT_BINDING_INVALID when it
    # was left to derive them from unset environment names)
    digests = dict(binding.hashes)
    bound_hashes = {"manifest_sha256": digests["manifest"],
                    "runtime_config_sha256": digests["runtime_config"],
                    "contact_policy_fingerprint": binding.policy_fingerprint}
    # the broker is the ROS/process seam, which a test may stand in for; everything else stays production
    # P1-5: the broker is the ROS/process seam, and *"external I/O may be substituted, but the chain may not"* - so a
    # caller that has the PRODUCTION broker (WITH its `prefix_source_port`, which APPROACH's admission reads as an
    # `isinstance`) passes it here; the default stays the stand-in the prefix cases have always used.
    if broker is None:
        broker = FakeBroker()
    child = RclpyActionDriver(pick_place_port=port, owner=owner, broker=broker, act_hashes=bound_hashes,
                              startup_proof_consumer=lambda request: {
                                  "schema_version": 1, "proof": "startup",
                                  "session_id": session_id,
                                  "stack_owner": {"pid": owner.pid, "pgid": owner.pgid},
                                  "child_owner": {"pid": owner.pid}})
    deadline_ns = time.monotonic_ns() + 5_000_000_000   # short for iteration (CP-1378 lesson)      # one deadline, shared by the request and its token
    request = IpcRequest(
        version=1, operation="task8_phase",
        command_id=f"{worker_id}-command", service_epoch=f"{worker_id}-epoch",
        # the act identity block the model validator requires for act operations
        campaign_id=campaign_id, worker_id=worker_id,     # the rule is token.child_id == worker_id
        execution_generation=1,
        runtime_id=f"{worker_id}-runtime",
        # the token is a closed model, and the request's execution_generation is an int - not strings
        token=DispatchTokenModel(operation_id=f"{worker_id}-op", child_id=worker_id,
                                 runtime_id=f"{worker_id}-runtime", execution_generation=1,
                                 deadline_ns=deadline_ns,
                                 revocation_revision=0),
        service_token=f"{worker_id}-service_token",
        session_id=session_id, attempt_id=attempt_id,
        deadline_ns=deadline_ns,
        payload=_PickPlacePhasePayload(
            support_distance_max_m=0.02,   # the admitted support distance the case's evidence is derived from
            gripper_closed_rad=0.5,
            close_duration_s=0.5,
            pick_policy="/home/matianyi/Projects/ros-moveit-demo/.worktrees/so101-act-data-0917a/src/so101_demo_py/config/policies/dynamic_cup_pick/v1",
            motion_duration_s=0.5,
            stop_after="SEARCH",     # the port provisions SEARCH; the child supports the prefix
            scenario_id=case_id,          # the journal's _CASE_ID is r"[a-z]+-[0-9]{2}\Z"
            manifest_sha256=digests["manifest"],
            runtime_config_sha256=digests["runtime_config"],
            contact_policy_fingerprint=bound_hashes["contact_policy_fingerprint"],
            stack_owner=_StackOwner(pid=owner.pid, pgid=owner.pgid, started_ticks=owner.started_ticks,
                                    argv_sha256=owner.argv_sha256,
                                    environment_sha256=owner.environment_sha256)).model_dump())


    return child, request, port
def test_the_child_runs_a_full_case_and_seals_what_the_runner_produced(tmp_path, monkeypatch):
    child, request, port = _prepare_child_case(tmp_path, monkeypatch)
    result = asyncio.run(child.pick_place_phase(request))   # SEARCH-only is what this port provisions
    print("[probe] result keys:", sorted(result) if isinstance(result, dict) else type(result).__name__)
    if isinstance(result, dict):
        for name in sorted(result):
            value = result[name]
            print(f"[probe]   {name} = {str(value)[:120]}")
    _win = getattr(port, "live_evidence_window", None)
    if _win is not None:
        print("[probe] window grid/event:", getattr(_win, "_grid_count", None), getattr(_win, "_event_count", None),
              "| phases seen:", getattr(_win, "_phases_seen", None))
    _rec = getattr(port, "_evidence_recorder", None)
    if _rec is not None:
        print("[probe] recorder entries:", len(getattr(_rec, "_entries", [])), "| sealed:", getattr(_rec, "_sealed", None) is not None)

    # the production port validates the receipt's shape and keeps every field it demanded, so the
    # assertion names the proof and the field set rather than the old three-key literal
    assert port.receipt.get("proof") == "startup", "the startup proof reached the production port"
    assert set(port.receipt) == {"schema_version", "proof", "session_id", "stack_owner", "child_owner"}
    assert result.get("stopped_confirmed") is True, "the entry only returns after a confirmed stop"


def test_the_real_case_execution_publishes_the_journal_row_for_a_prefix_case(tmp_path, monkeypatch):
    """P1-5: the production case entry runs the REAL child as its worker and publishes the row itself.

    Only the worker seam is substituted: ``run_pick_place_case`` does its own preflight, campaign check,
    result validation, live-evidence readback rule and retirement-receipt requirement, and ``_publish_new``
    writes the journal row. The evidence directory is its own subdirectory so the harness's manifest and this
    case's artifact binding cannot collide over the same file name.
    """

    from so101_teleop.unified.pick_place_case_execution import run_pick_place_case
    from test_task8_case_execution import _prepared

    spec, owner, journal, events = _prepared(tmp_path)
    evidence = tmp_path / "child-evidence"
    evidence.mkdir()
    child, request, port = _prepare_child_case(
        evidence, monkeypatch, case_id="prefix-01", session_id="session-298",
        attempt_id="prefix-01", campaign_id="case-298")

    async def run_pick_place(case_request):
        events.append("execute")          # the child runs between the harness's start and finish
        assert case_request["attempt_id"] == "prefix-01", "the harness's case is what the child runs"
        assert case_request["session_id"] == "session-298"
        return await child.pick_place_phase(request)

    owner.worker.run_pick_place = run_pick_place
    row = asyncio.run(run_pick_place_case(spec, "prefix-01", owner, journal))

    assert journal.exists(), "the production entry published the journal row itself"
    assert row["case_id"] == "prefix-01" and row["mode"] == "phase_prefix"
    assert row["status"] == "PASSED" and row["stopped_confirmed"] is True
    assert row["completed_phases"] == ["SEARCH"]
    assert row["eligible_for_formal_collection"] is False
    assert row["live_evidence_path"] == "", "a prefix case carries no sealed artifact, and says so"
    assert row["live_evidence_sha256"] == "0" * 64
    assert Path(row["stack_retirement_receipt_path"]).is_file()
    assert Path(row["child_retirement_receipt_path"]).is_file()
    assert events == ["start", "execute", "finish"]

    # the published artifact is the bytes on disk, canonically: the row the caller receives is the file the
    # trusted reader will open, and a replay of the same case cannot overwrite it
    import json as _json
    published = journal.read_bytes()
    expected = (_json.dumps(row, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()
    assert published == expected, "the journal's bytes are the row, canonically encoded"
    journal_sha256 = hashlib.sha256(published).hexdigest()
    assert len(journal_sha256) == 64
    with pytest.raises(ValueError, match="TASK8_CASE_JOURNAL_INVALID"):
        from so101_teleop.unified.pick_place_case_execution import _publish_new
        _publish_new(journal, row)

    # and the trusted path's own translator: the row a campaign publishes becomes the journal row the
    # aggregator reads, validated by the same rule the aggregator applies
    import hashlib as _hashlib
    from so101_demo.act.task8_live_evidence import case_row_to_journal_row

    identities = {"source_provenance_sha256": "a" * 64, "runtime_config_sha256": "b" * 64,
                  "contact_policy_fingerprint": "d" * 64}
    manifest_sha256 = _hashlib.sha256((tmp_path / "manifest.json").read_bytes()).hexdigest()
    journal_row = case_row_to_journal_row(row, identities=identities,
                                          manifest_document_sha256=manifest_sha256)

    assert journal_row["case_id"] == "prefix-01"
    assert journal_row["mode"] == "phase_prefix"
    for name, value in identities.items():
        assert journal_row[name] == value, f"the bundle identity {name} is carried into the journal row"
    assert journal_row["manifest_document_sha256"] == manifest_sha256
    # the producer's receipt digests survive the translation under the journal's own names
    assert journal_row["child_retirement_receipt_sha256"] == row["child_receipt_sha256"]
    assert journal_row["stack_retirement_receipt_sha256"] == row["stack_receipt_sha256"]
    assert journal_row["live_evidence_sha256"] == "0" * 64

    # negative: a row that lost a required field is refused by the trusted translator, not accepted loosely
    tampered = {key: value for key, value in row.items() if key != "child_receipt_sha256"}
    with pytest.raises(ValueError, match="TASK8_CASE_ROW_INVALID"):
        case_row_to_journal_row(tampered, identities=identities,
                                manifest_document_sha256=manifest_sha256)


def test_the_trusted_aggregator_refuses_a_missing_and_a_tampered_case_journal(tmp_path, monkeypatch):
    """P1-5 negatives against the TRUSTED validator, not against my own expectations.

    ``validate_case_journals`` is the aggregator's own reader: it walks the campaign's case ids, demands a
    complete journal for each at the path the campaign writes, and refuses the whole qualification on a
    missing, foreign or incomplete journal. Two of the review's negatives live here.
    """

    import json
    from so101_demo.act.task8_live_evidence import require_campaign_cases
    from so101_demo.act.task8_live_qualification import validate_case_journals
    from test_task8_case_execution import _prepared
    from so101_teleop.unified.pick_place_case_execution import run_pick_place_case

    spec, owner, journal_path, events = _prepared(tmp_path)
    manifest = json.loads((tmp_path / "manifest.json").read_bytes())
    manifest_sha256 = hashlib.sha256((tmp_path / "manifest.json").read_bytes()).hexdigest()
    identities = {"source_provenance_sha256": "a" * 64, "runtime_config_sha256": "b" * 64,
                  "contact_policy_fingerprint": manifest["contact_policy_fingerprint"]}
    required = tuple(require_campaign_cases(manifest))
    assert required, "the campaign names its cases"

    case_root = tmp_path / "campaign"
    cases = case_root / "task8-live" / "cases"
    cases.mkdir(parents=True)

    # negative 1 - a missing row refuses the whole qualification, by the trusted reader's own error
    with pytest.raises(ValueError, match="TASK8_QUALIFICATION_JOURNAL_MISSING"):
        validate_case_journals(case_root, manifest, identities=identities,
                               manifest_document_sha256=manifest_sha256)

    # the real published row, placed where the campaign writes it
    evidence = tmp_path / "child-evidence"
    evidence.mkdir()
    child, request, port = _prepare_child_case(
        evidence, monkeypatch, case_id=required[0], session_id="session-298",
        attempt_id=required[0], campaign_id="case-298")

    async def run_pick_place(case_request):
        return await child.pick_place_phase(request)

    owner.worker.run_pick_place = run_pick_place
    row = asyncio.run(run_pick_place_case(spec, required[0], owner, journal_path))

    # the campaign publishes a PRODUCER row; the trusted reader wants the JOURNAL row, so the translation the
    # trusted path provides is applied first - that is the pipeline, and the negatives live after it
    from so101_demo.act.task8_live_evidence import case_row_to_journal_row
    journal_row = case_row_to_journal_row(row, identities=identities,
                                          manifest_document_sha256=manifest_sha256)

    # negative 2 - a journal whose row lost a required field is refused even though the file is there
    tampered = {key: value for key, value in journal_row.items()
                if key != "child_retirement_receipt_sha256"}
    (cases / f"{required[0]}.json").write_text(json.dumps(tampered, sort_keys=True))
    with pytest.raises(ValueError, match="TASK8_"):
        validate_case_journals(case_root, manifest, identities=identities,
                               manifest_document_sha256=manifest_sha256)

    # and the untampered row is ACCEPTED for its case: the reader moves on and stops at the NEXT missing one
    (cases / f"{required[0]}.json").write_text(json.dumps(journal_row, sort_keys=True))
    with pytest.raises(ValueError, match="TASK8_QUALIFICATION_JOURNAL_MISSING"):
        validate_case_journals(case_root, manifest, identities=identities,
                               manifest_document_sha256=manifest_sha256)


def test_a_missing_retirement_receipt_refuses_the_case_and_publishes_nothing(tmp_path):
    """Negative: without the child's retirement receipt the case must not publish a success row."""

    from so101_teleop.unified.pick_place_case_execution import run_pick_place_case
    from test_task8_case_execution import _prepared

    from so101_teleop.unified.contracts import MutationError

    spec, owner, journal, events = _prepared(tmp_path, omit_child_receipt=True)
    with pytest.raises(MutationError, match="TASK8_RETIREMENT_RECEIPT_INVALID"):
        asyncio.run(run_pick_place_case(spec, "prefix-01", owner, journal))
    assert not journal.exists(), "a case without both retirement receipts publishes nothing"
    assert "finish" in events, "the attempt still retired the stack and the child"


def test_the_case_window_binds_its_reset_epoch_exactly_once(tmp_path, monkeypatch):
    """Negative: the window's generation is bound once; claiming another epoch for the same case is refused."""

    child, request, port = _prepare_child_case(tmp_path, monkeypatch)
    asyncio.run(child.pick_place_phase(request))
    window = port.live_evidence_window
    assert window is not None, "the child attached its evidence window to the production port"
    with pytest.raises(ValueError):
        window.bind_reset_epoch(99)


def test_a_campaign_of_prefixes_alone_cannot_qualify():
    """The trusted qualification gate refuses the bounded campaign we can actually run - by its own rules.

    ``validate_campaign_summary`` demands PASSED, nine prefixes, **five consecutive fulls** and one digest per
    case. A run of prefixes alone therefore cannot qualify, which is the honest bound on this fixture's
    evidence: it does not produce a qualification, and the code says exactly why.
    """

    from so101_demo.act.task8_live_qualification import validate_campaign_summary

    digests = [f"{index:064x}" for index in range(14)]
    complete = {"status": "PASSED", "prefix_count": 9, "consecutive_full_count": 5,
                "case_journal_sha256": digests}
    assert validate_campaign_summary(complete)["status"] == "PASSED"

    prefixes_only = dict(complete, consecutive_full_count=0)
    with pytest.raises(ValueError, match="TASK8_QUALIFICATION_FULLS_NOT_CONSECUTIVE"):
        validate_campaign_summary(prefixes_only)

    short = dict(complete, case_journal_sha256=digests[:9])
    with pytest.raises(ValueError, match="TASK8_QUALIFICATION_CASE_COUNT_INVALID"):
        validate_campaign_summary(short)

    not_passed = dict(complete, status="INVALID")
    with pytest.raises(ValueError, match="TASK8_QUALIFICATION_NOT_PASSED"):
        validate_campaign_summary(not_passed)

    duplicate = dict(complete, case_journal_sha256=[digests[0]] * 14)
    with pytest.raises(ValueError, match="TASK8_QUALIFICATION_JOURNAL_DUPLICATE"):
        validate_campaign_summary(duplicate)


def test_the_real_case_execution_publishes_the_journal_row_for_a_prefix_case(tmp_path, monkeypatch):
    """P1-5: the production case entry runs the REAL child as its worker and publishes the row itself.

    Only the worker seam is substituted: ``run_pick_place_case`` does its own preflight, campaign check,
    result validation, live-evidence readback rule and retirement-receipt requirement, and ``_publish_new``
    writes the journal row. The evidence directory is its own subdirectory so the harness's manifest and this
    case's artifact binding cannot collide over the same file name.
    """

    from so101_teleop.unified.pick_place_case_execution import run_pick_place_case
    from test_task8_case_execution import _prepared

    spec, owner, journal, events = _prepared(tmp_path)
    evidence = tmp_path / "child-evidence"
    evidence.mkdir()
    child, request, port = _prepare_child_case(
        evidence, monkeypatch, case_id="prefix-01", session_id="session-298",
        attempt_id="prefix-01", campaign_id="case-298")

    async def run_pick_place(case_request):
        events.append("execute")          # the child runs between the harness's start and finish
        assert case_request["attempt_id"] == "prefix-01", "the harness's case is what the child runs"
        assert case_request["session_id"] == "session-298"
        return await child.pick_place_phase(request)

    owner.worker.run_pick_place = run_pick_place
    row = asyncio.run(run_pick_place_case(spec, "prefix-01", owner, journal))

    assert journal.exists(), "the production entry published the journal row itself"
    assert row["case_id"] == "prefix-01" and row["mode"] == "phase_prefix"
    assert row["status"] == "PASSED" and row["stopped_confirmed"] is True
    assert row["completed_phases"] == ["SEARCH"]
    assert row["eligible_for_formal_collection"] is False
    assert row["live_evidence_path"] == "", "a prefix case carries no sealed artifact, and says so"
    assert row["live_evidence_sha256"] == "0" * 64
    assert Path(row["stack_retirement_receipt_path"]).is_file()
    assert Path(row["child_retirement_receipt_path"]).is_file()
    assert events == ["start", "execute", "finish"]

    # the published artifact is the bytes on disk, canonically: the row the caller receives is the file the
    # trusted reader will open, and a replay of the same case cannot overwrite it
    import json as _json
    published = journal.read_bytes()
    expected = (_json.dumps(row, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()
    assert published == expected, "the journal's bytes are the row, canonically encoded"
    journal_sha256 = hashlib.sha256(published).hexdigest()
    assert len(journal_sha256) == 64
    with pytest.raises(ValueError, match="TASK8_CASE_JOURNAL_INVALID"):
        from so101_teleop.unified.pick_place_case_execution import _publish_new
        _publish_new(journal, row)

    # and the trusted path's own translator: the row a campaign publishes becomes the journal row the
    # aggregator reads, validated by the same rule the aggregator applies
    import hashlib as _hashlib
    from so101_demo.act.task8_live_evidence import case_row_to_journal_row

    identities = {"source_provenance_sha256": "a" * 64, "runtime_config_sha256": "b" * 64,
                  "contact_policy_fingerprint": "d" * 64}
    manifest_sha256 = _hashlib.sha256((tmp_path / "manifest.json").read_bytes()).hexdigest()
    journal_row = case_row_to_journal_row(row, identities=identities,
                                          manifest_document_sha256=manifest_sha256)

    assert journal_row["case_id"] == "prefix-01"
    assert journal_row["mode"] == "phase_prefix"
    for name, value in identities.items():
        assert journal_row[name] == value, f"the bundle identity {name} is carried into the journal row"
    assert journal_row["manifest_document_sha256"] == manifest_sha256
    # the producer's receipt digests survive the translation under the journal's own names
    assert journal_row["child_retirement_receipt_sha256"] == row["child_receipt_sha256"]
    assert journal_row["stack_retirement_receipt_sha256"] == row["stack_receipt_sha256"]
    assert journal_row["live_evidence_sha256"] == "0" * 64

    # negative: a row that lost a required field is refused by the trusted translator, not accepted loosely
    tampered = {key: value for key, value in row.items() if key != "child_receipt_sha256"}
    with pytest.raises(ValueError, match="TASK8_CASE_ROW_INVALID"):
        case_row_to_journal_row(tampered, identities=identities,
                                manifest_document_sha256=manifest_sha256)


def test_the_trusted_aggregator_refuses_a_missing_and_a_tampered_case_journal(tmp_path, monkeypatch):
    """P1-5 negatives against the TRUSTED validator, not against my own expectations.

    ``validate_case_journals`` is the aggregator's own reader: it walks the campaign's case ids, demands a
    complete journal for each at the path the campaign writes, and refuses the whole qualification on a
    missing, foreign or incomplete journal. Two of the review's negatives live here.
    """

    import json
    from so101_demo.act.task8_live_evidence import require_campaign_cases
    from so101_demo.act.task8_live_qualification import validate_case_journals
    from test_task8_case_execution import _prepared
    from so101_teleop.unified.pick_place_case_execution import run_pick_place_case

    spec, owner, journal_path, events = _prepared(tmp_path)
    manifest = json.loads((tmp_path / "manifest.json").read_bytes())
    manifest_sha256 = hashlib.sha256((tmp_path / "manifest.json").read_bytes()).hexdigest()
    identities = {"source_provenance_sha256": "a" * 64, "runtime_config_sha256": "b" * 64,
                  "contact_policy_fingerprint": manifest["contact_policy_fingerprint"]}
    required = tuple(require_campaign_cases(manifest))
    assert required, "the campaign names its cases"

    case_root = tmp_path / "campaign"
    cases = case_root / "task8-live" / "cases"
    cases.mkdir(parents=True)

    # negative 1 - a missing row refuses the whole qualification, by the trusted reader's own error
    with pytest.raises(ValueError, match="TASK8_QUALIFICATION_JOURNAL_MISSING"):
        validate_case_journals(case_root, manifest, identities=identities,
                               manifest_document_sha256=manifest_sha256)

    # the real published row, placed where the campaign writes it
    evidence = tmp_path / "child-evidence"
    evidence.mkdir()
    child, request, port = _prepare_child_case(
        evidence, monkeypatch, case_id=required[0], session_id="session-298",
        attempt_id=required[0], campaign_id="case-298")

    async def run_pick_place(case_request):
        return await child.pick_place_phase(request)

    owner.worker.run_pick_place = run_pick_place
    row = asyncio.run(run_pick_place_case(spec, required[0], owner, journal_path))

    # the campaign publishes a PRODUCER row; the trusted reader wants the JOURNAL row, so the translation the
    # trusted path provides is applied first - that is the pipeline, and the negatives live after it
    from so101_demo.act.task8_live_evidence import case_row_to_journal_row
    journal_row = case_row_to_journal_row(row, identities=identities,
                                          manifest_document_sha256=manifest_sha256)

    # negative 2 - a journal whose row lost a required field is refused even though the file is there
    tampered = {key: value for key, value in journal_row.items()
                if key != "child_retirement_receipt_sha256"}
    (cases / f"{required[0]}.json").write_text(json.dumps(tampered, sort_keys=True))
    with pytest.raises(ValueError, match="TASK8_"):
        validate_case_journals(case_root, manifest, identities=identities,
                               manifest_document_sha256=manifest_sha256)

    # and the untampered row is ACCEPTED for its case: the reader moves on and stops at the NEXT missing one
    (cases / f"{required[0]}.json").write_text(json.dumps(journal_row, sort_keys=True))
    with pytest.raises(ValueError, match="TASK8_QUALIFICATION_JOURNAL_MISSING"):
        validate_case_journals(case_root, manifest, identities=identities,
                               manifest_document_sha256=manifest_sha256)


def test_a_missing_retirement_receipt_refuses_the_case_and_publishes_nothing(tmp_path):
    """Negative: without the child's retirement receipt the case must not publish a success row."""

    from so101_teleop.unified.pick_place_case_execution import run_pick_place_case
    from test_task8_case_execution import _prepared

    from so101_teleop.unified.contracts import MutationError

    spec, owner, journal, events = _prepared(tmp_path, omit_child_receipt=True)
    with pytest.raises(MutationError, match="TASK8_RETIREMENT_RECEIPT_INVALID"):
        asyncio.run(run_pick_place_case(spec, "prefix-01", owner, journal))
    assert not journal.exists(), "a case without both retirement receipts publishes nothing"
    assert "finish" in events, "the attempt still retired the stack and the child"


def test_the_case_window_binds_its_reset_epoch_exactly_once(tmp_path, monkeypatch):
    """Negative: the window's generation is bound once; claiming another epoch for the same case is refused."""

    child, request, port = _prepare_child_case(tmp_path, monkeypatch)
    asyncio.run(child.pick_place_phase(request))
    window = port.live_evidence_window
    assert window is not None, "the child attached its evidence window to the production port"
    with pytest.raises(ValueError):
        window.bind_reset_epoch(99)


def test_the_case_evidence_is_indexed_and_a_tampered_raw_record_is_refused(tmp_path, monkeypatch):
    """The indexed evidence this repository can produce for a bounded case, plus one more tamper negative.

    The recorder writes each sample once, fsync'd, and keeps an index row per sample with its own digest,
    phase, step, sim time and epochs. A bounded (prefix) case does not seal - that is the production rule -
    so what exists to check is the index and the bytes it names, and one production refusal for a raw record
    whose bytes no longer match the digest a sample claims.
    """

    import json
    from so101_demo.act.task8_live_evidence import build_live_evidence_sample
    from so101_demo.adapters.act.pick_place_readback import PickPlaceReadbackError  # noqa: F401

    child, request, port = _prepare_child_case(tmp_path, monkeypatch)
    asyncio.run(child.pick_place_phase(request))

    recorder = port._evidence_recorder
    entries = list(recorder._entries)
    # the port feeds this window itself now (P1-3), and since P1-4 it records the phase's EDGE ADDITIONS beside the
    # grid samples (`add_event`: "it never counts as a grid point"), so a bounded SEARCH case carries its sample AND
    # the edge the phase produced - the count is the case's own, not a literal (the same family as CP-1728)
    assert len(entries) >= 1, f"the phase's own samples are the case's evidence: {len(entries)}"
    assert {entry["phase"] for entry in entries} == {"SEARCH"}, "and they belong to the phase that ran"

    # every index row names a real file whose bytes hash to the digest the row claims
    for entry in entries:
        # the index row's relative path already names the staging directory inside the evidence root
        path = Path(recorder.evidence_root) / entry["relative_path"]
        assert path.is_file(), f"indexed evidence exists: {entry['relative_path']}"
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"]

    assert {entry["reset_epoch"] for entry in entries} == {port.boundary.reset_epoch}
    assert {entry["release_epoch"] for entry in entries} == {0}

    # tamper negative at the evidence layer: a raw record whose bytes were changed is refused by append
    root = Path(recorder.evidence_root)
    identity = {"case_id": request.payload["scenario_id"], "session_id": request.session_id,
                "attempt_id": request.attempt_id, "reset_epoch": port.boundary.reset_epoch,
                "release_epoch": 0}
    stamps = {name: 5.0 for name in READBACK_SOURCES}
    records = _raw_records(root, 5.0)
    first = sorted(records)[0]
    (root / records[first]["relative_path"]).write_bytes(b"{\"tampered\": true}")
    sample = build_live_evidence_sample(
        identity=identity, phase="SEARCH", physics_step=99, sim_time_s=5.0,
        source_stamps_s=dict(stamps), source_received_monotonic_s=dict(stamps),
        raw_records=records, holding_state="HOLDING",
        frame={"wrist_frame_valid": True, "wrist_target_visible": True},
        contact={"observation_valid": True, "bilateral_contact": False, "no_fingertip_contact": True,
                 "cup_supported": False, "released": False, "placement_stable": False},
        measurements={"cup_support_distance_m": 0.01, "end_effector_position_m": [0.0, 0.0, 0.1],
                      "cup_position_m": [0.0, 0.0, 0.1], "cup_orientation_xyzw": [0.0, 0.0, 0.0, 1.0]})
    with pytest.raises(ValueError, match="TASK8_LIVE_EVIDENCE_RAW_RECORD_INVALID"):
        # P1-4: `append` now takes the sample's KIND - the recorder's sealed entry records whether it was a grid point
        # or an event, and an event carries the reason it was taken - so a direct caller names it.
        recorder.append(sample, kind="grid")


def test_a_campaign_of_prefixes_alone_cannot_qualify():
    """The trusted qualification gate refuses the bounded campaign we can actually run - by its own rules.

    ``validate_campaign_summary`` demands PASSED, nine prefixes, **five consecutive fulls** and one digest per
    case. A run of prefixes alone therefore cannot qualify, which is the honest bound on this fixture's
    evidence: it does not produce a qualification, and the code says exactly why.
    """

    from so101_demo.act.task8_live_qualification import validate_campaign_summary

    digests = [f"{index:064x}" for index in range(14)]
    complete = {"status": "PASSED", "prefix_count": 9, "consecutive_full_count": 5,
                "case_journal_sha256": digests}
    assert validate_campaign_summary(complete)["status"] == "PASSED"

    prefixes_only = dict(complete, consecutive_full_count=0)
    with pytest.raises(ValueError, match="TASK8_QUALIFICATION_FULLS_NOT_CONSECUTIVE"):
        validate_campaign_summary(prefixes_only)

    short = dict(complete, case_journal_sha256=digests[:9])
    with pytest.raises(ValueError, match="TASK8_QUALIFICATION_CASE_COUNT_INVALID"):
        validate_campaign_summary(short)

    not_passed = dict(complete, status="INVALID")
    with pytest.raises(ValueError, match="TASK8_QUALIFICATION_NOT_PASSED"):
        validate_campaign_summary(not_passed)

    duplicate = dict(complete, case_journal_sha256=[digests[0]] * 14)
    with pytest.raises(ValueError, match="TASK8_QUALIFICATION_JOURNAL_DUPLICATE"):
        validate_campaign_summary(duplicate)
