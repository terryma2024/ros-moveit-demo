"""Fresh single-process live execute orchestration used by the public CLI."""

from dataclasses import asdict, dataclass
import json
import math
import os
from pathlib import Path
import time
import uuid

from .gazebo.observer import evaluate_bilateral_contact, evaluate_support_contact, MOVING_PAD_MESH_PENETRATION_CEILING_M
from .physical_outcome import FinalPlacementSample
from .release_settle import ReleaseSettleExecutor
from .moveit.planning import JointPlanRequest, MoveItPlanningClient, make_get_motion_plan_request
from .motion.executor import MoveItExecutionClient, make_execute_goal
from .policy_config import load_policy_bundle
from .test_support.ros_gazebo_backend import RosGazeboLiveBackend


TRACE=("IDLE","PREPARE_OPEN_GRIPPER","MOVE_ABOVE_OBJECT","DESCEND","CLOSE_GRIPPER","WAIT_GRASP_STABLE","MICRO_LIFT","WAIT_MICRO_LIFT_STABLE","VERIFY_PHYSICAL_GRASP","ATTACH_MOVEIT","LIFT","MOVE_ABOVE_PLACE","DESCEND_TO_PLACE","OPEN_GRIPPER","RETREAT","DETACH_MOVEIT","WAIT_RELEASE_SETTLE","VALIDATE_FINAL_PLACEMENT","SYNC_WORLD_OBJECT","DONE")


@dataclass(frozen=True, slots=True)
class ContinuationEvaluation:
    can_continue: bool
    failure_code: str | None
    observed_object_delta_m: tuple[float, float, float]
    position_error_m: float
    telemetry: dict[str, float | bool | None]


@dataclass(frozen=True, slots=True)
class FinalOutcomeEpochs:
    pre_retreat: object
    post_retreat: object


@dataclass(frozen=True, slots=True)
class CollectedFinalOutcome:
    epoch_id: str
    result: object
    final_sample: object

    @property
    def evaluation(self):
        return self.result.evaluation


def collect_final_outcomes_around_retreat(*, collect_epoch, retreat) -> FinalOutcomeEpochs:
    """Collect independent outcome epochs with RETREAT strictly between them."""
    pre_retreat=collect_epoch()
    retreat(pre_retreat)
    post_retreat=collect_epoch()
    return FinalOutcomeEpochs(pre_retreat,post_retreat)


def collect_final_outcome_after_immediate_retreat(
    *, collect_epoch, retreat,
) -> FinalOutcomeEpochs:
    """Retreat first, then collect the sole authoritative physical outcome."""
    retreat()
    return FinalOutcomeEpochs(None,collect_epoch())


def arm_tcp_stable_between(
    previous_pose, current_pose, *, elapsed_s: float,
    max_linear_speed_m_s: float, max_angular_speed_rad_s: float,
) -> bool:
    """Evaluate arm stability from observed TCP motion, not commanded joint targets."""
    values=(*previous_pose,*current_pose,elapsed_s)
    if elapsed_s <= 0.0 or not all(math.isfinite(value) for value in values):
        return False
    linear_speed=math.dist(previous_pose[:3],current_pose[:3])/elapsed_s
    dot=abs(sum(a*b for a,b in zip(previous_pose[3:],current_pose[3:])))
    angular_speed=2.0*math.acos(max(-1.0,min(1.0,dot)))/elapsed_s
    return (
        linear_speed <= max_linear_speed_m_s
        and angular_speed <= max_angular_speed_rad_s
    )


def collect_final_outcome_epoch(
    observer, outcome_policy, *, gazebo_detached: bool, scene_membership: dict,
    monotonic=time.monotonic, wait=time.sleep,
) -> CollectedFinalOutcome:
    """Collect one final epoch through a single persistent pose/contact observer."""
    release_epoch_id=str(uuid.uuid4()); sample_sequence=0; latest_sample=[None]
    previous_tcp=[None]; previous_observed_at=[None]
    def observe_final():
        nonlocal sample_sequence
        observed,contacts=observer.observe(); latest_sample[0]=observed; sample_sequence+=1
        support=evaluate_support_contact(
            contacts, outcome_policy.intended_support_collision,
            outcome_policy.minimum_support_contact_depth_m,
        )
        now=monotonic()
        tcp_pose=(*observed.tcp_xyz,*observed.tcp_xyzw)
        controller_healthy=(
            all(math.isfinite(value) for value in tcp_pose)
            if previous_tcp[0] is None
            else arm_tcp_stable_between(
                previous_tcp[0],tcp_pose,
                elapsed_s=now-previous_observed_at[0],
                max_linear_speed_m_s=outcome_policy.max_linear_speed_m_s,
                max_angular_speed_rad_s=outcome_policy.max_angular_speed_rad_s,
            )
        )
        previous_tcp[0]=tcp_pose; previous_observed_at[0]=now
        moveit_detached=(
            "plastic_cup" in scene_membership["world_objects"]
            and "plastic_cup" not in scene_membership["attached_objects"]
        )
        return FinalPlacementSample(
            release_epoch_id, sample_sequence, now, now,
            (*observed.object_xyz,*observed.object_xyzw), support.supported,
            any(pair.finger_collision != outcome_policy.intended_support_collision for pair in contacts),
            gazebo_detached, moveit_detached, controller_healthy, True, True,
        )
    result=ReleaseSettleExecutor(
        outcome_policy,observe_final,monotonic,wait,lambda:False,
    ).run(release_epoch_id,0)
    return CollectedFinalOutcome(release_epoch_id,result,latest_sample[0])


def evaluate_continuation(
    *, before, after,
    commanded_object_delta_m: tuple[float, float, float],
    position_tolerance_m: float,
    arm_stable: bool,
    contact_evidence,
    q6_position: float | None,
    minimum_axial_progress_m: float | None = None,
    maximum_lateral_drift_m: float | None = None,
) -> ContinuationEvaluation:
    """Evaluate intermediate progress from cup/arm outcomes, retaining contact as telemetry."""
    observed = tuple(
        after.object_xyz[index] - before.object_xyz[index] for index in range(3)
    )
    error = math.dist(observed, commanded_object_delta_m)
    lateral = math.hypot(observed[0], observed[1])
    position_ok = error <= position_tolerance_m
    failure_code = (
        "CUP_POSE_NONFINITE" if not all(
            math.isfinite(value)
            for value in (*before.object_xyz, *after.object_xyz)
        )
        else "ARM_UNSTABLE" if not arm_stable
        else "CUP_INSUFFICIENT_LIFT" if (
            minimum_axial_progress_m is not None
            and observed[2] < minimum_axial_progress_m
        )
        else "CUP_LATERAL_DRIFT" if (
            maximum_lateral_drift_m is not None
            and lateral > maximum_lateral_drift_m
        )
        else None if position_ok
        else "CUP_INTERMEDIATE_POSITION"
    )
    return ContinuationEvaluation(
        can_continue=failure_code is None,
        failure_code=failure_code,
        observed_object_delta_m=observed,
        position_error_m=error,
        telemetry={
            "bilateral_contact": contact_evidence.bilateral,
            "max_moving_pad_penetration_m": (
                contact_evidence.max_moving_pad_penetration_m
            ),
            "q6_position": q6_position,
            "arm_stable": arm_stable,
            "position_tolerance_m": position_tolerance_m,
            "minimum_axial_progress_m": minimum_axial_progress_m,
            "maximum_lateral_drift_m": maximum_lateral_drift_m,
            "observed_lateral_drift_m": lateral,
        },
    )


