"""Compose one admitted child's SEARCH port from installed and measured inputs."""

from __future__ import annotations

from pathlib import Path
import re

import mujoco

from so101_demo.act.calibration import require_gate
from so101_demo.act.contracts import finite
from so101_demo.act.head_search_binding import HeadSearchBinding
from so101_demo.act.approach_grasp_contact_diagnostic import build_full_manifest
from so101_demo.act.alternate_anchor_grasp_contact_diagnostic import build_alt_manifest
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
    policy_proposal_path: Path | None = None,
    policy_receipt_path: Path | None = None,
    sweep_factory=MujocoNeckSweepChecker,
    reset_factory=PickPlaceResetBoundary,
    boundary_factory=PickPlaceSearchBoundary,
    path_process_factory=None,
    route_motion: dict | None = None,
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
    if (policy_proposal_path is None) != (policy_receipt_path is None):
        raise ValueError("PICK_PLACE_APPROACH_ROUTE_ACTIVATION_INVALID")
    route_factory = None
    if policy_proposal_path is not None:
        proposal = Path(policy_proposal_path)
        receipt = Path(policy_receipt_path)
        if (not proposal.is_absolute() or not receipt.is_absolute()
                or ".." in proposal.parts or ".." in receipt.parts
                or not proposal.is_file() or not receipt.is_file()):
            raise ValueError("PICK_PLACE_APPROACH_ROUTE_ACTIVATION_INVALID")

        def route_factory(request):
            cases = (*manifest["prefix_cases"], *manifest["full_cases"])
            selected = [case for case in cases
                        if case["case_id"] == request.get("scenario_id")]
            if len(selected) != 1:
                raise ValueError("PICK_PLACE_APPROACH_ROUTE_CASE_INVALID")
            anchor = selected[0]["anchor"]
            config = share / "config/mujoco/act"
            common = dict(
                scene_path=scene,
                plugin_path=config / "task6_route_plugins.yaml",
                proposal_path=proposal, receipt_path=receipt,
                session_id=request["session_id"],
                attempt_id=request["attempt_id"],
            )
            if anchor == "default":
                return build_full_manifest(
                    route_profile_path=config / "task6_visible_approach_v1.json",
                    profile_path=config / "task6_contact_transition_v1.json",
                    **common,
                )
            return build_alt_manifest(
                anchors_path=share / "config/act/task8-live-anchors.yaml",
                profile_path=config / "task6_alt_full_contact_v1.json",
                anchor=anchor, **common,
            )
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
        route_factory=route_factory,
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

    port = PickPlaceSearchPhasePort(boundary, expert_route_factory=expert_route_factory)
    # APPROACH's inspection authority is built only when the caller supplies the ADMITTED route motion: the screen
    # needs a path checker whose model hash matches the sources', and the checker's configuration is not something this
    # builder may invent. A SEARCH-only caller therefore gets no screen and `execute_approach` refuses by name; a full
    # case must pass the admitted document, which is the only source for those values.
    if route_motion is not None:
        from .physics import MujocoPathProcess
        from .pick_place_approach_path_screen import PickPlaceApproachPathScreen

        factory = MujocoPathProcess if path_process_factory is None else path_process_factory
        checker = factory(check_timeout_s=route_motion["submit_lead_s"], start_timeout_s=2.0,
                          model_path=route_motion["model_path"], protected_roots=("base",),
                          cup_joint="cup_free_joint", gripper_body="gripper",
                          path_step_s=route_motion["path_step_s"],
                          path_clearance_m=route_motion["path_clearance_m"],
                          velocity_limit_rad_s=route_motion["velocity_limit_rad_s"],
                          acceleration_limit_rad_s2=route_motion["acceleration_limit_rad_s2"])
        if checker.model_sha256 != route_motion["model_sha256"]:
            checker.close()
            raise ValueError("APPROACH_CHECKER_MODEL_HASH_INVALID")
        boundary.approach_screen = PickPlaceApproachPathScreen(
            search_port=port, sources=sources, broker=command_broker, path_checker=checker,
            cancelled=cancelled)
    return port


# Legacy Python API for version-one pick-place callers.
build_task8_child_search_port = build_pick_place_child_search_port
