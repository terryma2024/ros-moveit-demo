"""Bind one already selected world/scene/contact frame to its measured physics step.

This read-only source join does not establish stationary history or grant a goal.
"""

from __future__ import annotations

import copy
import math
import time

from so101_demo.act.contracts import sha256
from so101_demo.core.simulation.types import SimulationEvidence

from .contact_evidence import FRAME_KEYS, RobotContactObserver, contact_hazard
from .physics_clock_history import PhysicsClockHistory
from .scene_state import SCENE_KEYS, SceneStateObserver


_READBACK_KEYS = frozenset((
    "world", "scene", "contact", "observation", "reference",
    "source_stamps_s", "source_received_wall_s"))
_RECEIPT_KEYS = frozenset((
    "world", "scene", "contact", "head", "wrist", "arm", "neck"))


def _simulation_ns(value):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or value < 0):
        raise ValueError("simulation time invalid")
    return round(value * 1_000_000_000)


def _receipt_ns(value, now_ns, max_age_ns):
    receipt_ns = _simulation_ns(value)
    if not 0 <= now_ns - receipt_ns <= max_age_ns:
        raise ValueError("receipt stale or future")
    return receipt_ns


def _selected_record(observer, *, step_key, expected, receipt, now_ns, max_age_ns):
    records = observer.recent_frames_with_receipts()
    if (not records or
            (records[-1][0]["simulation_session_id"], records[-1][0]["reset_epoch"])
            != (expected["simulation_session_id"], expected["reset_epoch"])):
        raise ValueError("observer epoch changed")
    selected = [(frame, accepted) for frame, accepted in records
                if (frame["simulation_session_id"], frame["reset_epoch"],
                    frame[step_key]) ==
                (expected["simulation_session_id"], expected["reset_epoch"],
                 expected[step_key])]
    if len(selected) != 1 or selected[0][0] != expected:
        raise ValueError("selected record missing, changed or duplicated")
    if _receipt_ns(selected[0][1], now_ns, max_age_ns) != _receipt_ns(
            receipt, now_ns, max_age_ns):
        raise ValueError("selected receipt changed")


def join_selected_physics_sample(
    readback, physics_history, scene_observer, contact_observer, *,
    expected_model_sha256, max_source_age_ns, clock_ns=time.monotonic_ns,
):
    """Freeze the selected step and its original source/receipt clocks, without authority."""
    try:
        sha256(expected_model_sha256)
        if (type(max_source_age_ns) is not int or max_source_age_ns < 1
                or not callable(clock_ns)
                or type(readback) is not dict or set(readback) != _READBACK_KEYS
                or not isinstance(physics_history, PhysicsClockHistory)
                or not isinstance(scene_observer, SceneStateObserver)
                or not isinstance(contact_observer, RobotContactObserver)):
            raise ValueError("join configuration invalid")
        now_ns = clock_ns()
        if type(now_ns) is not int or now_ns < 1:
            raise ValueError("join clock invalid")

        world, scene, contact = (
            readback["world"], readback["scene"], readback["contact"])
        receipts = readback["source_received_wall_s"]
        if (not isinstance(world, SimulationEvidence)
                or type(scene) is not dict or set(scene) != SCENE_KEYS
                or type(contact) is not dict or set(contact) != FRAME_KEYS
                or type(receipts) is not dict or set(receipts) != _RECEIPT_KEYS
                or world.paused is not False or world.truncated is not False
                or world.simulation_step < 1 or world.reset_epoch < 1
                or scene["paused"] is not False
                or contact["truncated"] is not False
                or contact["evidence_loss"] is not False):
            raise ValueError("selected readback invalid")
        for value in receipts.values():
            _receipt_ns(value, now_ns, max_source_age_ns)

        scope = (world.simulation_session_id, world.reset_epoch,
                 world.simulation_step)
        if ((scene["simulation_session_id"], scene["reset_epoch"],
             scene["simulation_step"]) != scope
                or (contact["simulation_session_id"], contact["reset_epoch"],
                    contact["physics_step"]) != scope
                or physics_history.session_id != scope[0]
                or physics_history.epoch != scope[1]
                or scene_observer.model_sha256 != expected_model_sha256
                or scene["model_sha256"] != expected_model_sha256
                or scene_observer.nq != physics_history.nq
                or scene_observer.nv != physics_history.nv
                or contact_hazard(contact, contact_observer.allowed)):
            raise ValueError("selected source scope invalid")
        scene_observer.validate(scene)

        _selected_record(
            scene_observer, step_key="simulation_step", expected=scene,
            receipt=receipts["scene"], now_ns=now_ns,
            max_age_ns=max_source_age_ns)
        _selected_record(
            contact_observer, step_key="physics_step", expected=contact,
            receipt=receipts["contact"], now_ns=now_ns,
            max_age_ns=max_source_age_ns)
        physics = physics_history.step_at(scope[2])
        sample = physics["sample"]
        source_begin = scene["clock_interval_begin_monotonic_ns"]
        source_end = scene["clock_interval_end_monotonic_ns"]
        if (sample.simulation_session_id != scope[0]
                or sample.reset_epoch != scope[1]
                or sample.physics_step != scope[2]
                or _simulation_ns(world.simulation_time_s) !=
                   _simulation_ns(sample.simulation_time_s)
                or _simulation_ns(scene["simulation_time_s"]) !=
                   _simulation_ns(sample.simulation_time_s)
                or _simulation_ns(contact["simulation_time_s"]) !=
                   _simulation_ns(sample.simulation_time_s)
                or tuple(scene["qpos"]) != tuple(sample.model_qpos)
                or tuple(scene["qvel"]) != tuple(sample.model_qvel)
                or type(source_begin) is not int or type(source_end) is not int
                or not 0 < sample.clock_interval_end_monotonic_ns <=
                   source_begin <= source_end <= now_ns
                or now_ns - source_end > max_source_age_ns
                or now_ns - sample.clock_interval_end_monotonic_ns >
                   max_source_age_ns
                or _receipt_ns(receipts["scene"], now_ns, max_source_age_ns)
                   < source_end):
            raise ValueError("selected physics state or source clock invalid")

        return {
            "readback": copy.deepcopy(readback),
            "physics_sample": copy.deepcopy(sample),
            "physics_received_monotonic_ns": physics["received_monotonic_ns"],
            "scene_source_interval_monotonic_ns": (source_begin, source_end),
            "command_authority": False,
        }
    except (AttributeError, KeyError, TypeError, ValueError, OverflowError,
            RuntimeError) as error:
        raise ValueError("SELECTED_PHYSICS_JOIN_INVALID") from error
