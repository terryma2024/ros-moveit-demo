"""Fresh single-process live execute orchestration used by the public CLI."""

from dataclasses import asdict
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


TRACE=("IDLE","PREPARE_OPEN_GRIPPER","MOVE_ABOVE_OBJECT","DESCEND","CLOSE_GRIPPER","WAIT_GRASP_STABLE","MICRO_LIFT","WAIT_MICRO_LIFT_STABLE","VERIFY_PHYSICAL_GRASP","ATTACH_MOVEIT","LIFT","MOVE_ABOVE_PLACE","DESCEND_TO_PLACE","DETACH_MOVEIT","OPEN_GRIPPER","WAIT_RELEASE_SETTLE","VALIDATE_FINAL_PLACEMENT","SYNC_WORLD_OBJECT","RETREAT","DONE")


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


def carry_with_shadow_gates(backend, policies, shadow_gate):
    for name, policy in policies.items():
        shadow_gate(name)
        backend.move_arm(
            policy.waypoints,
            policy.velocity_scaling if name != "LIFT" else None,
        )


def attachment_safe_contact(evidence) -> bool:
    depth=evidence.max_moving_pad_penetration_m
    return evidence.bilateral and depth is not None and depth <= MOVING_PAD_MESH_PENETRATION_CEILING_M


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


def seating_preload_target(q6_contact: float, q6_safe_lower: float) -> float:
    """Return the main-workspace fixed preload without exceeding the q6 floor."""
    return max(q6_safe_lower, q6_contact - 0.006)


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


def _moveit_plan_execute(target: tuple[float,...]) -> int:
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
    executor=MoveItExecutionClient(ActionClient(node,ExecuteTrajectory,"/execute_trajectory"),make_execute_goal,progress)
    result=executor.execute(outcome.trajectory,30.)
    node.destroy_subscription(subscription); node.destroy_node(); rclpy.shutdown()
    if result.failure: raise RuntimeError(str(result.failure))
    return points


def _moveit_world_z_execute(delta_m: float, local_x_m: float = 0.0) -> tuple[int, float]:
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
    target_pose=make_world_z_target((transform.transform.translation.x,transform.transform.translation.y,transform.transform.translation.z,transform.transform.rotation.x,transform.transform.rotation.y,transform.transform.rotation.z,transform.transform.rotation.w),delta_m)
    dx,dy,dz=local_x_world_delta(target_pose[3:],local_x_m)
    target_pose=(target_pose[0]+dx,target_pose[1]+dy,target_pose[2]+dz,*target_pose[3:])
    client=ActionClient(node,MoveGroup,"/move_action")
    if not client.wait_for_server(timeout_sec=10.): raise RuntimeError("/move_action unavailable")
    future=client.send_goal_async(make_pose_move_group_goal(names,positions,target_pose)); rclpy.spin_until_future_complete(node,future,timeout_sec=5.)
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
    return points, transform.transform.translation.z


def _stable_bilateral(backend: RosGazeboLiveBackend, required: int = 6):
    consecutive=0; last=None
    for _ in range(30):
        last=evaluate_bilateral_contact(backend.contacts())
        consecutive = consecutive + 1 if last.bilateral else 0
        if consecutive >= required: return last
    raise RuntimeError(f"bilateral stability timeout: {last}")


def stabilize_with_contact_missing_retries(
    backend, seating_target: float, preopen_q6: float, q6_safe_lower: float
):
    """Apply at most four 1 mrad contact-missing retries after the first attempt."""
    last_error=None
    for retry in range(5):
        try:
            return _stable_bilateral(backend)
        except RuntimeError as error:
            last_error=error
            if retry == 4:
                break
            backend.move_gripper(preopen_q6)
            retry_target=max(q6_safe_lower,seating_target-.001*(retry+1))
            backend.move_gripper(retry_target)
    raise last_error


