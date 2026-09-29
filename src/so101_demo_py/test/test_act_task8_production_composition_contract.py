"""P1-1: the production composition must DRIVE a real measurement, not merely construct providers.

The review's finding is that `task8_production_composition.py` returns a controller of `None`, a clock that is
not a clock, and a `PersistentTaskStack` that implements none of the protocol the measurement driver calls - so
the composition cannot run a measurement at all. These are contract tests, so they fail while that is true.

What is substituted here is ONLY the lowest-level external I/O (the MuJoCo/ROS client the adapters talk to),
and it is substituted through the composition's own seam - one `io_client` argument. Everything above it - the
stack adapter, clock, detector, controller and phase-camera - is the production construction path, reached by
calling `build_production_measurement_driver` WITHOUT injected providers and without the provider-seam env.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_act_task8_measurement_runtime_descriptor import _context_document, _descriptor  # noqa: E402


def _phase_path(phase):
    """The phase's joint path at the admitted cadence; the neck joint pans this camera."""

    joints = [0.0] * 7
    joints[6] = {"SEARCH": 0.0, "APPROACH": 0.1}.get(phase, 0.2)
    return {"samples": [{"t_s": index * 0.002, "joints_rad": list(joints)} for index in range(11)]}


def _target():
    return {"class_id": "plastic_cup", "position_m": [0.10, 0.10, 0.02], "radius_m": 0.03}


def _occluders():
    return {"fixed_fingertip_00": {"position_m": [0.02, 0.0, 0.10], "radius_m": 0.005}}


class CannedMujocoClient:
    """The single substituted boundary, and the only thing these tests stand in for.

    Its surface is exactly what the production stack adapter delegates to, and every method returns a value the
    assertions can recognise - so a passing test proves the value travelled through the real adapter, the real driver
    and the real sealing path rather than that a key exists somewhere.
    """

    def __init__(self, *, fail_on_launch: bool = False) -> None:
        self.calls: list[tuple] = []
        self.fail_on_launch = fail_on_launch

    def launch(self, anchor):
        self.calls.append(("launch", anchor))
        if self.fail_on_launch:
            raise RuntimeError("MUJOCO_LAUNCH_REFUSED")
        return {"session_id": f"session-{anchor}", "reset_epoch": 7, "attempt_id": f"attempt-{anchor}"}

    def close(self, anchor):
        self.calls.append(("close", anchor))
        return True

    def cleanup(self, anchor, generation):
        self.calls.append(("cleanup", anchor, generation))
        return {"status": "CONFIRMED", "generation": generation}

    def readback(self, anchor):
        # the driver reads the anchor's real identity here, so the values are the client's own
        self.calls.append(("readback", anchor))
        return {"session_id": f"session-{anchor}", "reset_epoch": 7, "attempt_id": f"attempt-{anchor}"}

    def run_search(self, anchor, request):
        self.calls.append(("run_search", anchor))
        return {"found": True, "bearing_rad": 0.0125, "confidence": 0.875,
                "iterations": [{"index": 0, "bearing_rad": 0.0125, "confidence": 0.875, "physics_step": 4096}]}

    def camera_info(self, anchor):
        self.calls.append(("camera_info", anchor))
        return {"frame_id": "head_camera_frame", "ray_origin_frame_id": "head_camera_frame",
                "width_px": 640, "height_px": 480}

    def tf(self, anchor):
        self.calls.append(("tf", anchor))
        return {"base_link->head_camera_frame": {"translation_m": [0.0, 0.0, 0.21],
                                                "rotation_xyzw": [0.0, 0.0, 0.0, 1.0]}}

    def probe(self, anchor, command):
        self.calls.append(("probe", anchor))
        return {"contacts": [], "physics_step": 4096, "command": dict(command)}

    def frame(self, anchor):
        # the controller adapter asks for the anchor's current frame and neck feedback; the values are the client's,
        # and their sim times are coherent so the state machine sees fresh, mutually consistent input
        self.calls.append(("frame", anchor))
        return {"frame_id": "head_camera_frame", "sim_time_s": 81.92, "detections": []}

    def neck_feedback(self, anchor):
        self.calls.append(("neck_feedback", anchor))
        return {"neck_yaw_rad": 0.0, "neck_velocity_rad_s": 0.0, "sim_time_s": 81.92, "safe_observe": True}

    def command(self, anchor, command):
        self.calls.append(("command", anchor, command.get("status")))
        return {"accepted": True, "command": dict(command)}


