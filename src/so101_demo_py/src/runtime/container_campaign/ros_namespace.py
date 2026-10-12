"""Explicit container ROS addressing; frame IDs and robot parameters stay intact."""

import copy
import re


def validate_container_namespace(namespace):
    if type(namespace) is not str or re.fullmatch(r"(?:/[a-zA-Z_][a-zA-Z0-9_]*)+", namespace) is None:
        raise ValueError("CONTAINER_ROS_NAMESPACE_INVALID")
    return namespace


def qualified_name(namespace, name):
    if namespace != "/":
        validate_container_namespace(namespace)
    if type(name) is not str or not name.startswith("/") or "//" in name or ".." in name.split("/"):
        raise ValueError("CONTAINER_ROS_NAME_INVALID")
    return name if namespace == "/" else namespace+name


def namespaced_parameters(document, namespace):
    validate_container_namespace(namespace)
    if type(document) is not dict or not document:
        raise ValueError("CONTAINER_ROS_PARAMETERS_INVALID")
    result = {}
    for name, parameters in document.items():
        if type(name) is not str or not name or type(parameters) is not dict:
            raise ValueError("CONTAINER_ROS_PARAMETERS_INVALID")
        source = name if name.startswith("/") else "/"+name
        target = qualified_name(namespace, source)
        if target in result:
            raise ValueError("CONTAINER_ROS_PARAMETERS_INVALID")
        result[target] = copy.deepcopy(parameters)
    return result


def namespace_remappings(namespace):
    validate_container_namespace(namespace)
    names = ("clock", "joint_states", "tf", "tf_static", "robot_description", "mujoco_robot_description",
        "robot_description_semantic", "planning_scene", "planning_scene_world",
        "monitored_planning_scene", "attached_collision_object", "collision_object",
        "apply_planning_scene", "get_planning_scene", "plan_kinematic_path", "get_position_ik",
        "get_position_fk", "query_planner_interface", "check_state_validity", "clear_octomap",
        "trajectory_execution_event", "display_planned_path")
    # Jazzy's installed rcl rejects wildcard remap rules. Keep all current
    # absolute endpoints explicit; relative names already use PushRosNamespace.
    endpoints = set(names)
    controllers = ('arm_controller','gripper_controller','neck_controller')
    for controller in controllers:
        for topic in ('controller_state','state','joint_trajectory','speed_scaling_input',
                      'reference','commands','query_state','transition_event'):
            endpoints.add(controller+'/'+topic)
    actions = tuple(controller+'/follow_joint_trajectory' for controller in controllers) + (
        'execute_trajectory','move_action')
    for action in actions:
        endpoints.add(action)
        for suffix in ('send_goal','get_result','cancel_goal','feedback','status'):
            endpoints.add(action+'/_action/'+suffix)
    for service in ('list_controllers','switch_controller','load_controller','unload_controller',
                    'configure_controller','list_hardware_components','list_hardware_interfaces',
                    'set_hardware_component_state','reload_controller_libraries','list_controller_types'):
        endpoints.add('controller_manager/'+service)
    for camera in ('head_camera','wrist_camera','task_camera'):
        for topic in ('color','camera_info','depth'):
            endpoints.add(camera+'/'+topic)
    endpoints.update('so101/'+name for name in ('attach_object','detach_object','object_attached',
        'object_attached_event','raw/planning_scene_reads','teacher/events',
        'simulation/evidence','simulation/joints','simulation/robot_contacts','simulation/scene_state',
        'simulation/physics_step_chunks','simulation/physics_hazard','simulation/physics_cancellation_request',
        'simulation/physics_cancellation_ack','simulation/physics_step_fence_request','simulation/physics_step_fence_ack'))
    endpoints.add('move_group/moveit')
    return tuple(('/'+name,namespace+'/'+name) for name in sorted(endpoints))