def verify_physical_micro_lift(backend, execute=_moveit_world_z_execute):
    """Execute the 2 mm probe, wait for stable contact, then verify object motion."""
    before=backend.sample()
    micro_points,micro_start_z=execute(.002)
    _stable_bilateral(backend)
    after=backend.sample()
    lift=after.object_xyz[2]-before.object_xyz[2]
    lateral=math.dist(after.object_xyz[:2],before.object_xyz[:2])
    if lift < .002 or lateral > .001:
        raise RuntimeError(f"physical micro-lift failed lift={lift} lateral={lateral}")
    return lift,lateral,micro_points,micro_start_z,before,after


def run_bounded_physical_grasp_attempts(
    backend, seating_target: float, preopen_q6: float, q6_safe_lower: float
):
    """Run no more than five complete stabilize/micro-lift physical attempts."""
    last_error=None
    lifted=False
    for attempt in range(5):
        target=seating_target
        if attempt:
            if lifted:
                _moveit_world_z_execute(-.002)
                lifted=False
            backend.move_gripper(preopen_q6)
            _moveit_world_z_execute(0.0,local_x_m=-.0002)
            backend.move_gripper(target)
        try:
            contact=_stable_bilateral(backend)
            lifted=True
            result=verify_physical_micro_lift(backend)
            return contact,result,attempt+1,target
        except RuntimeError as error:
            last_error=error
    raise last_error


def _apply_scene(operation: str, object_pose: tuple[float,...] | None = None) -> dict:
    import rclpy
    from geometry_msgs.msg import Pose
    from moveit_msgs.msg import AttachedCollisionObject, CollisionObject, PlanningScene, PlanningSceneComponents
    from moveit_msgs.srv import ApplyPlanningScene, GetPlanningScene
    from shape_msgs.msg import SolidPrimitive
    rclpy.init(); node=rclpy.create_node(f"so101_py_scene_{operation}")
    apply_client=node.create_client(ApplyPlanningScene,"/apply_planning_scene")
    get_client=node.create_client(GetPlanningScene,"/get_planning_scene")
    if not apply_client.wait_for_service(timeout_sec=10.) or not get_client.wait_for_service(timeout_sec=10.): raise RuntimeError("planning scene services unavailable")
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
        remove=AttachedCollisionObject(); remove.object.id="plastic_cup"; remove.object.operation=CollisionObject.REMOVE; scene.robot_state.attached_collision_objects=[remove]
        world=CollisionObject(); world.id="plastic_cup"; world.header.frame_id="world"; world.operation=CollisionObject.ADD
        world.primitives=[SolidPrimitive(type=SolidPrimitive.CYLINDER,dimensions=[.08,.036])]
        pose=Pose(); pose.position.x,pose.position.y,pose.position.z=object_pose[:3]; pose.orientation.x,pose.orientation.y,pose.orientation.z,pose.orientation.w=object_pose[3:]
        world.primitive_poses=[pose]; scene.world.collision_objects=[world]
    request=ApplyPlanningScene.Request(scene=scene); future=apply_client.call_async(request); rclpy.spin_until_future_complete(node,future,timeout_sec=10.)
    if not future.done() or not future.result().success: raise RuntimeError("ApplyPlanningScene failed")
    query=GetPlanningScene.Request(); query.components.components=PlanningSceneComponents.WORLD_OBJECT_NAMES|PlanningSceneComponents.ROBOT_STATE_ATTACHED_OBJECTS
    future=get_client.call_async(query); rclpy.spin_until_future_complete(node,future,timeout_sec=10.); observed=future.result().scene
    result={"world_objects":[item.id for item in observed.world.collision_objects],"attached_objects":[item.object.id for item in observed.robot_state.attached_collision_objects]}
    node.destroy_node(); rclpy.shutdown(); return result