def _quaternion_multiply(first, second):
    ax,ay,az,aw=first; bx,by,bz,bw=second
    return (
        aw*bx+ax*bw+ay*bz-az*by,
        aw*by-ax*bz+ay*bw+az*bx,
        aw*bz+ax*by-ay*bx+az*bw,
        aw*bw-ax*bx-ay*by-az*bz,
    )


def _rotate(vector, quaternion):
    rotated=_quaternion_multiply(
        _quaternion_multiply(quaternion,(*vector,0.0)),
        (-quaternion[0],-quaternion[1],-quaternion[2],quaternion[3]),
    )
    return rotated[:3]


def compose_pose(parent, relative):
    translated=_rotate(relative[:3],parent[3:])
    return (
        *(parent[index]+translated[index] for index in range(3)),
        *_quaternion_multiply(parent[3:],relative[3:]),
    )


def relative_pose(parent, child):
    inverse=(-parent[3],-parent[4],-parent[5],parent[6])
    translation=_rotate(tuple(child[index]-parent[index] for index in range(3)),inverse)
    return (*translation,*_quaternion_multiply(inverse,child[3:]))


def translated_grasp_pose(pose, translation_offset_m):
    return (
        *(pose[index] + translation_offset_m[index] for index in range(3)),
        *pose[3:],
    )


def rotated_grasp_pose(pose, world_x_rotation_rad: float):
    """Rotate only the pose orientation about the world X axis."""
    half = world_x_rotation_rad / 2.0
    rotation = (math.sin(half), 0.0, 0.0, math.cos(half))
    return (*pose[:3], *_quaternion_multiply(rotation, pose[3:]))


def carry_with_shadow_gates(backend, policies, shadow_gate):
    for name, policy in policies.items():
        shadow_gate(name)
        backend.move_arm(
            policy.waypoints,
            policy.velocity_scaling,
        )


def release_alignment_target(
    place_xyz: tuple[float, float, float],
    settling_compensation_m: tuple[float, float, float] = (0.0050, -0.0050, 0.0140),
) -> tuple[float, float, float]:
    """Offset the held-cup target while preserving pre-open table clearance."""
    return tuple(
        value + compensation
        for value, compensation in zip(
            place_xyz, settling_compensation_m, strict=True,
        )
    )


def release_separation_translation(
    observed, *, distance_m: float = 0.010,
) -> tuple[float, float, float]:
    """Move the opened gripper radially away from the observed cup center."""
    if not 0.0 < distance_m <= 0.030:
        raise ValueError("release separation must stay within the 0.030 m bound")
    dx=observed.tcp_xyz[0]-observed.object_xyz[0]
    dy=observed.tcp_xyz[1]-observed.object_xyz[1]
    radial=math.hypot(dx,dy)
    if not math.isfinite(radial) or radial < 0.001:
        raise RuntimeError("release separation requires a finite radial direction")
    return dx/radial*distance_m,dy/radial*distance_m,0.0


def align_cup_for_release(
    backend, target_xyz, *, execute,
    max_attempts: int = 3, xy_tolerance_m: float = 0.010,
    z_tolerance_m: float = 0.010,
    max_axis_correction_m: float = 0.030,
    max_pre_release_height_error_m: float = 0.030,
    max_arm_linear_speed_m_s: float = 0.005,
    max_arm_angular_speed_rad_s: float = 0.05,
    recovery_settle_s: float = 0.25,
    monotonic=time.monotonic,
    wait=time.sleep,
):
    """Use same-run cup pose feedback for a bounded pre-release XY alignment."""
    current=backend.sample(); reverse_waypoints=[]; telemetry=[]
    for attempt in range(max_attempts+1):
        values=(*current.object_xyz,*current.object_xyzw,*current.tcp_xyz,*current.tcp_xyzw)
        if not all(math.isfinite(value) for value in values):
            raise RuntimeError("place alignment requires finite cup and arm poses")
        height_error=abs(current.object_xyz[2]-target_xyz[2])
        x_error=target_xyz[0]-current.object_xyz[0]
        y_error=target_xyz[1]-current.object_xyz[1]
        z_error=target_xyz[2]-current.object_xyz[2]
        xy_error=math.hypot(x_error,y_error)
        if height_error > max_pre_release_height_error_m:
            raise RuntimeError(
                f"place alignment pre-release height outside plausibility bound: "
                f"{height_error}"
            )
        if xy_error <= xy_tolerance_m and abs(z_error) <= z_tolerance_m:
            return current,tuple(reverse_waypoints),tuple(telemetry)
        if attempt == max_attempts:
            break
        if any(
            abs(error) > max_axis_correction_m
            for error in (x_error,y_error,z_error)
        ):
            raise RuntimeError(
                f"place alignment correction exceeds bound: {(x_error,y_error,z_error)}"
            )
        delta=(x_error,y_error,z_error)
        try:
            points,start_positions=execute(delta,0.15)
        except RuntimeError as error:
            message=str(error)
            recoverable=(
                "MOVEIT_EXECUTION_FAILED" in message
                and "MoveIt execution error -4" in message
            )
            if not recoverable:
                raise
            first_after_abort=backend.sample()
            first_observed_at=monotonic()
            wait(recovery_settle_s)
            after=backend.sample()
            second_observed_at=monotonic()
            arm_stable=arm_tcp_stable_between(
                (*first_after_abort.tcp_xyz,*first_after_abort.tcp_xyzw),
                (*after.tcp_xyz,*after.tcp_xyzw),
                elapsed_s=max(
                    recovery_settle_s,
                    second_observed_at-first_observed_at,
                ),
                max_linear_speed_m_s=max_arm_linear_speed_m_s,
                max_angular_speed_rad_s=max_arm_angular_speed_rad_s,
            )
            after_error=math.hypot(
                target_xyz[0]-after.object_xyz[0],
                target_xyz[1]-after.object_xyz[1],
            )
            telemetry.append({
                "attempt":attempt+1,
                "commanded_translation_m":delta,
                "planned_points":None,
                "before_object_xyz":current.object_xyz,
                "after_object_xyz":after.object_xyz,
                "before_xy_error_m":xy_error,
                "after_xy_error_m":after_error,
                "execution_recovered":True,
                "execution_error":message,
                "arm_stable":arm_stable,
            })
            if not arm_stable:
                raise RuntimeError(
                    "place alignment arm remained unstable after execution abort"
                ) from error
            current=after
            continue
        after=backend.sample()
        after_error=math.hypot(
            target_xyz[0]-after.object_xyz[0],
            target_xyz[1]-after.object_xyz[1],
        )
        telemetry.append({
            "attempt":attempt+1,
            "commanded_translation_m":delta,
            "planned_points":points,
            "before_object_xyz":current.object_xyz,
            "after_object_xyz":after.object_xyz,
            "before_xy_error_m":xy_error,
            "after_xy_error_m":after_error,
            "execution_recovered":False,
        })
        reverse_waypoints.append(tuple(start_positions)); current=after
    raise RuntimeError(
        f"place alignment did not converge within {max_attempts} attempts: "
        f"{current.object_xyz}"
    )


