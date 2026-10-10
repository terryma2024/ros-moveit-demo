"""Build one pick-place validation head search from the admitted reset and ACT lease."""

from __future__ import annotations

import math
from pathlib import Path

import mujoco

from so101_demo.act.head_search_binding import HeadSearchBinding
from so101_demo.act.search import HeadSearchController
from .detector import build_bound_head_detector
from .ros_neck import RosNeckSearchPort
from .ros_search import RosSearchAdapter
from .pick_place_reset import pick_place_reset_targets


def build_pick_place_search_adapter(node, *, boundary, binding: HeadSearchBinding,
                               request: dict, snapshot_root: Path, neck_sweep_checker,
                               tf_buffer=None) -> RosSearchAdapter:
    """Use the reset epoch, frozen anchor and sole current broker ticket."""
    if (not isinstance(binding, HeadSearchBinding)
            or not callable(getattr(neck_sweep_checker, "check", None))
            or getattr(neck_sweep_checker, "model_sha256", None) !=
               boundary.sources.contact_pairs.model_sha256):
        raise ValueError("TASK8_SEARCH_BINDING_INVALID")

    def guard():
        boundary._guard(request)
        sources = boundary.sources
        receipt = boundary.receipt
        context = boundary.act_context
        if (receipt is None or context is None
                or sources.session_id != request["session_id"]
                or sources.phase != "SEARCH"
                or sources.reset_epoch != receipt.new_epoch
                or (context["owner"], context["session_id"], context["attempt_id"]) !=
                   ("act", request["session_id"], request["attempt_id"])):
            raise RuntimeError("TASK8_SEARCH_SCOPE_MISMATCH")
        world = sources.world.snapshot()
        if (world.simulation_session_id != request["session_id"]
                or world.reset_epoch != receipt.new_epoch
                or world.paused is not False or world.simulation_step < 1):
            raise RuntimeError("TASK8_SEARCH_EPOCH_MISMATCH")
        return boundary.broker.ownership.ticket(
            context["lease_token"], "act", request["session_id"], request["attempt_id"],
        )

    guard()
    sources = boundary.sources
    targets = pick_place_reset_targets(
        boundary.model, boundary.manifest, request,
        expected_model_sha256=sources.contact_pairs.model_sha256,
        expected_mujoco_version=mujoco.mj_versionString(),
    )
    config = binding.search_config(
        session_id=request["session_id"], attempt_id=request["attempt_id"],
        search_start_rad=targets.joints_rad[6],
    )
    floor = sources.scene.floor
    if type(floor) not in (int, float) or not math.isfinite(floor) or floor < 0:
        raise RuntimeError("TASK8_SEARCH_RESET_FLOOR_INVALID")
    detector = build_bound_head_detector(binding, snapshot_root=snapshot_root)
    guard()

    def neck_motion_allowed(current_rad, target_rad):
        guard()
        if not binding.neck_motion_allowed(current_rad, target_rad):
            return False
        try:
            raw = sources.capture(request["attempt_id"])
            world, scene = raw["world"], raw["scene"]
            if (world.simulation_session_id != request["session_id"]
                    or world.reset_epoch != boundary.receipt.new_epoch
                    or world.paused is not False
                    or type(world.simulation_step) is not int
                    or world.simulation_step < 1
                    or scene["simulation_session_id"] != request["session_id"]
                    or scene["reset_epoch"] != world.reset_epoch
                    or scene["simulation_step"] != world.simulation_step
                    or scene["paused"] is not False):
                return False
            return neck_sweep_checker.check(
                scene["qpos"], current_rad=current_rad, target_rad=target_rad,
                duration_s=binding.motion["neck_goal_duration_s"],
            ) is True
        except (AttributeError, KeyError, TypeError, ValueError, RuntimeError):
            return False

    neck = RosNeckSearchPort(
        node, session_id=request["session_id"], attempt_id=request["attempt_id"],
        goal_duration_s=binding.motion["neck_goal_duration_s"],
        submit_lead_s=binding.search_values["submit_lead_s"],
        stop_timeout_s=binding.search_values["stop_latency_s"],
        stop_velocity_rad_s=binding.search_values["stop_velocity_rad_s"],
        max_age_s=binding.search_values["max_age_s"],
        command_guard=neck_motion_allowed,
        broker=boundary.broker, ticket_port=guard,
    )
    adapter = RosSearchAdapter(
        node, HeadSearchController(config), detector.runtime, neck,
        tf_buffer=tf_buffer, operation_guard=guard,
    )
    adapter.reset(config, source_floor_s=floor)
    return adapter


# Legacy Python API for version-one pick-place callers.
build_task8_search_adapter = build_pick_place_search_adapter
