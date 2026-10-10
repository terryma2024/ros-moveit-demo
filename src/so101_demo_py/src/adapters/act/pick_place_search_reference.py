"""Bind a selected SEARCH frame to original controller publications."""

from so101_demo.act.contracts import finite, vector

from .selected_search_source import freeze_selected_search_source
from .stationary_reference_history import verify_stationary_reference_history


_WINDOW_NS = 100_000_000
_WINDOW_STEPS = 50
_CONTROLLERS = ("arm", "gripper", "neck")


def verify_search_stationary_references(sources, observed, physical_proof, *,
                                        stopped_wall_s):
    """Verify the matching publication window without granting command authority."""
    try:
        stop_wall = finite(stopped_wall_s, nonnegative=True)
        selected = freeze_selected_search_source(
            observed, max_skew_s=sources.readback.max_skew)
        scope = (selected["session_id"], selected["reset_epoch"])
        if ((sources.session_id, sources.reset_epoch) != scope
                or sources.phase != "SEARCH" or type(physical_proof) is not dict):
            raise ValueError("SEARCH_REFERENCE_SCOPE_INVALID")
        selected_ns = round(selected["simulation_time_s"] * 1_000_000_000)
        bridge_ns = selected_ns - _WINDOW_NS
        if (bridge_ns < 0
                or physical_proof.get("selected_physics_step") != selected["physics_step"]
                or physical_proof.get("first_physics_step") !=
                   selected["physics_step"] - _WINDOW_STEPS
                or physical_proof.get("interval_ns") != _WINDOW_NS
                or round(finite(physical_proof["selected_sim_time_s"])
                         * 1_000_000_000) != selected_ns
                or round(finite(physical_proof["bridge_sim_time_s"])
                         * 1_000_000_000) != bridge_ns
                or physical_proof.get("selected_source_sha256") !=
                   selected["observation_sha256"]
                or physical_proof.get("stop_confirmed_wall_s") != stop_wall
                or physical_proof.get("controller_interval_proof_required") is not True
                or physical_proof.get("command_authority") is not False
                or physical_proof.get("eligible_for_collection") is not False):
            raise ValueError("SEARCH_REFERENCE_PHYSICS_INVALID")
        raw = observed.physical_readback
        qpos = vector(raw["scene"]["qpos"], len(physical_proof["model_qpos"]))
        qvel = vector(raw["scene"]["qvel"], len(physical_proof["model_qvel"]))
        if (qpos != tuple(physical_proof["model_qpos"])
                or qvel != tuple(physical_proof["model_qvel"])):
            raise ValueError("SEARCH_REFERENCE_PHYSICS_CHANGED")
        reference = raw["reference"]
        positions = vector(reference["positions"], 6)
        if round(finite(reference["requested_sim_time_s"])
                 * 1_000_000_000) != selected_ns:
            raise ValueError("SEARCH_REFERENCE_SELECTED_TIME_INVALID")
        rows = {}
        stop_ns = round(stop_wall * 1_000_000_000)
        for kind in _CONTROLLERS:
            identity, history = sources.readback.broker.recent_controller_references(kind)
            if identity != scope:
                raise ValueError("SEARCH_REFERENCE_EPOCH_INVALID")
            window = tuple(frame for frame in history
                           if bridge_ns <= frame["sim_stamp_ns"] <= selected_ns)
            if any(frame["received_monotonic_ns"] < stop_ns for frame in window):
                raise ValueError("SEARCH_REFERENCE_BEFORE_STOP")
            rows[kind] = window
        neck_position = vector(rows["neck"][-1]["positions"], 1)[0]
        joint_addresses = sources.readback.joints
        tolerance = finite(sources.readback.joint_tolerance)
        if (len(joint_addresses) != 7 or tolerance <= 0
                or abs(neck_position - qpos[joint_addresses[6]]) > tolerance):
            raise ValueError("SEARCH_REFERENCE_NECK_DIVERGED")
        expected = {"arm": positions[:5], "gripper": positions[5:],
                    "neck": (neck_position,)}
        proof = verify_stationary_reference_history(
            selected_sim_time_ns=selected_ns,
            reference_frames=rows, expected_positions=expected,
            max_wall_age_s=sources.readback.max_wall_age,
            stop_velocity_rad_s=sources.readback.broker.stop_velocity,
            monotonic_ns=lambda: round(
                finite(sources.readback.monotonic(), nonnegative=True)
                * 1_000_000_000),
        )
        if (proof["bridge_sim_time_ns"] != bridge_ns
                or proof["selected_sim_time_ns"] != selected_ns
                or (sources.session_id, sources.reset_epoch) != scope
                or sources.phase != "SEARCH"
                or freeze_selected_search_source(
                    observed, max_skew_s=sources.readback.max_skew) != selected):
            raise ValueError("SEARCH_REFERENCE_SCOPE_CHANGED")
        return {**proof, "selected_source_sha256": selected["observation_sha256"],
                "stop_confirmed_wall_s": stop_wall}
    except (AttributeError, IndexError, KeyError, TypeError, ValueError,
            RuntimeError, OverflowError) as error:
        raise ValueError("SEARCH_REFERENCE_HISTORY_INVALID") from error
