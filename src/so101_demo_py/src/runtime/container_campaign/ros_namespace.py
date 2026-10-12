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
    roots = ("arm_controller", "gripper_controller", "neck_controller", "controller_manager",
             "execute_trajectory", "move_group", "task_camera", "head_camera", "wrist_camera", "so101")
    return tuple(("/"+name, namespace+"/"+name) for name in names) + tuple(
        ("/"+name+"/**", namespace+"/"+name+"/\\1") for name in roots)