def plan_waypoint_sequence(planner, names, start, waypoints) -> int:
    current=tuple(start); total=0
    for target in waypoints:
        target=tuple(target)
        outcome=planner.plan_joint_path(
            JointPlanRequest(tuple(names),current,target,.03,.03,8.),15.,
        )
        if outcome.failure:
            raise RuntimeError(str(outcome.failure))
        points=len(outcome.trajectory.joint_trajectory.points)
        if points == 0:
            raise RuntimeError("MoveIt returned an empty waypoint plan")
        total+=points; current=target
    return total


def shadow_divergence_healthy(gazebo_pose, shadow_pose, pair_age_s, policy) -> bool:
    values=(*gazebo_pose,*shadow_pose,pair_age_s)
    if len(gazebo_pose) != 7 or len(shadow_pose) != 7 or not all(math.isfinite(value) for value in values):
        return False
    if pair_age_s < 0.0 or pair_age_s > policy.max_pair_age_s:
        return False
    position=math.dist(gazebo_pose[:3],shadow_pose[:3])
    dot=abs(sum(a*b for a,b in zip(gazebo_pose[3:],shadow_pose[3:])))
    orientation=2.0*math.acos(max(-1.0,min(1.0,dot)))
    return position <= policy.max_position_divergence_m and orientation <= policy.max_orientation_divergence_rad


def synchronize_planning_shadow(
    backend, object_in_tcp, policy, apply_scene, *, observe_pose=None,
):
    """Refresh a slipped attached-object shadow from fresh Gazebo truth."""
    observed=backend.sample() if observe_pose is None else observe_pose()
    gazebo_pose=(*observed.object_xyz,*observed.object_xyzw)
    tcp_pose=(*observed.tcp_xyz,*observed.tcp_xyzw)
    if (
        observed.pose_pair_age_s < 0.0
        or observed.pose_pair_age_s > policy.max_pair_age_s
    ):
        raise RuntimeError("planning shadow evidence stale")
    if not all(math.isfinite(value) for value in (*gazebo_pose,*tcp_pose)):
        raise RuntimeError("planning shadow evidence non-finite")
    expected=compose_pose(tcp_pose,object_in_tcp)
    healthy=shadow_divergence_healthy(
        gazebo_pose,expected,observed.pose_pair_age_s,policy,
    )
    check={
        "gazebo_pose":gazebo_pose,
        "shadow_pose":expected,
        "pair_age_s":observed.pose_pair_age_s,
        "healthy_before_sync":healthy,
        "resynchronized":False,
    }
    if not healthy:
        scene=apply_scene("attach",gazebo_pose)
        if "plastic_cup" not in scene["attached_objects"]:
            raise RuntimeError("planning shadow resynchronization failed")
        object_in_tcp=relative_pose(tcp_pose,gazebo_pose)
        check.update({"resynchronized":True,"planning_scene":scene})
    return check,object_in_tcp


def seating_preload_target(q6_contact: float, q6_safe_lower: float, preload_rad: float = 0.006) -> float:
    """Return the configured seating preload without exceeding the q6 floor."""
    return max(q6_safe_lower, q6_contact - preload_rad)


def select_joint_position(names, positions, joint_name: str) -> float:
    """Select one joint position from a JointState-shaped pair of sequences."""
    return float(positions[tuple(names).index(joint_name)])


def _current_joint_position(joint_name: str) -> float:
    import rclpy
    from rclpy.qos import qos_profile_sensor_data
    from sensor_msgs.msg import JointState

    rclpy.init()
    node = rclpy.create_node("so101_py_live_joint_probe")
    latest = []
    subscription = node.create_subscription(
        JointState, "/joint_states", lambda message: latest.append(message),
        qos_profile_sensor_data,
    )
    deadline = time.monotonic() + 5.0
    while not latest and time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=0.1)
    try:
        if not latest:
            raise RuntimeError("joint states unavailable at physical contact")
        return select_joint_position(latest[-1].name, latest[-1].position, joint_name)
    finally:
        node.destroy_subscription(subscription)
        node.destroy_node()
        rclpy.shutdown()


def make_world_z_target(
    current_xyz_xyzw: tuple[float, ...], delta_m: float
) -> tuple[float, ...]:
    """Translate a TCP pose only along world Z."""
    x, y, z, qx, qy, qz, qw = current_xyz_xyzw
    return x, y, z + delta_m, qx, qy, qz, qw


def local_x_world_delta(quaternion_xyzw, distance_m: float):
    x,y,z,w=quaternion_xyzw
    return (
        distance_m*(1-2*(y*y+z*z)),
        distance_m*2*(x*y+w*z),
        distance_m*2*(x*z-w*y),
    )


def make_pose_move_group_goal(names, positions, target_xyz_xyzw):
    """Build the main-workspace request-scoped pose-constrained micro-lift goal."""
    from geometry_msgs.msg import Pose
    from moveit_msgs.action import MoveGroup
    from moveit_msgs.msg import Constraints, OrientationConstraint, PositionConstraint
    from sensor_msgs.msg import JointState
    from shape_msgs.msg import SolidPrimitive

    goal=MoveGroup.Goal()
    goal.request.group_name="arm"
    goal.request.num_planning_attempts=1
    goal.request.allowed_planning_time=5.0
    goal.request.max_velocity_scaling_factor=.03
    goal.request.max_acceleration_scaling_factor=.03
    goal.request.start_state.joint_state=JointState(name=list(names),position=list(positions))
    goal.request.start_state.is_diff=True
    constraints=Constraints()
    position=PositionConstraint()
    position.header.frame_id="world"; position.link_name="so101_tcp"; position.weight=1.0
    position.constraint_region.primitives=[SolidPrimitive(type=SolidPrimitive.BOX,dimensions=[.0004,.0004,.0004])]
    pose=Pose(); pose.position.x,pose.position.y,pose.position.z=target_xyz_xyzw[:3]; pose.orientation.w=1.0
    position.constraint_region.primitive_poses=[pose]
    orientation=OrientationConstraint()
    orientation.header.frame_id="world"; orientation.link_name="so101_tcp"; orientation.weight=1.0
    orientation.orientation.x,orientation.orientation.y,orientation.orientation.z,orientation.orientation.w=target_xyz_xyzw[3:]
    orientation.absolute_x_axis_tolerance=.005; orientation.absolute_y_axis_tolerance=.005; orientation.absolute_z_axis_tolerance=.005
    constraints.position_constraints=[position]; constraints.orientation_constraints=[orientation]
    goal.request.goal_constraints=[constraints]
    goal.planning_options.plan_only=True
    goal.planning_options.planning_scene_diff.is_diff=True
    return goal


