"""Light reachability stack: robot_state_publisher and move_group with the parameters of the ACT execution stack, scene_setup, and a fake
simulator for /clock and /joint_states. No MuJoCo, no GPU. Needs LIGHT_FAKE_SIM (path of fake_sim.py)."""
import os
from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import ExecuteProcess
from launch_ros.actions import Node
from so101_demo.act.rig_files import rig_model_files
from so101_demo.act.rig_profile import DEFAULT_RIG
from so101_demo.runtime.launch_composition.mujoco_actions import _moveit_parameters, _render_mujoco_robot_description


def generate_launch_description():
    share = Path(get_package_share_directory("so101_demo_py"))
    scene = str(share / rig_model_files(DEFAULT_RIG).scene)
    robot_description = _render_mujoco_robot_description(share, scene, headless=True, sensor_rendering=True, sim_speed_factor=1.0,
                                                         initial_keyframe="task_start", act_profile=True, rig=DEFAULT_RIG)
    return LaunchDescription([
        ExecuteProcess(cmd=["python3", os.environ["LIGHT_FAKE_SIM"]], output="log"),
        Node(package="robot_state_publisher", executable="robot_state_publisher",
             parameters=[{"use_sim_time": True, "robot_description": robot_description}], output="log"),
        Node(package="so101_mujoco_support", executable="graceful_shutdown_move_group",
             parameters=[_moveit_parameters(share, robot_description, publish_planning_scene=False), {"use_sim_time": True}], output="log"),
        Node(package="so101_demo_py", executable="scene_setup", parameters=[{"use_sim_time": True, "readiness_timeout_s": 90.0}], output="log"),
    ])