def run_live_execute(evidence_directory: Path) -> dict:
    from ament_index_python.packages import get_package_share_directory
    share=Path(get_package_share_directory("so101_gazebo_demo_py"))
    bundle=load_policy_bundle(share/"config/task_objects/light_plastic_cup.yaml",share/"config/motion_policies/light_cup_wall_pick.yaml",share/"config/validation_policies/light_cup_wall_pick.yaml")
    backend=RosGazeboLiveBackend(); evidence_directory=Path(evidence_directory); evidence_directory.mkdir(parents=True,exist_ok=True)
    initial=backend.sample(); backend.move_gripper(bundle.motion.preopen_q6)
    move_above=bundle.motion.states[next(state for state in bundle.motion.states if state.value=="MOVE_ABOVE_OBJECT")].waypoints
    backend.move_arm(move_above[:-1]); moveit_points=_moveit_plan_execute(move_above[-1])
    state=next(state for state in bundle.motion.states if state.value=="DESCEND"); descend=bundle.motion.states[state]; backend.move_arm(descend.waypoints)
    close_target=bundle.motion.grasp_close_q6
    backend.move_gripper(close_target)
    initial_contact=evaluate_bilateral_contact(backend.contacts())
    if initial_contact.bilateral:
        try: _stable_bilateral(backend)
        except RuntimeError: pass
    q6_contact=_current_joint_position("6")
    seating_target=seating_preload_target(q6_contact,-.059600220867817)
    backend.move_gripper(seating_target)
    contact,physical,physical_attempts,final_grasp_target=run_bounded_physical_grasp_attempts(backend,seating_target,bundle.motion.preopen_q6,-.059600220867817)
    lift,lateral,micro_points,micro_start_z,before,after=physical
    if not attachment_safe_contact(contact) and final_grasp_target < seating_target:
        backend.move_gripper(seating_target)
        contact=_stable_bilateral(backend)
        after=backend.sample()
        lift=after.object_xyz[2]-before.object_xyz[2]
        lateral=math.dist(after.object_xyz[:2],before.object_xyz[:2])
    if not attachment_safe_contact(contact):
        raise RuntimeError(f"moving-pad attachment ceiling exceeded: {contact.max_moving_pad_penetration_m}")
    if lift < .002 or lateral > .001:
        raise RuntimeError(f"physical gate changed after retraction lift={lift} lateral={lateral}")
    gate={"status":"PROVED","attachment_state":backend.attachment_state(),"bilateral":contact.bilateral,"max_moving_pad_penetration_m":contact.max_moving_pad_penetration_m,"cup_world_z_delta_m":lift,"lateral_drift_m":lateral,"micro_lift_command_m":.002,"attempts":physical_attempts,"final_grasp_target_q6":final_grasp_target}
    (evidence_directory/"physical-gate.json").write_text(json.dumps(gate,indent=2))
    shadow_pose=(*after.object_xyz,*after.object_xyzw)
    attached_scene=_apply_scene("attach",shadow_pose)
    object_in_tcp=relative_pose((*after.tcp_xyz,*after.tcp_xyzw),shadow_pose)
    shadow_checks=[]
    def gate_shadow(name):
        observed=backend.sample()
        gazebo_pose=(*observed.object_xyz,*observed.object_xyzw)
        expected=compose_pose((*observed.tcp_xyz,*observed.tcp_xyzw),object_in_tcp)
        healthy=shadow_divergence_healthy(
            gazebo_pose,expected,observed.pose_pair_age_s,
            bundle.validation.physical_outcome.planning_shadow,
        )
        shadow_checks.append({"state":name,"gazebo_pose":gazebo_pose,"shadow_pose":expected,"pair_age_s":observed.pose_pair_age_s,"healthy":healthy})
        if not healthy:
            raise RuntimeError(f"planning shadow divergence before {name}")
    carry_policies={}
    for name in ("LIFT","MOVE_ABOVE_PLACE","DESCEND_TO_PLACE"):
        state=next(state for state in bundle.motion.states if state.value==name)
        carry_policies[name]=bundle.motion.states[state]
    carry_with_shadow_gates(backend,carry_policies,gate_shadow)
    placed=backend.sample()
    pose=(*placed.object_xyz,*placed.object_xyzw); detached_scene=_apply_scene("detach",pose)
    backend.move_gripper(bundle.motion.release_q6)
    release_epoch_id=str(uuid.uuid4()); sample_sequence=0; latest_sample=[placed]
    outcome_policy=bundle.validation.physical_outcome
    def observe_final():
        nonlocal sample_sequence
        observed=backend.sample(); latest_sample[0]=observed; sample_sequence+=1
        contacts=backend.contacts()
        support=evaluate_support_contact(
            contacts, outcome_policy.intended_support_collision,
            outcome_policy.minimum_support_contact_depth_m,
        )
        now=time.monotonic()
        return FinalPlacementSample(
            release_epoch_id, sample_sequence, now, now,
            (*observed.object_xyz,*observed.object_xyzw), support.supported,
            any(pair.finger_collision != outcome_policy.intended_support_collision for pair in contacts),
            backend.attachment_state() == "detached", True, True, True, True,
        )
    settle=ReleaseSettleExecutor(
        outcome_policy, observe_final, time.monotonic, time.sleep, lambda: False,
    ).run(release_epoch_id,0)
    if not settle.evaluation.success:
        raise RuntimeError(f"final physical outcome failed: {settle.evaluation.failure_code}")
    final=latest_sample[0]
    final_pose=(*final.object_xyz,*final.object_xyzw)
    synchronized_scene=_apply_scene("detach",final_pose)
    state=next(state for state in bundle.motion.states if state.value=="RETREAT"); retreat=bundle.motion.states[state]; backend.move_arm(retreat.waypoints)
    summary={"status":"DONE","current_state":"DONE","state_trace":TRACE,"exit_code":0,"moveit":{"planned_points":moveit_points,"micro_lift_planned_points":micro_points,"execute_succeeded":True,"attached_scene":attached_scene,"detached_scene":detached_scene,"synchronized_scene":synchronized_scene,"shadow_checks":shadow_checks},"gazebo":{"bilateral_before_attach":contact.bilateral,"max_penetration_m":contact.max_moving_pad_penetration_m,"events":[],"attachment_state":backend.attachment_state(),"initial_object_xyz":initial.object_xyz,"pre_attach_object_xyz":after.object_xyz,"place_object_xyz":placed.object_xyz,"final_object_xyz":final.object_xyz,"final_object_xyzw":final.object_xyzw},"controller":{"arm":"SUCCEEDED","gripper":"SUCCEEDED"},"tf":{"micro_lift_start_z":micro_start_z,"initial_tcp_xyz":initial.tcp_xyz,"final_tcp_xyz":final.tcp_xyz},"physical":{"reclose_target_q6":close_target,"q6_contact":q6_contact,"seating_preload_rad":.006,"seating_target_q6":seating_target,"micro_lift_world_z":lift,"lateral_drift_m":lateral},"final_outcome":{"success":settle.evaluation.success,"failure_code":settle.evaluation.failure_code,"sample_count":settle.evaluation.sample_count,"duration_s":settle.evaluation.duration_s,"max_linear_speed_m_s":settle.evaluation.max_linear_speed_m_s,"max_angular_speed_rad_s":settle.evaluation.max_angular_speed_rad_s,"metrics":dict(settle.evaluation.metrics),"telemetry":[sample.as_dict() for sample in settle.evaluation.telemetry]},"provenance":{"package_share":str(share),"policy_sha256":bundle.sha256,"ros_domain_id":os.environ.get("ROS_DOMAIN_ID"),"gz_partition":os.environ.get("GZ_PARTITION")}}
    path=evidence_directory/"live-summary.json"; path.write_text(json.dumps(summary,indent=2)); return summary
