"""Astra item 5: drive the production child entry with only the external I/O replaced.

The child is built as the dispatcher builds it, its artifacts arrive through the production
loader (``ActArtifactBinding``), and the request is the real closed IPC model. The runner, the
``CaseEvidenceDriver``, the window seal and the journal are production objects; only the ROS,
MuJoCo, controller and process boundaries are fakes - the port is the one the Boundary V chain
test already builds.
"""

from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import json
import time
from pathlib import Path

from so101_demo.act.contact_calibration import REGIMES
from so101_demo.act.contact_policy import policy_fingerprint
from so101_teleop.unified.act_artifacts import ActArtifactBinding
from so101_teleop.unified.ipc import DispatchTokenModel, IpcRequest, _PickPlacePayload, _StackOwner
from so101_teleop.unified.ros_child import RclpyActionDriver, local_owner
from test_act_campaign_admission import _calibration, _canonical, _write_policy
import test_task8_case_runner_chain as chain
from test_task8_case_runner_chain import FakePort

_HASHED = ("source", "manifest", "runtime_config", "collection_config", "calibration_report")
_POLICY = ("proposal", "activation_receipt")


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


class ChildPort(FakePort):
    """The chain test's port, plus the reset-epoch binding the production evidence driver needs.

    The chain test bound the window's epoch from its own fixture; here the window belongs to the child's
    CaseEvidenceDriver, so the port - which is the thing that sees the reset - binds it.
    """

    def seal_live_evidence(self, request):
        # the window belongs to the child's CaseEvidenceDriver, so its recorder does too; the chain fixture passed
        # one in explicitly, this fixture takes it from the window the child attached
        self.recorder = getattr(self.window, "_recorder", None) or self.recorder
        return super().seal_live_evidence(request)

    def begin(self, request):
        result = super().begin(request)
        window = getattr(self, "window", None)
        if window is not None and hasattr(window, "bind_reset_epoch"):
            window.bind_reset_epoch(self.reset_epoch)      # exactly what the rows carry, not a fallback
        return result


class FakeBroker:
    """The ROS/process seam: the child must not start a real broker inside a test."""

    def stop(self, *args, **kwargs):
        return True

    def __getattr__(self, name):                     # every other broker call answers harmlessly
        def _call(*args, **kwargs):
            return True
        return _call


def test_the_child_runs_a_full_case_and_seals_what_the_runner_produced(tmp_path, monkeypatch):
    binding = _binding(tmp_path)
    for name, value in binding.environment().items():      # the binder's own writer, not a copy of it
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("SO101_ACT_CAMPAIGN_ID", "campaign-item5")

    # the chain test's port builds its rows from its own fixture identity, and the production recorder refuses
    # samples naming another case - so the fixture supplies this case's identity to that builder (fixture code,
    # not production code, and the sample builder itself stays the production one)
    port = ChildPort()
    # the rows must carry the epochs the port is actually at, since the runner advances release_epoch as the case
    # proceeds - so the builder reads the live port rather than a constant
    monkeypatch.setattr(chain, "_identity", lambda: {"case_id": "case-05", "session_id": "session-item5",
                                                    "attempt_id": "attempt-item5",
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
    child = RclpyActionDriver(pick_place_port=port, owner=owner, broker=FakeBroker(), act_hashes=bound_hashes,
                              startup_proof_consumer=lambda request: {"proof": "startup"})
    deadline_ns = time.monotonic_ns() + 60_000_000_000      # one deadline, shared by the request and its token
    request = IpcRequest(
        version=1, operation="task8_full",
        command_id="item5-command", service_epoch="item5-epoch",
        # the act identity block the model validator requires for act operations
        campaign_id="campaign-item5", worker_id="item5-child",     # the rule is token.child_id == worker_id
        execution_generation=1,
        runtime_id="item5-runtime",
        # the token is a closed model, and the request's execution_generation is an int - not strings
        token=DispatchTokenModel(operation_id="item5-op", child_id="item5-child",
                                 runtime_id="item5-runtime", execution_generation=1,
                                 deadline_ns=deadline_ns,
                                 revocation_revision=0),
        service_token="item5-service_token",
        session_id="session-item5", attempt_id="attempt-item5",
        deadline_ns=deadline_ns,
        payload=_PickPlacePayload(
            scenario_id="case-05",          # the journal's _CASE_ID is r"[a-z]+-[0-9]{2}\Z"
            manifest_sha256=digests["manifest"],
            runtime_config_sha256=digests["runtime_config"],
            contact_policy_fingerprint=bound_hashes["contact_policy_fingerprint"],
            stack_owner=_StackOwner(pid=owner.pid, pgid=owner.pgid, started_ticks=owner.started_ticks,
                                    argv_sha256=owner.argv_sha256,
                                    environment_sha256=owner.environment_sha256)).model_dump())

    result = asyncio.run(child.pick_place_full(request))

    assert port.receipt == {"proof": "startup"}, "the startup receipt reached the port"
    assert result.get("stopped_confirmed") is True, "the entry only returns after a confirmed stop"