def _moveit_plan_execute(target: tuple[float,...], execute: bool = True) -> int:
    import rclpy
    from moveit_msgs.action import ExecuteTrajectory
    from moveit_msgs.srv import GetMotionPlan
    from rclpy.action import ActionClient
    from rclpy.qos import qos_profile_sensor_data
    from sensor_msgs.msg import JointState
    rclpy.init(); node=rclpy.create_node("so101_py_live_moveit")
    latest=[]
    subscription=node.create_subscription(JointState,"/joint_states",lambda message:latest.append(message),qos_profile_sensor_data)
    deadline=time.monotonic()+10
    while not latest and time.monotonic()<deadline: rclpy.spin_once(node,timeout_sec=.1)
    if not latest: raise RuntimeError("joint states unavailable")
    names=("1","2","3","4","5"); index={name:i for i,name in enumerate(latest[-1].name)}
    current=tuple(latest[-1].position[index[name]] for name in names)
    progress=lambda: rclpy.spin_once(node,timeout_sec=.01)
    planner=MoveItPlanningClient(node.create_client(GetMotionPlan,"/plan_kinematic_path"),make_get_motion_plan_request,progress)
    outcome=planner.plan_joint_path(JointPlanRequest(names,current,target,.03,.03,8.),15.)
    if outcome.failure: raise RuntimeError(str(outcome.failure))
    points=len(outcome.trajectory.joint_trajectory.points)
    result=None
    if execute:
        executor=MoveItExecutionClient(ActionClient(node,ExecuteTrajectory,"/execute_trajectory"),make_execute_goal,progress)
        result=executor.execute(outcome.trajectory,30.)
    node.destroy_subscription(subscription); node.destroy_node(); rclpy.shutdown()
    if result is not None and result.failure: raise RuntimeError(str(result.failure))
    return points


def _moveit_plan_waypoints(waypoints) -> int:
    import rclpy
    from moveit_msgs.srv import GetMotionPlan
    from rclpy.qos import qos_profile_sensor_data
    from sensor_msgs.msg import JointState
    rclpy.init(); node=rclpy.create_node("so101_py_live_waypoint_planner")
    latest=[]
    subscription=node.create_subscription(
        JointState,"/joint_states",lambda message:latest.append(message),
        qos_profile_sensor_data,
    )
    deadline=time.monotonic()+10.0
    while not latest and time.monotonic()<deadline:
        rclpy.spin_once(node,timeout_sec=.1)
    if not latest:
        node.destroy_subscription(subscription); node.destroy_node(); rclpy.shutdown()
        raise RuntimeError("joint states unavailable")
    names=("1","2","3","4","5"); index={name:i for i,name in enumerate(latest[-1].name)}
    current=tuple(latest[-1].position[index[name]] for name in names)
    progress=lambda: rclpy.spin_once(node,timeout_sec=.01)
    planner=MoveItPlanningClient(
        node.create_client(GetMotionPlan,"/plan_kinematic_path"),
        make_get_motion_plan_request,progress,
    )
    try:
        return plan_waypoint_sequence(planner,names,current,waypoints)
    finally:
        node.destroy_subscription(subscription); node.destroy_node(); rclpy.shutdown()


def _moveit_plan_grasp_translation(start_positions, translation_offset_m, world_x_rotation_rad: float = 0.0) -> int:
    import rclpy
    from moveit_msgs.action import MoveGroup
    from moveit_msgs.srv import GetPositionFK
    from rclpy.action import ActionClient
    from sensor_msgs.msg import JointState

    rclpy.init(); node=rclpy.create_node("so101_py_grasp_translation_planner")
    names=("1","2","3","4","5")
    fk=node.create_client(GetPositionFK,"/compute_fk")
    try:
        if not fk.wait_for_service(timeout_sec=10.0):
            raise RuntimeError("/compute_fk unavailable")
        request=GetPositionFK.Request()
        request.header.frame_id="world"; request.fk_link_names=["so101_tcp"]
        request.robot_state.joint_state=JointState(
            name=list(names),position=list(start_positions),
        )
        future=fk.call_async(request)
        rclpy.spin_until_future_complete(node,future,timeout_sec=10.0)
        response=future.result() if future.done() else None
        if response is None or response.error_code.val != 1 or not response.pose_stamped:
            raise RuntimeError("DESCEND endpoint FK failed")
        pose=response.pose_stamped[0].pose
        baseline=(
            pose.position.x,pose.position.y,pose.position.z,
            pose.orientation.x,pose.orientation.y,pose.orientation.z,pose.orientation.w,
        )
        target=rotated_grasp_pose(translated_grasp_pose(baseline,translation_offset_m),world_x_rotation_rad)
        client=ActionClient(node,MoveGroup,"/move_action")
        if not client.wait_for_server(timeout_sec=10.0):
            raise RuntimeError("/move_action unavailable")
        future=client.send_goal_async(
            make_pose_move_group_goal(names,start_positions,target),
        )
        rclpy.spin_until_future_complete(node,future,timeout_sec=10.0)
        handle=future.result() if future.done() else None
        if handle is None or not handle.accepted:
            raise RuntimeError("grasp translation plan rejected")
        future=handle.get_result_async()
        rclpy.spin_until_future_complete(node,future,timeout_sec=20.0)
        wrapped=future.result() if future.done() else None
        if wrapped is None or wrapped.result.error_code.val != 1:
            raise RuntimeError("grasp translation planning failed")
        points=len(wrapped.result.planned_trajectory.joint_trajectory.points)
        if points == 0:
            raise RuntimeError("grasp translation plan was empty")
        return points
    finally:
        node.destroy_node(); rclpy.shutdown()


