"""Freeze the selected physical SEARCH readback before prefix production."""

from dataclasses import asdict
import hashlib
import json

from so101_demo.act.contracts import finite, validate_observation, validate_search_result
from so101_demo.core.simulation.types import SimulationEvidence
from so101_demo.ports.planning_scene import SceneCommandReceipt
from .pick_place_search_segment import PickPlaceSearchObservation


_SOURCE_KEYS = frozenset(("world", "scene", "contact", "head", "wrist", "arm", "neck"))
_FRAME_KEYS = frozenset(("head", "wrist", "arm", "neck"))
_READBACK_KEYS = frozenset(("world", "scene", "contact", "observation",
                            "reference", "source_stamps_s",
                            "source_received_wall_s"))


def freeze_selected_search_source(observed, *, max_skew_s):
    """Return exact original receipts and a versioned hash of the selected data."""
    try:
        skew = finite(max_skew_s)
        if skew <= 0 or not isinstance(observed, PickPlaceSearchObservation):
            raise ValueError("input")
        result = validate_search_result(observed.search_result)
        raw = observed.physical_readback
        if type(raw) is not dict or set(raw) != _READBACK_KEYS:
            raise ValueError("readback")
        world, scene, contact = raw["world"], raw["scene"], raw["contact"]
        selected = validate_observation(raw["observation"])
        receipts = raw["source_received_wall_s"]
        stamps = raw["source_stamps_s"]
        planning = observed.planning_scene
        if (not isinstance(world, SimulationEvidence)
                or type(scene) is not dict or type(contact) is not dict
                or type(receipts) is not dict or set(receipts) != _SOURCE_KEYS
                or type(stamps) is not dict or set(stamps) != _FRAME_KEYS
                or not isinstance(planning, SceneCommandReceipt)
                or planning.backend != "mujoco" or planning.phase != "READ_BACK"
                or planning.success is not True or planning.failure_code is not None
                or planning.evidence.get("mismatches") != []
                or set(planning.evidence.get("world_ids", ())) !=
                   {"table", "pedestal", "plastic_cup"}
                or planning.evidence.get("attached_ids") != []
                or result["found"] is not True
                or result["attempt_id"] != selected["attempt_id"]
                or world.simulation_session_id != selected["session_id"]
                or world.simulation_time_s != selected["sim_time_s"]
                or world.simulation_step < 1 or world.reset_epoch < 1
                or world.paused is not False or world.truncated is not False
                or (scene.get("simulation_session_id"), scene.get("reset_epoch"),
                    scene.get("simulation_step")) != (
                        world.simulation_session_id, world.reset_epoch,
                        world.simulation_step)
                or scene.get("paused") is not False
                or (contact.get("simulation_session_id"), contact.get("reset_epoch"),
                    contact.get("physics_step")) != (
                        world.simulation_session_id, world.reset_epoch,
                        world.simulation_step)
                or contact.get("truncated") is not False
                or contact.get("evidence_loss") is not False
                or abs(finite(scene["simulation_time_s"])
                       - world.simulation_time_s) > skew
                or abs(finite(contact["simulation_time_s"])
                       - world.simulation_time_s) > skew
                or any(not 0 <= world.simulation_time_s
                       - finite(stamp, nonnegative=True) <= skew
                       for stamp in stamps.values())):
            raise ValueError("scope")
        original_receipts = {
            key: finite(receipts[key], nonnegative=True)
            for key in ("world", "scene", "contact", "head", "wrist", "arm", "neck")
        }
        metadata = dict(
            version=1, world=asdict(world), scene=scene, contact=contact,
            observation={key: selected[key] for key in (
                "session_id", "attempt_id", "sim_time_s", "state")},
            reference=raw["reference"], source_stamps_s=stamps,
            source_received_wall_s=original_receipts,
            search_result=result, planning_scene=asdict(planning),
        )
        encoded = json.dumps(metadata, sort_keys=True, separators=(",", ":"),
                             allow_nan=False).encode("utf-8")
        digest = hashlib.sha256()
        digest.update(b"SO101_SELECTED_SEARCH_SOURCE_V1\0")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        for key in ("head", "wrist"):
            pixels = selected[key].tobytes(order="C")
            digest.update(key.encode("ascii"))
            digest.update(len(pixels).to_bytes(8, "big"))
            digest.update(pixels)
        return dict(
            session_id=world.simulation_session_id,
            attempt_id=selected["attempt_id"], reset_epoch=world.reset_epoch,
            phase="SEARCH", physics_step=world.simulation_step,
            simulation_time_s=world.simulation_time_s,
            observation_sha256=digest.hexdigest(),
            source_received_wall_s=original_receipts,
        )
    except (AttributeError, KeyError, TypeError, ValueError, OverflowError) as error:
        raise ValueError("SELECTED_SEARCH_SOURCE_INVALID") from error