def _run(tmp_path, monkeypatch, client):
    """Drive the whole measurement through the real composition path, with only the I/O client replaced."""

    from so101_demo.act.task8_production_composition import (
        PROVIDER_SEAM_ENV, build_production_measurement_driver, build_real_providers,
    )

    # the provider seam must not be in play: these tests are about the real construction path
    monkeypatch.delenv(PROVIDER_SEAM_ENV, raising=False)
    # the calibration is the repo's own fixture pair (runtime descriptor + admitted report), reused rather than
    # re-invented, so this test cannot pass with a pairing the production binding would refuse
    from test_act_head_search_binding import _inputs

    runtime, calibration, _weights, _sample = _inputs(tmp_path)
    document = _context_document(tmp_path, runtime)
    # the production type requires the twelve the CLI passes; the duck-typed version needed none of them, which is
    # another way the old test was weaker than it looked
    document.setdefault("contract_sha256", "f" * 64)
    document["calibration_report"] = calibration
    document["session_id"] = "session-default"
    document["attempt_id"] = "attempt-default"
    document["search_start_rad"] = 0.0
    # the PRODUCTION context type, not a duck-typed namespace: the previous version satisfied `getattr` reads with a
    # throwaway class, so it never exercised the type the CLI constructs - which is how item 1's four missing fields
    # survived a green contract test (CP-1633). A test that proves the formal path must use the formal object.
    from so101_demo.act.task8_calibration_admission import CalibrationMeasurementContext

    context = CalibrationMeasurementContext(**document)

    class CannedDetector:
        """The substituted model, in the shape the production builder validates and the driver calls."""

        cold_start_latency_ms = 12.5

        def __call__(self, context):
            return {"detections": [], "backend": "canned",
                    "anchor": context.get("anchor"), "sample": context.get("sample")}

    def canned_detector_factory(**_kwargs):
        # the production builder calls the factory with the validated artifact arguments, so the test accepts
        # them rather than pretending the weights file is a real network
        return CannedDetector()

    # the per-run values are ARGUMENTS: this test stands in for the driver, so it supplies them the way the driver
    # does - a composition without them refuses by name (CP-1635)
    # P1-3: the phase camera measures, so this test supplies the geometry a measurement has - the phase path, the
    # target and the occluders - through the same bottom-I/O layer the client and the model factory come from
    providers = build_real_providers(context=context, descriptor=document["runtime_descriptor"],
                                     io_client=client, yolo_detector_factory=canned_detector_factory,
                                     session_id=document["session_id"], attempt_id=document["attempt_id"],
                                     search_start_rad=document["search_start_rad"],
                                     phase_path=_phase_path, target=_target, occluder_geometry=_occluders)
    # the driver requires the schema's ten-member identity document, so the test supplies one rather than a
    # single convenient hash (the same document the batch seal and the aggregator share)
    from so101_demo.act.task8_measurement_schema import MeasurementIdentity

    identity = {"source_commit": "a" * 40,
                **{name: hashlib.sha256(name.encode()).hexdigest() for name in MeasurementIdentity.MEMBERS
                   if name != "source_commit"}}
    # the per-run values are ARGUMENTS now (CP-1635): the driver supplies them, and a composition that is not
    # given them refuses by name rather than defaulting
    driver = build_production_measurement_driver(
        context=context, identity=identity, providers=providers, session_id=document["session_id"],
        attempt_id=document["attempt_id"], search_start_rad=document["search_start_rad"])
    return driver.run(context, tmp_path / "batch"), context


def test_the_real_composition_drives_every_anchor_and_seals_a_closed_batch(tmp_path, monkeypatch):
    client = CannedMujocoClient()
    root, _context = _run(tmp_path, monkeypatch, client)

    # the sealer returns the document it published, so it is read directly rather than treated as a directory
    batch_path = Path(root)
    assert batch_path.is_file(), "the driver returned the sealed document it published"
    batch = json.loads(batch_path.read_bytes())
    assert batch["status"] == "CLOSED", f"the batch sealed INVALID: {batch.get('error_code')}"
    assert batch["anchors"] == ["default", "left", "forward"], "every configured anchor was measured"
    assert batch["cleanup"]["status"] == "CONFIRMED", "the run cleaned up its own generation"
    assert batch["contamination"] is None

    # the batch indexes every artefact it wrote, WITH digests: this is what makes the seal evidence rather than a
    # summary, so the test re-hashes the files the index names instead of trusting the list
    files = batch["files"]
    assert files, "the sealed batch indexes the rows it acquired"
    for relative, digest in files.items():
        written = batch_path.parent / relative
        assert written.is_file(), f"indexed artefact exists: {relative}"
        assert hashlib.sha256(written.read_bytes()).hexdigest() == digest, f"digest matches for {relative}"
    assert any(name.endswith("search.json") for name in files), "the live search's raw rows are in the index"

    # the values travelled: they are the client's, not constants the driver could have invented
    assert ("launch", "default") in client.calls, "the stack adapter launched through the client"
    assert ("readback", "default") in client.calls, "the anchor's identity came from the client's readback"
    assert ("run_search", "default") in client.calls, "the live search ran through the client"
    assert ("probe", "default") in client.calls, "the fixed probe ran through the client"
    commands = [call for call in client.calls if call[0] == "command"]
    assert len(commands) == 30, f"one command per recorded sample per anchor: {len(commands)}"
    assert all(isinstance(call[2], str) and call[2] for call in commands), \
        "each command carries the state machine's own status rather than an invented one"
    assert {call[1] for call in commands} == {"default", "left", "forward"}
    # the driver cleans up ONCE, for the last anchor of the case, naming the context's own generation
    assert ("cleanup", "forward", "gen-descriptor-red") in client.calls, "cleanup named this context's generation"
    assert len([call for call in client.calls if call[0] == "cleanup"]) == 1, "cleanup ran exactly once"
    # the client's own identity values are in the sealed rows, so the batch measured THIS client
    rows = sorted(batch_path.parent.glob("**/*.json"))
    assert rows, "the batch carries the per-anchor rows it acquired"
    assert "session-default" in " ".join(row.read_text() for row in rows), \
        "the client's own identity values reached the recorded rows"


def test_a_launch_refusal_seals_an_invalid_batch_carrying_that_code(tmp_path, monkeypatch):
    root, _context = _run(tmp_path, monkeypatch, CannedMujocoClient(fail_on_launch=True))

    batch = json.loads(Path(root).read_bytes())
    assert batch["status"] == "INVALID"
    assert "MUJOCO_LAUNCH_REFUSED" in json.dumps(batch), "the client's own failure reaches the sealed batch"
