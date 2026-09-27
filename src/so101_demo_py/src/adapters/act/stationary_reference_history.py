"""Verify a stamped controller-reference window without granting goal authority."""

import hashlib
import json

from so101_demo.act.contracts import finite, vector
from so101_demo.act.joints import ARM_JOINTS


_JOINT_NAMES = {
    "arm": ARM_JOINTS[:5],
    "gripper": ARM_JOINTS[5:],
    "neck": ("neck_yaw_joint",),
}
_SAMPLES = 51
_STEP_NS = 2_000_000
_SPAN_NS = 100_000_000
_FRAME_KEYS = frozenset(("sim_stamp_ns", "received_monotonic_ns",
                         "joint_names", "positions", "velocities"))


def _nanoseconds(value):
    if type(value) is not int or value < 0:
        raise ValueError("REFERENCE_TIME_INVALID")
    return value


def verify_stationary_reference_history(
    *, selected_sim_time_ns, reference_frames, expected_positions,
    max_wall_age_s, stop_velocity_rad_s, monotonic_ns,
):
    """Require 51 exact 500 Hz frames from all three ACT controllers.

    This result still needs a broker goal/ownership interval fence and the
    physical history for the same epoch before it may enter PathProof.
    """
    try:
        selected = _nanoseconds(selected_sim_time_ns)
        now = _nanoseconds(monotonic_ns())
        max_age = finite(max_wall_age_s)
        velocity_limit = finite(stop_velocity_rad_s)
        if min(max_age, velocity_limit) <= 0 or selected < _SPAN_NS:
            raise ValueError("REFERENCE_WINDOW_CONFIG_INVALID")
        max_age_ns = round(max_age * 1_000_000_000)
        if (type(reference_frames) is not dict
                or set(reference_frames) != set(_JOINT_NAMES)
                or type(expected_positions) is not dict
                or set(expected_positions) != set(_JOINT_NAMES)):
            raise ValueError("REFERENCE_WINDOW_SCOPE_INVALID")
        bridge = selected - _SPAN_NS
        sealed = []
        for kind, names in _JOINT_NAMES.items():
            frames = reference_frames[kind]
            if not isinstance(frames, (tuple, list)) or len(frames) != _SAMPLES:
                raise ValueError("REFERENCE_WINDOW_INCOMPLETE")
            expected = vector(expected_positions[kind], len(names))
            previous_receipt = None
            for index, frame in enumerate(frames):
                if type(frame) is not dict or set(frame) != _FRAME_KEYS:
                    raise ValueError("REFERENCE_FRAME_INVALID")
                stamp = _nanoseconds(frame["sim_stamp_ns"])
                receipt = _nanoseconds(frame["received_monotonic_ns"])
                if (stamp != bridge + index * _STEP_NS
                        or tuple(frame["joint_names"]) != names
                        or not 0 <= now - receipt <= max_age_ns
                        or previous_receipt is not None and receipt < previous_receipt):
                    raise ValueError("REFERENCE_FRAME_SCOPE_INVALID")
                positions = vector(frame["positions"], len(names))
                velocities = vector(frame["velocities"], len(names))
                if (positions != expected
                        or any(abs(value) > velocity_limit for value in velocities)):
                    raise ValueError("REFERENCE_NOT_STATIONARY")
                previous_receipt = receipt
                sealed.append((kind, stamp, receipt, names, positions, velocities))
        encoded = json.dumps(sealed, separators=(",", ":"), allow_nan=False).encode()
        digest = hashlib.sha256(b"SO101_STATIONARY_REFERENCE_WINDOW_V1\0" + encoded).hexdigest()
        return {
            "bridge_sim_time_ns": bridge,
            "selected_sim_time_ns": selected,
            "sample_count_by_controller": {kind: _SAMPLES for kind in _JOINT_NAMES},
            "reference_window_sha256": digest,
            "owner_goal_interval_proof_required": True,
            "command_authority": False,
            "eligible_for_collection": False,
        }
    except (AttributeError, KeyError, TypeError, ValueError, OverflowError) as error:
        raise ValueError("STATIONARY_REFERENCE_HISTORY_INVALID") from error