def _moveit_world_z_execute(
    delta_m: float,
    local_x_m: float = 0.0,
    world_translation_m: tuple[float, float, float] = (0.0, 0.0, 0.0),
    world_x_rotation_rad: float = 0.0,
    orientation_tolerance_rad: float = 0.005,
    return_arm_start: bool = False,
):
    import rclpy
    from moveit_msgs.action import ExecuteTrajectory, MoveGroup
    from rclpy.action import ActionClient
    from rclpy.duration import Duration
    from rclpy.qos import qos_profile_sensor_data
    from sensor_msgs.msg import JointState
    from tf2_ros import Buffer, TransformListener
    rclpy.init(); node=rclpy.create_node("so101_py_live_world_z")
    latest=[]; subscription=node.create_subscription(JointState,"/joint_states",lambda message:latest.append(message),qos_profile_sensor_data)
    buffer=Buffer(); listener=TransformListener(buffer,node)
    deadline=time.monotonic()+10; transform=None
    while time.monotonic()<deadline and (not latest or transform is None):
        rclpy.spin_once(node,timeout_sec=.1)
        try: transform=buffer.lookup_transform("world","so101_tcp",rclpy.time.Time(),timeout=Duration(seconds=.05))
        except Exception: transform=None
    if not latest or transform is None: raise RuntimeError("fresh joint/TF state unavailable for world-Z micro lift")
    names=tuple(latest[-1].name); positions=tuple(latest[-1].position)
    position_by_name=dict(zip(names,positions))
    arm_start=tuple(position_by_name[name] for name in ("1","2","3","4","5"))
    target_pose=make_world_z_target((transform.transform.translation.x,transform.transform.translation.y,transform.transform.translation.z,transform.transform.rotation.x,transform.transform.rotation.y,transform.transform.rotation.z,transform.transform.rotation.w),delta_m)
    dx,dy,dz=local_x_world_delta(target_pose[3:],local_x_m)
    target_pose=(target_pose[0]+dx,target_pose[1]+dy,target_pose[2]+dz,*target_pose[3:])
    target_pose=rotated_grasp_pose(translated_grasp_pose(target_pose,world_translation_m),world_x_rotation_rad)
    client=ActionClient(node,MoveGroup,"/move_action")
    if not client.wait_for_server(timeout_sec=10.): raise RuntimeError("/move_action unavailable")
    goal=make_pose_move_group_goal(names,positions,target_pose)
    orientation=goal.request.goal_constraints[0].orientation_constraints[0]
    orientation.absolute_x_axis_tolerance=orientation_tolerance_rad
    orientation.absolute_y_axis_tolerance=orientation_tolerance_rad
    orientation.absolute_z_axis_tolerance=orientation_tolerance_rad
    future=client.send_goal_async(goal); rclpy.spin_until_future_complete(node,future,timeout_sec=5.)
    handle=future.result() if future.done() else None
    if handle is None or not handle.accepted: raise RuntimeError("world-Z MoveGroup goal rejected")
    future=handle.get_result_async(); rclpy.spin_until_future_complete(node,future,timeout_sec=15.)
    wrapped=future.result() if future.done() else None
    if wrapped is None or wrapped.result.error_code.val != 1: raise RuntimeError(f"world-Z MoveGroup planning failed: {None if wrapped is None else wrapped.result.error_code.val}")
    trajectory=wrapped.result.planned_trajectory
    if not trajectory.joint_trajectory.points: raise RuntimeError("world-Z MoveGroup plan was empty")
    progress=lambda: rclpy.spin_once(node,timeout_sec=.01)
    points=len(trajectory.joint_trajectory.points)
    result=MoveItExecutionClient(ActionClient(node,ExecuteTrajectory,"/execute_trajectory"),make_execute_goal,progress).execute(trajectory,30.)
    node.destroy_subscription(subscription); node.destroy_node(); rclpy.shutdown()
    if result.failure: raise RuntimeError(str(result.failure))
    if return_arm_start:
        return points,transform.transform.translation.z,arm_start
    return points,transform.transform.translation.z


def _moveit_world_translation_execute(
    translation_m: tuple[float,float,float], orientation_tolerance_rad: float,
):
    points,_,arm_start=_moveit_world_z_execute(
        0.0,
        world_translation_m=translation_m,
        orientation_tolerance_rad=orientation_tolerance_rad,
        return_arm_start=True,
    )
    return points,arm_start


def _stable_bilateral(backend: RosGazeboLiveBackend, required: int = 6):
    consecutive=0; last=None
    for _ in range(30):
        last=evaluate_bilateral_contact(backend.contacts())
        depth=last.max_moving_pad_penetration_m
        if depth is not None and depth > MOVING_PAD_MESH_PENETRATION_CEILING_M:
            raise RuntimeError(f"moving-pad penetration ceiling exceeded: {depth}")
        consecutive = consecutive + 1 if last.bilateral else 0
        if consecutive >= required: return last
    raise RuntimeError(f"bilateral stability timeout: {last}")


def seat_and_stabilize_physical_grasp(backend, seating_target: float):
    """Apply the preload, then require stable physical contact before shadow attach."""
    backend.move_gripper(seating_target)
    return _stable_bilateral(backend)


def stabilize_to_target_penetration(
    backend, seating_target: float, preopen_q6: float, q6_safe_lower: float,
    minimum_penetration_m: float = 0.0001,
    maximum_penetration_m: float = 0.001,
    adjustment_rad: float = 0.001,
    max_adjustments: int = 4,
):
    """Bound q6 adjustments until stable bilateral penetration is in range."""
    if not 0.0 < minimum_penetration_m <= maximum_penetration_m:
        raise ValueError("invalid target penetration interval")
    if adjustment_rad <= 0.0 or max_adjustments < 0:
        raise ValueError("invalid penetration adjustment policy")
    target=seating_target
    last_error=None
    for adjustment in range(max_adjustments+1):
        try:
            contact=_stable_bilateral(backend)
        except RuntimeError as error:
            if "penetration ceiling exceeded" in str(error):
                raise
            last_error=error
            depth=None
        else:
            depth=contact.max_moving_pad_penetration_m
            if (
                depth is not None
                and minimum_penetration_m <= depth <= maximum_penetration_m
            ):
                return contact,target,adjustment
        if adjustment == max_adjustments:
            break
        if depth is not None and depth > maximum_penetration_m:
            next_target=min(preopen_q6,target+adjustment_rad)
        else:
            backend.move_gripper(preopen_q6)
            next_target=max(q6_safe_lower,target-adjustment_rad)
        if next_target == target:
            break
        target=next_target
        backend.move_gripper(target)
    detail=(
        str(last_error) if last_error is not None
        else f"depth={depth} target_q6={target}"
    )
    raise RuntimeError(
        "target penetration not reached within bounded adjustments: " + detail
    )


def verify_physical_micro_lift(backend, execute=_moveit_world_z_execute):
    """Execute the 2 mm probe and gate continuation on the cup/arm result."""
    before=backend.sample()
    micro_points,micro_start_z=execute(.002)
    contact=evaluate_bilateral_contact(backend.contacts())
    after=backend.sample()
    lift=after.object_xyz[2]-before.object_xyz[2]
    lateral=math.dist(after.object_xyz[:2],before.object_xyz[:2])
    continuation=evaluate_continuation(
        before=before,
        after=after,
        commanded_object_delta_m=(0.0,0.0,0.002),
        position_tolerance_m=0.006,
        minimum_axial_progress_m=0.0001,
        maximum_lateral_drift_m=0.006,
        arm_stable=all(math.isfinite(value) for value in (*after.tcp_xyz,*after.tcp_xyzw)),
        contact_evidence=contact,
        q6_position=None,
    )
    if not continuation.can_continue:
        raise RuntimeError(
            f"physical micro-lift failed {continuation.failure_code} "
            f"lift={lift} lateral={lateral}"
        )
    return lift,lateral,micro_points,micro_start_z,before,after,continuation


def run_bounded_physical_grasp_attempts(
    backend, seating_target: float, preopen_q6: float, q6_safe_lower: float,
    max_attempts: int = 1,
    execute=_moveit_world_z_execute,
):
    """Run a pre-registered number of physical attempts; live defaults to one."""
    if max_attempts < 1:
        raise ValueError("max_attempts must be positive")
    last_error=None
    lifted=False
    for attempt in range(max_attempts):
        target=seating_target
        if attempt:
            if lifted:
                execute(-.002)
                lifted=False
            backend.move_gripper(preopen_q6)
            execute(0.0,local_x_m=-.0002)
            backend.move_gripper(target)
        try:
            contact=evaluate_bilateral_contact(backend.contacts())
            lifted=True
            result=verify_physical_micro_lift(backend,execute=execute)
            return contact,result,attempt+1,target
        except RuntimeError as error:
            last_error=error
    raise last_error


