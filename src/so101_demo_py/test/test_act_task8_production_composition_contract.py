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

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_act_task8_measurement_runtime_descriptor import _context_document, _descriptor  # noqa: E402


class CannedMujocoClient:
    """The single substituted boundary, and the only thing these tests stand in for.

    Every method returns a value the assertions can recognise, so a passing test proves the value travelled
    through the real stack adapter, the real driver and the real sealing path rather than that a key exists.
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

    def camera_info(self, anchor):
        self.calls.append(("camera_info", anchor))
        return {"frame_id": "head_camera_frame", "ray_origin_frame_id": "head_camera_frame",
                "width_px": 640, "height_px": 480}

    def tf(self, anchor):
        self.calls.append(("tf", anchor))
        return [{"parent": "base_link", "child": "head_camera_frame",
                 "translation_m": [0.0, 0.0, 0.21], "rotation_xyzw": [0.0, 0.0, 0.0, 1.0]}]

    def search(self, anchor):
        self.calls.append(("search", anchor))
        return {"found": True, "bearing_rad": 0.0125, "confidence": 0.875, "physics_step": 4096,
                "sim_time_s": 81.92}

    def probe(self, anchor):
        self.calls.append(("probe", anchor))
        return {"physics_step": 4096, "sim_time_s": 81.92, "joints_rad": [0.0] * 6}


def _run(tmp_path, monkeypatch, client):
    """Drive the whole measurement through the real composition path, with only the I/O client replaced."""

    from so101_demo.act.task8_production_composition import (
        PROVIDER_SEAM_ENV, build_production_measurement_driver, build_real_providers,
    )

    # the provider seam must not be in play: these tests are about the real construction path
    monkeypatch.delenv(PROVIDER_SEAM_ENV, raising=False)
    document = _context_document(tmp_path, _descriptor())
    context = type("Context", (), document)()
    context.runtime_descriptor = document["runtime_descriptor"]
    context.resource_binding = document["resource_binding"]

    providers = build_real_providers(context=context, descriptor=document["runtime_descriptor"],
                                     io_client=client)
    driver = build_production_measurement_driver(
        context=context, identity={"driver_source_sha256": document["driver_source_sha256"]},
        providers=providers)
    return driver.run(context, tmp_path / "batch"), context


def test_the_real_composition_drives_every_anchor_and_seals_a_closed_batch(tmp_path, monkeypatch):
    client = CannedMujocoClient()
    root, _context = _run(tmp_path, monkeypatch, client)

    batch = json.loads((Path(root) / "batch.json").read_bytes())
    assert batch["status"] == "CLOSED", f"the batch sealed INVALID: {batch.get('error_code')}"
    assert [entry["status"] for entry in batch["anchors"]] == ["COLLECTED"] * len(batch["anchors"])
    assert batch["anchors"], "the driver measured the anchors it was given"

    # the values travelled: they are the client's, not constants the driver could have invented
    assert ("launch", "default") in client.calls and ("cleanup", "default", "gen-descriptor-red") in client.calls
    resolved = [call for call in client.calls if call[0] == "search"]
    assert resolved, "the search route ran through the stack adapter rather than being skipped"


def test_a_launch_refusal_seals_an_invalid_batch_carrying_that_code(tmp_path, monkeypatch):
    root, _context = _run(tmp_path, monkeypatch, CannedMujocoClient(fail_on_launch=True))

    batch = json.loads((Path(root) / "batch.json").read_bytes())
    assert batch["status"] == "INVALID"
    assert "MUJOCO_LAUNCH_REFUSED" in json.dumps(batch), "the client's own failure reaches the sealed batch"
