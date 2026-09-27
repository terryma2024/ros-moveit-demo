"""Compose one admitted child's SEARCH port from installed and measured inputs."""

from __future__ import annotations

from pathlib import Path
import re

import mujoco

from so101_demo.act.calibration import require_gate
from so101_demo.act.contracts import finite
from so101_demo.act.head_search_binding import HeadSearchBinding
from so101_demo.act.pick_place_validation_manifest import require_pick_place_validation_manifest
from so101_demo.core.task_geometry import load_task_geometry
from .physics import model_sha256
from .pick_place_neck_sweep import MujocoNeckSweepChecker
from .pick_place_reset import PickPlaceResetBoundary
from .pick_place_search_boundary import PickPlaceSearchBoundary
from .pick_place_search_port import PickPlaceSearchPhasePort
from .selected_approach_candidate import SelectedApproachCandidate
from .visible_approach_expert_route import VisibleApproachExpertRoute


_CHILD_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")


def build_pick_place_child_search_port(
    *, node, model, contact_pairs, manifest, report, sources,
    command_broker, connection, cancelled, binding: HeadSearchBinding,
    evidence_root: Path, campaign_id: str, worker_id: str, generation: int,
    scene_node_factory, package_share: Path | None = None,
    sweep_factory=MujocoNeckSweepChecker,
    reset_factory=PickPlaceResetBoundary,
    boundary_factory=PickPlaceSearchBoundary,
) -> PickPlaceSearchPhasePort:
    """Build only SEARCH; the consumed startup receipt arms it later."""
    require_gate(report, "pick_place_validation")
    require_pick_place_validation_manifest(manifest)
    root = Path(evidence_root)
    if (not root.is_absolute() or ".." in root.parts or not root.is_dir()
            or root.is_symlink()
            or type(campaign_id) is not str or _CHILD_ID.fullmatch(campaign_id) is None
            or type(worker_id) is not str or _CHILD_ID.fullmatch(worker_id) is None
            or type(generation) is not int or generation < 0
            or not callable(scene_node_factory)
            or not isinstance(binding, HeadSearchBinding)
            or not isinstance(model, mujoco.MjModel)
            or model_sha256(model) != getattr(contact_pairs, "model_sha256", None)
            or getattr(sources, "contact_pairs", None) is not contact_pairs
            or getattr(sources, "session_id", None) !=
               getattr(command_broker, "simulation_session_id", None)
            or getattr(connection, "broker", None) is not command_broker):
        raise ValueError("TASK8_CHILD_PORT_SCOPE_INVALID")
    if package_share is None:
        from ament_index_python.packages import get_package_share_directory
        share = Path(get_package_share_directory("so101_demo_py"))
    else:
        share = Path(package_share)
    scene = share / "assets/mujoco/act/scene.xml"
    geometry_file = share / "assets/common/geometry-manifest.yaml"
    if (not share.is_absolute() or ".." in share.parts
            or not scene.is_file() or not geometry_file.is_file()):
        raise ValueError("TASK8_CHILD_PORT_ASSET_INVALID")
    geometry = load_task_geometry(geometry_file)
    measured = report["measurements"]
    step = finite(measured["path_step_s"]["value"])
    clearance = finite(measured["path_clearance_m"]["value"])
    max_age = finite(measured["max_age_s"]["value"])
    stop_timeout = finite(measured["stop_latency_s"]["value"])
    timestep = finite(float(model.opt.timestep))
    if min(step, clearance, max_age, stop_timeout, timestep) <= 0 or stop_timeout > 30:
        raise ValueError("TASK8_CHILD_PORT_MEASUREMENT_INVALID")
    sweep = sweep_factory(
        scene, expected_model_sha256=contact_pairs.model_sha256,
        protected_roots=("base",),
        allowed_pairs=tuple(sorted(contact_pairs.for_phase("SEARCH"))),
        path_step_s=step, path_clearance_m=clearance,
    )
    validation_root = root / "task8-live"
    case_root = validation_root / campaign_id
    snapshot_root = case_root / "snapshots"
    if (validation_root.is_symlink()
            or case_root.exists() and not case_root.is_dir()
            or case_root.is_symlink() or snapshot_root.exists()
            or snapshot_root.is_symlink()
            or not case_root.resolve().is_relative_to(root.resolve())):
        raise ValueError("TASK8_CHILD_PORT_SCOPE_INVALID")
    snapshot_root.mkdir(parents=True, mode=0o700)
    reset = reset_factory(
        node=node, model=model, manifest=manifest, sources=sources,
        command_broker=command_broker, connection=connection,
        cancelled=cancelled, service_node_factory=scene_node_factory,
    )
    boundary = boundary_factory(
        reset, binding=binding, geometry=geometry,
        snapshot_root=snapshot_root,
        scene_node_factory=scene_node_factory,
        neck_sweep_checker=sweep,
        max_source_wait_s=max_age,
        poll_interval_s=min(timestep, max_age),
        stop_timeout_s=stop_timeout,
    )
    def expert_route_factory(request):
        readback = sources.readback
        config = share / "config/mujoco/act"
        candidate = SelectedApproachCandidate(
            scene_path=scene,
            plugin_path=config / "task6_route_plugins.yaml",
            source_profile_path=config / "task6_visible_approach_v1.json",
            candidate_profile_path=config / "visible_approach_candidate_v1.json",
            session_id=request["session_id"], attempt_id=request["attempt_id"],
            max_skew_s=readback.max_skew,
            max_source_age_s=min(max_age, readback.max_wall_age),
            joint_tolerance_rad=readback.joint_tolerance,
            cup_tolerance_m=readback.cup_position_tolerance,
            stop_velocity_rad_s=command_broker.driver.stop_velocity,
        )
        return VisibleApproachExpertRoute(
            candidate, policy_fingerprint=manifest["contact_policy_fingerprint"])

    return PickPlaceSearchPhasePort(
        boundary, expert_route_factory=expert_route_factory)


# Legacy Python API for version-one pick-place callers.
build_task8_child_search_port = build_pick_place_child_search_port