class PlanningSceneShadowClient:
    """Reuse one isolated ROS context while preserving apply-plus-readback semantics."""

    def __init__(self) -> None:
        import rclpy
        from moveit_msgs.srv import ApplyPlanningScene, GetPlanningScene
        from rclpy.executors import SingleThreadedExecutor

        self._context=rclpy.Context()
        self._context.init()
        self._executor=SingleThreadedExecutor(context=self._context)
        self._node=rclpy.create_node("so101_py_scene",context=self._context)
        self._executor.add_node(self._node)
        self._apply_client=self._node.create_client(
            ApplyPlanningScene,"/apply_planning_scene",
        )
        self._get_client=self._node.create_client(
            GetPlanningScene,"/get_planning_scene",
        )
        if (
            not self._apply_client.wait_for_service(timeout_sec=10.)
            or not self._get_client.wait_for_service(timeout_sec=10.)
        ):
            self.close()
            raise RuntimeError("planning scene services unavailable")

    def __enter__(self):
        return self

    def __exit__(self, *_exc_info) -> None:
        self.close()

    def close(self) -> None:
        if getattr(self,"_closed",False):
            return
        self._closed=True
        if hasattr(self,"_executor") and hasattr(self,"_node"):
            self._executor.remove_node(self._node)
            self._executor.shutdown()
        if hasattr(self,"_node"):
            self._node.destroy_node()
        if hasattr(self,"_context") and self._context.ok():
            self._context.shutdown()

    def _wait(self, future, *, timeout_s: float, failure: str):
        self._executor.spin_until_future_complete(future,timeout_sec=timeout_s)
        if not future.done() or future.result() is None:
            raise RuntimeError(failure)
        return future.result()

    def apply(
        self, operation: str, object_pose: tuple[float,...] | None = None,
    ) -> dict:
        from geometry_msgs.msg import Pose
        from moveit_msgs.msg import (
            AttachedCollisionObject, CollisionObject, PlanningScene,
            PlanningSceneComponents,
        )
        from moveit_msgs.srv import ApplyPlanningScene, GetPlanningScene
        from shape_msgs.msg import SolidPrimitive
        scene=PlanningScene(); scene.is_diff=True; scene.robot_state.is_diff=True
        if operation == "attach":
            if object_pose is None:
                raise ValueError("MoveIt shadow attach requires the latest Gazebo object pose")
            attached=AttachedCollisionObject(); attached.link_name="gripper"; attached.touch_links=["gripper","jaw"]
            attached.object.id="plastic_cup"; attached.object.header.frame_id="world"; attached.object.operation=CollisionObject.ADD
            primitive=SolidPrimitive(type=SolidPrimitive.CYLINDER,dimensions=[.08,.036]); attached.object.primitives=[primitive]
            pose=Pose(); pose.position.x,pose.position.y,pose.position.z=object_pose[:3]; pose.orientation.x,pose.orientation.y,pose.orientation.z,pose.orientation.w=object_pose[3:]
            attached.object.primitive_poses=[pose]
            scene.robot_state.attached_collision_objects=[attached]
        elif operation == "detach":
            if object_pose is None:
                raise ValueError("MoveIt shadow detach requires the latest Gazebo object pose")
            remove=AttachedCollisionObject(); remove.object.id="plastic_cup"; remove.object.operation=CollisionObject.REMOVE; scene.robot_state.attached_collision_objects=[remove]
            world=CollisionObject(); world.id="plastic_cup"; world.header.frame_id="world"; world.operation=CollisionObject.ADD
            world.primitives=[SolidPrimitive(type=SolidPrimitive.CYLINDER,dimensions=[.08,.036])]
            pose=Pose(); pose.position.x,pose.position.y,pose.position.z=object_pose[:3]; pose.orientation.x,pose.orientation.y,pose.orientation.z,pose.orientation.w=object_pose[3:]
            world.primitive_poses=[pose]; scene.world.collision_objects=[world]
        else:
            raise ValueError(f"unsupported Planning Scene operation: {operation}")
        request=ApplyPlanningScene.Request(scene=scene)
        applied=self._wait(
            self._apply_client.call_async(request),timeout_s=10.,
            failure="ApplyPlanningScene timed out",
        )
        if not applied.success:
            raise RuntimeError("ApplyPlanningScene failed")
        query=GetPlanningScene.Request()
        query.components.components=(
            PlanningSceneComponents.WORLD_OBJECT_NAMES
            | PlanningSceneComponents.ROBOT_STATE_ATTACHED_OBJECTS
        )
        observed=self._wait(
            self._get_client.call_async(query),timeout_s=10.,
            failure="GetPlanningScene timed out",
        ).scene
        return {
            "world_objects":[item.id for item in observed.world.collision_objects],
            "attached_objects":[
                item.object.id
                for item in observed.robot_state.attached_collision_objects
            ],
        }


def run_live_plan_only(
    evidence_directory: Path,
    state_name: str,
    motion_policy: Path | None = None,
) -> dict:
    from ament_index_python.packages import get_package_share_directory
    from .domain import State
    share=Path(get_package_share_directory("so101_gazebo_demo_py"))
    bundle=load_policy_bundle(
        share/"config/task_objects/light_plastic_cup.yaml",
        motion_policy or share/"config/motion_policies/light_cup_wall_pick.yaml",
        share/"config/validation_policies/light_cup_wall_pick.yaml",
    )
    state=State(state_name)
    if state not in bundle.motion.states:
        raise ValueError(f"motion policy missing state {state_name}")
    points=_moveit_plan_waypoints(bundle.motion.states[state].waypoints)
    if state.value == "DESCEND" and (any(bundle.motion.grasp_tcp_translation_offset_m) or bundle.motion.grasp_tcp_world_x_rotation_rad):
        points += _moveit_plan_grasp_translation(
            bundle.motion.states[state].waypoints[-1],
            bundle.motion.grasp_tcp_translation_offset_m,
            bundle.motion.grasp_tcp_world_x_rotation_rad,
        )
    result={"status":"PLAN_ONLY_COMPLETE","current_state":state_name,"state_trace":[state_name],"exit_code":0,"planned_points":points,"policy_sha256":bundle.sha256}
    evidence_directory=Path(evidence_directory); evidence_directory.mkdir(parents=True,exist_ok=True)
    (evidence_directory/f"plan-only-{state_name}.json").write_text(json.dumps(result,indent=2))
    return result


def run_live_execute(
    evidence_directory: Path,
    stop_after: str | None = None,
    motion_policy: Path | None = None,
) -> dict:
    with PlanningSceneShadowClient() as scene_client:
        return _run_live_execute_with_scene(
            evidence_directory,stop_after,motion_policy,
            apply_scene=scene_client.apply,
        )


