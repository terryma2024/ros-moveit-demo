"""Source-bound held-cup transfer targets for a later physical port.

The explicit 2 ms prefix contract preserves the screened cubic path. Live
bridge, controller, Planning Scene, and camera gates remain separate.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from .execution import bounded_positions


_RAW_SHA = "e196a112210bc07a35bcc2a56ca37dd06166caf64226626f40132c554e6c2bba"
_CONTENT_SHA = "f52b63939c69538a8ce6362538c1aebb910c86a069e2bc7fb15b494b7d1e7700"
_MODEL_SHA = "17c415d9541be3c13ce43d8650a0879b5b2d7f62177cca7601500fd94d3d878e"
_SCENE_SHA = "ea7e18df15dd67e8beddcc35d66eab6fda128145a7877b578fc641d282c114cb"
_POLICY_SHA = "0ba8e07f16e448b16efe7b342745af7181678af47ddf45f975434919774dca11"
_MATRIX_SHA = "2555d1b7a6af11a82cac4b0c676ab82e57c6381a13cf2e7bee8b8a8eabff3ef8"
_ANCHORS = ("default", "left", "forward")
_PHASES = ("TRANSPORT",) * 6 + ("ALIGN",) * 5
_PROFILE_KEYS = frozenset({
    "schema_version", "kind", "eligible_for_collection", "backend",
    "mujoco_version", "scene_sha256", "model_sha256", "policy_fingerprint",
    "source_matrix_sha256", "interpolation", "segment_duration_s",
    "target_interval_s", "hold_after_first_s", "hold_after_last_s",
    "held_start_tolerance_rad", "velocity_limit_rad_s",
    "acceleration_limit_rad_s2", "phase_labels", "target_cup_xyz_m",
    "anchors",
})
_ANCHOR_KEYS = frozenset({
    "held_state_sha256", "source_route_sha256",
    "source_static_result_sha256", "source_dynamic_result_sha256",
    "held_q_rad", "held_pitch_sum_rad", "held_cup_xyz_m",
    "cup_in_gripper_transform", "endpoints",
})


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode()


def require_held_cup_transfer_profile(value: object) -> dict:
    """Refuse any profile drift, including a recomputed but unreviewed hash."""
    try:
        if (not isinstance(value, dict) or set(value) != _PROFILE_KEYS
                or hashlib.sha256(_canonical(value)).hexdigest() != _CONTENT_SHA
                or value["schema_version"] != 1
                or value["kind"] != "HELD_CUP_TRANSFER_PROFILE"
                or value["eligible_for_collection"] is not False
                or value["backend"] != "mujoco"
                or value["mujoco_version"] != "3.12.0"
                or value["scene_sha256"] != _SCENE_SHA
                or value["model_sha256"] != _MODEL_SHA
                or value["policy_fingerprint"] != _POLICY_SHA
                or value["source_matrix_sha256"] != _MATRIX_SHA
                or value["interpolation"] != "CUBIC_SMOOTHSTEP"
                or value["segment_duration_s"] != 1.0
                or value["target_interval_s"] != 0.002
                or value["hold_after_first_s"] != 0.2
                or value["hold_after_last_s"] != 0.2
                or value["held_start_tolerance_rad"] != 0.001
                or value["velocity_limit_rad_s"] != 0.25
                or value["acceleration_limit_rad_s2"] != 1.2
                or value["phase_labels"] != list(_PHASES)
                or value["target_cup_xyz_m"] != [-0.0788, -0.2475, 0.1835]
                or not isinstance(value["anchors"], dict)
                or set(value["anchors"]) != set(_ANCHORS)):
            raise ValueError("profile identity")
        for anchor in _ANCHORS:
            entry = value["anchors"][anchor]
            if (not isinstance(entry, dict) or set(entry) != _ANCHOR_KEYS
                    or not isinstance(entry["endpoints"], list)
                    or len(entry["endpoints"]) != len(_PHASES)
                    or any(not isinstance(entry[name], str)
                           or len(entry[name]) != 64
                           or any(letter not in "0123456789abcdef" for letter in entry[name])
                           for name in (
                               "held_state_sha256", "source_route_sha256",
                               "source_static_result_sha256",
                               "source_dynamic_result_sha256",
                           ))):
                raise ValueError("anchor identity")
            held = bounded_positions(entry["held_q_rad"])
            endpoints = [bounded_positions(row) for row in entry["endpoints"]]
            pitch = float(entry["held_pitch_sum_rad"])
            if not math.isfinite(pitch) or abs(sum(held[1:4]) - pitch) > 1e-10:
                raise ValueError("held pitch")
            yaw_offset = held[4] - held[0]
            final = endpoints[-1]
            for index, row in enumerate(endpoints, 1):
                if (any(abs(actual - (start + (end - start) * index / 11)) > 1e-12
                        for actual, start, end in zip(row, held, final, strict=True))
                        or abs(sum(row[1:4]) - pitch) > 1e-10
                        or abs(row[4] - row[0] - yaw_offset) > 1e-10
                        or row[5] != held[5]):
                    raise ValueError("anchor trajectory")
            previous = held
            for row in endpoints:
                if (max(abs(end - start) * 1.5 for start, end in zip(
                        previous, row, strict=True)) > value["velocity_limit_rad_s"]
                        or max(abs(end - start) * 6 for start, end in zip(
                            previous, row, strict=True)) > value["acceleration_limit_rad_s2"]):
                    raise ValueError("anchor timing")
                previous = row
            transform = entry["cup_in_gripper_transform"]
            if (not isinstance(transform, list) or len(transform) != 4
                    or any(not isinstance(row, list) or len(row) != 4
                           or any(type(number) not in (int, float)
                                  or not math.isfinite(number) for number in row)
                           for row in transform)
                    or any(abs(actual - expected) > 1e-10 for actual, expected in
                           zip(transform[3], (0., 0., 0., 1.), strict=True))):
                raise ValueError("held transform")
        return value
    except (KeyError, TypeError, ValueError, OverflowError) as error:
        raise ValueError("TRANSFER_PROFILE_BINDING_INVALID") from error


def load_held_cup_transfer_profile(
    path: Path, *, expected_model_sha256: str,
    expected_policy_fingerprint: str,
) -> dict:
    """Load only the reviewed profile bytes for the activated model and policy."""
    try:
        raw = Path(path).read_bytes()
        if (hashlib.sha256(raw).hexdigest() != _RAW_SHA
                or expected_model_sha256 != _MODEL_SHA
                or expected_policy_fingerprint != _POLICY_SHA):
            raise ValueError("profile bytes or activation")
        return require_held_cup_transfer_profile(json.loads(raw))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError("TRANSFER_PROFILE_BINDING_INVALID") from error


def build_held_cup_transfer_segments(
    profile: dict, anchor: str, *, held_q_rad,
) -> list[tuple[str, list[list[float]]]]:
    """Generate the fixed controller grid without issuing a motion command."""
    require_held_cup_transfer_profile(profile)
    if anchor not in _ANCHORS:
        raise ValueError("TRANSFER_ANCHOR_INVALID")
    try:
        observed = bounded_positions(held_q_rad)
        entry = profile["anchors"][anchor]
        held = bounded_positions(entry["held_q_rad"])
        if max(abs(a - b) for a, b in zip(observed, held, strict=True)) > .001:
            raise ValueError("held pose")
    except (TypeError, ValueError) as error:
        raise ValueError("TRANSFER_HELD_POSE_MISMATCH") from error
    result = []
    previous = held
    for index, (phase, endpoint) in enumerate(zip(
            _PHASES, entry["endpoints"], strict=True)):
        rows = []
        for part in range(1, 501):
            fraction = part / 500
            ease = fraction * fraction * (3 - 2 * fraction)
            row = [float(start + (end - start) * ease)
                   for start, end in zip(previous, endpoint, strict=True)]
            rows.append(list(bounded_positions(row)))
        rows[-1] = list(endpoint)
        if index in (0, 10):
            rows.extend([list(endpoint) for _ in range(100)])
        result.append((phase, rows))
        previous = endpoint
    # The finite-difference grid is the one the existing controller contract
    # actually admits. Holds and boundaries are included in this check.
    points = [held] + [row for _, rows in result for row in rows]
    velocities = [tuple((b - a) / .002 for a, b in zip(before, after, strict=True))
                  for before, after in zip(points[:-1], points[1:])]
    if (max(abs(value) for row in velocities for value in row) > .25 + 1e-10
            or max(abs(after - before) / .002
                   for before, after in zip([(0.,) * 6] + velocities[:-1],
                                             velocities, strict=True)
                   for before, after in zip(before, after, strict=True)) > 1.2 + 1e-10):
        raise ValueError("TRANSFER_CONTROLLER_GRID_LIMIT")
    return result