def _run_live_execute_with_scene(
    evidence_directory: Path,
    stop_after: str | None,
    motion_policy: Path | None,
    *,
    apply_scene,
) -> dict:
    from ament_index_python.packages import get_package_share_directory
    share=Path(get_package_share_directory("so101_gazebo_demo_py"))
    bundle=load_policy_bundle(share/"config/task_objects/light_plastic_cup.yaml",motion_policy or share/"config/motion_policies/light_cup_wall_pick.yaml",share/"config/validation_policies/light_cup_wall_pick.yaml")
    backend=RosGazeboLiveBackend(
        bundle.validation.physical_outcome.planning_shadow.max_pair_age_s,
    )
    evidence_directory=Path(evidence_directory); evidence_directory.mkdir(parents=True,exist_ok=True)
    initial=backend.sample(); backend.move_gripper(bundle.motion.preopen_q6)
    move_above=bundle.motion.states[next(state for state in bundle.motion.states if state.value=="MOVE_ABOVE_OBJECT")].waypoints
    backend.move_arm(move_above[:-1]); moveit_points=_moveit_plan_execute(move_above[-1])
    state=next(state for state in bundle.motion.states if state.value=="DESCEND"); descend=bundle.motion.states[state]; backend.move_arm(descend.waypoints)
    grasp_offset=bundle.motion.grasp_tcp_translation_offset_m
    grasp_rotation=bundle.motion.grasp_tcp_world_x_rotation_rad
    if any(grasp_offset) or grasp_rotation:
        _moveit_world_z_execute(0.0,world_translation_m=grasp_offset,world_x_rotation_rad=grasp_rotation)
    close_target=bundle.motion.grasp_close_q6
    backend.move_gripper(close_target)
    initial_contact=evaluate_bilateral_contact(backend.contacts())
    if initial_contact.bilateral:
        try: _stable_bilateral(backend)
        except RuntimeError: pass
    q6_contact=_current_joint_position("6")
    seating_target=seating_preload_target(q6_contact,-.059600220867817,bundle.motion.seating_preload_rad)
    try:
        backend.move_gripper(seating_target)
        seated_contact,normalized_seating_target,seating_adjustments=stabilize_to_target_penetration(
            backend,seating_target,bundle.motion.preopen_q6,-.059600220867817,
        )
        seating_actual_q6=_current_joint_position("6")
    except Exception as error:
        (evidence_directory/"physical-failure.json").write_text(json.dumps({
            "status":"FAILED","phase":"POST_SEATING_PHYSICAL_STABILITY",
            "error":str(error),"q6_contact":q6_contact,
            "seating_target_q6":seating_target,
            "gazebo_attachment_state":backend.attachment_state(),
        },indent=2))
        raise
    seating_telemetry={
        "requested_target_q6":seating_target,
        "normalized_target_q6":normalized_seating_target,
        "adjustments":seating_adjustments,
        "actual_q6":seating_actual_q6,
        "bilateral":seated_contact.bilateral,
        "moving_pad_depth_m":seated_contact.max_moving_pad_penetration_m,
    }
    pre_probe=backend.sample()
    shadow_pose=(*pre_probe.object_xyz,*pre_probe.object_xyzw)
    attached_scene=apply_scene("attach",shadow_pose)
    max_grasp_attempts=2
    try:
        contact,physical,physical_attempts,final_grasp_target=run_bounded_physical_grasp_attempts(
            backend,normalized_seating_target,bundle.motion.preopen_q6,-.059600220867817,
            max_attempts=max_grasp_attempts,
        )
    except Exception as error:
        failure_evidence={"status":"FAILED","error":str(error),"initial_contact":asdict(initial_contact),"q6_contact":q6_contact,"seating_target_q6":seating_target,"seating_telemetry":seating_telemetry,"post_seating_contact":asdict(seated_contact),"attempts":max_grasp_attempts,"planning_scene":attached_scene}
        try:
            latest_contact=evaluate_bilateral_contact(backend.contacts())
            latest_pose=backend.sample()
            failure_evidence.update({"latest_contact":asdict(latest_contact),"cup_pose_xyz_xyzw":[*latest_pose.object_xyz,*latest_pose.object_xyzw],"tcp_pose_xyz_xyzw":[*latest_pose.tcp_xyz,*latest_pose.tcp_xyzw],"pose_pair_age_s":latest_pose.pose_pair_age_s,"q6_final":_current_joint_position("6"),"gazebo_attachment_state":backend.attachment_state()})
        except Exception as capture_error:
            failure_evidence["evidence_capture_error"]=str(capture_error)
        (evidence_directory/"physical-failure.json").write_text(json.dumps(failure_evidence,indent=2))
        raise
    lift,lateral,micro_points,micro_start_z,before,after,continuation=physical
    gate={"status":"PROVED","gate_basis":"CUP_AND_ARM_OUTCOME","attachment_state":backend.attachment_state(),"bilateral":contact.bilateral,"max_moving_pad_penetration_m":contact.max_moving_pad_penetration_m,"post_seating_bilateral":seated_contact.bilateral,"post_seating_max_moving_pad_penetration_m":seated_contact.max_moving_pad_penetration_m,"seating_telemetry":seating_telemetry,"moving_pad_penetration_ceiling_m":MOVING_PAD_MESH_PENETRATION_CEILING_M,"cup_world_z_delta_m":lift,"lateral_drift_m":lateral,"micro_lift_command_m":.002,"attempts":physical_attempts,"final_grasp_target_q6":final_grasp_target,"continuation":asdict(continuation)}
    (evidence_directory/"physical-gate.json").write_text(json.dumps(gate,indent=2))
    if stop_after == "VERIFY_PHYSICAL_GRASP":
        result={"status":"CHECKPOINT_COMPLETE","current_state":stop_after,"state_trace":list(TRACE[:9]),"exit_code":0,"physical":gate,"provenance":{"package_share":str(share),"policy_sha256":bundle.sha256,"ros_domain_id":os.environ.get("ROS_DOMAIN_ID"),"gz_partition":os.environ.get("GZ_PARTITION")}}
        (evidence_directory/"live-summary.json").write_text(json.dumps(result,indent=2))
        return result
    shadow_pose=(*after.object_xyz,*after.object_xyzw)
    object_in_tcp=relative_pose((*after.tcp_xyz,*after.tcp_xyzw),shadow_pose)
    shadow_checks=[]
    def gate_shadow(name, observe_pose=None):
        nonlocal object_in_tcp
        started=time.monotonic()
        check,object_in_tcp=synchronize_planning_shadow(
            backend,object_in_tcp,
            bundle.validation.physical_outcome.planning_shadow,
            apply_scene,
            observe_pose=observe_pose,
        )
        check["observation_duration_s"]=time.monotonic()-started
        shadow_checks.append({"state":name,**check})
    carry_policies={}
    for name in ("LIFT","MOVE_ABOVE_PLACE","DESCEND_TO_PLACE"):
        state=next(state for state in bundle.motion.states if state.value==name)
        carry_policies[name]=bundle.motion.states[state]
    with backend.final_observer() as carry_observer:
        observe_carry_pose=lambda:carry_observer.observe()[0]
        carry_with_shadow_gates(
            backend,carry_policies,
            lambda name:gate_shadow(name,observe_pose=observe_carry_pose),
        )
    target_place_xyz=release_alignment_target(
        tuple(bundle.object.place_pose.values[:3])
    )
    outcome_policy=bundle.validation.physical_outcome
    def execute_place_correction(delta,orientation_tolerance_rad):
        gate_shadow("PLACE_ALIGNMENT")
        return _moveit_world_translation_execute(delta,orientation_tolerance_rad)
    placed,_place_reverse_waypoints,place_alignment=align_cup_for_release(
        backend,target_place_xyz,execute=execute_place_correction,
        max_arm_linear_speed_m_s=outcome_policy.max_linear_speed_m_s,
        max_arm_angular_speed_rad_s=outcome_policy.max_angular_speed_rad_s,
    )
    if place_alignment:
        gate_shadow("PRE_RELEASE_RETREAT")
    backend.move_gripper(bundle.motion.release_q6, final_release=True)
    released=backend.sample()
    detached_scene=[None]
    scene_membership=[None]
    synchronized_scene=[None]
    state=next(state for state in bundle.motion.states if state.value=="RETREAT")
    retreat_policy=bundle.motion.states[state]
    release_separation=[None]
    def detach_and_sync(observed):
        observed_pose=(*observed.object_xyz,*observed.object_xyzw)
        detached_scene[0]=apply_scene("detach",observed_pose)
        synchronized_scene[0]=detached_scene[0]
        scene_membership[0]=detached_scene[0]
    def collect_release_epoch():
        with backend.final_observer() as final_observer:
            return collect_final_outcome_epoch(
                final_observer,outcome_policy,
                gazebo_detached=backend.attachment_state() == "detached",
                scene_membership=scene_membership[0],
            )
    if not place_alignment:
        def immediate_retreat():
            backend.move_arm(retreat_policy.waypoints, velocity_scaling=retreat_policy.velocity_scaling)
            retreated=backend.sample()
            retreated_pose=(*retreated.object_xyz,*retreated.object_xyzw)
            detached_scene[0]=apply_scene("detach",retreated_pose)
            synchronized_scene[0]=detached_scene[0]
            scene_membership[0]=detached_scene[0]
        outcomes=collect_final_outcome_after_immediate_retreat(
            collect_epoch=collect_release_epoch,
            retreat=immediate_retreat,
        )
    else:
        detach_and_sync(released)
        def retreat_after_settle(_pre_retreat):
            release_separation[0]=release_separation_translation(placed)
            _moveit_world_translation_execute(
                release_separation[0],0.15,
            )
            _moveit_world_z_execute(
                0.060, orientation_tolerance_rad=0.15,
            )
            retreated=backend.sample()
            detach_and_sync(retreated)
        outcomes=collect_final_outcomes_around_retreat(
            collect_epoch=collect_release_epoch,
            retreat=retreat_after_settle,
        )
    pre_retreat_outcome=outcomes.pre_retreat
    post_retreat_outcome=outcomes.post_retreat
    def outcome_payload(evaluation):
        return {"success":evaluation.success,"failure_code":evaluation.failure_code,"sample_count":evaluation.sample_count,"duration_s":evaluation.duration_s,"max_linear_speed_m_s":evaluation.max_linear_speed_m_s,"max_angular_speed_rad_s":evaluation.max_angular_speed_rad_s,"metrics":dict(evaluation.metrics),"telemetry":[sample.as_dict() for sample in evaluation.telemetry]}
    def final_sample_payload(sample):
        if sample is None:
            return None
        return {
            "object_xyz":[*sample.object_xyz],
            "object_xyzw":[*sample.object_xyzw],
            "tcp_xyz":[*sample.tcp_xyz],
            "tcp_xyzw":[*sample.tcp_xyzw],
            "pose_pair_age_s":sample.pose_pair_age_s,
        }
    def collected_outcome_payload(collected):
        return None if collected is None else outcome_payload(collected.evaluation)
    def collected_final_sample_payload(collected):
        return None if collected is None else final_sample_payload(collected.final_sample)
    settle=outcomes.post_retreat.result
    if not settle.evaluation.success:
        failure={
            "status":"VALID_FAILURE",
            "pre_retreat_outcome":collected_outcome_payload(pre_retreat_outcome),
            "post_retreat_outcome":outcome_payload(post_retreat_outcome.evaluation),
            "pre_retreat_final_sample":collected_final_sample_payload(pre_retreat_outcome),
            "release_start_sample":final_sample_payload(placed),
            "post_retreat_final_sample":final_sample_payload(outcomes.post_retreat.final_sample),
            "gazebo_attachment_state":backend.attachment_state(),
            "planning_scene":synchronized_scene[0],
            "shadow_checks":shadow_checks,
            "place_alignment":place_alignment,
            "release_separation_m":release_separation[0],
        }
        (evidence_directory/"final-outcome-failure.json").write_text(
            json.dumps(failure,indent=2)
        )
        raise RuntimeError(f"post-retreat final physical outcome failed: {settle.evaluation.failure_code}")
    final=outcomes.post_retreat.final_sample
    summary={"status":"DONE","current_state":"DONE","state_trace":TRACE,"exit_code":0,"moveit":{"planned_points":moveit_points,"micro_lift_planned_points":micro_points,"execute_succeeded":True,"attached_scene":attached_scene,"detached_scene":detached_scene[0],"synchronized_scene":synchronized_scene[0],"shadow_checks":shadow_checks,"place_alignment":place_alignment,"release_separation_m":release_separation[0]},"gazebo":{"bilateral_before_attach":contact.bilateral,"max_penetration_m":contact.max_moving_pad_penetration_m,"events":[],"attachment_state":backend.attachment_state(),"initial_object_xyz":initial.object_xyz,"pre_attach_object_xyz":after.object_xyz,"place_object_xyz":placed.object_xyz,"final_object_xyz":final.object_xyz,"final_object_xyzw":final.object_xyzw},"controller":{"arm":"SUCCEEDED","gripper":"SUCCEEDED"},"tf":{"micro_lift_start_z":micro_start_z,"initial_tcp_xyz":initial.tcp_xyz,"final_tcp_xyz":final.tcp_xyz},"physical":{"reclose_target_q6":close_target,"q6_contact":q6_contact,"seating_preload_rad":bundle.motion.seating_preload_rad,"seating_target_q6":seating_target,"micro_lift_world_z":lift,"lateral_drift_m":lateral},"pre_retreat_outcome":collected_outcome_payload(pre_retreat_outcome),"pre_retreat_final_sample":collected_final_sample_payload(pre_retreat_outcome),"release_start_sample":final_sample_payload(placed),"final_outcome":outcome_payload(post_retreat_outcome.evaluation),"provenance":{"package_share":str(share),"policy_sha256":bundle.sha256,"ros_domain_id":os.environ.get("ROS_DOMAIN_ID"),"gz_partition":os.environ.get("GZ_PARTITION")}}
    path=evidence_directory/"live-summary.json"; path.write_text(json.dumps(summary,indent=2)); return summary
