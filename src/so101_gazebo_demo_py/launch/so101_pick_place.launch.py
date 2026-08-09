from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PythonExpression
from launch_ros.actions import Node


def generate_launch_description():
    share=Path(get_package_share_directory("so101_gazebo_demo_py"))
    run_mode=LaunchConfiguration("run_mode"); start=LaunchConfiguration("start_simulation")
    simulate=IfCondition(PythonExpression(["'",start,"' == 'true'"]))
    return LaunchDescription([
        DeclareLaunchArgument("run_mode",default_value="dry_run",choices=["dry_run","plan_only","execute"]),
        DeclareLaunchArgument("start_simulation",default_value="false",choices=["true","false"]),
        DeclareLaunchArgument("plan_only_state",default_value="MOVE_ABOVE_OBJECT"),
        DeclareLaunchArgument("checkpoint",default_value="/tmp/so101-py-runtime/checkpoint.json"),
        DeclareLaunchArgument("session_id",default_value="launch-session"),
        IncludeLaunchDescription(PythonLaunchDescriptionSource(str(share/"launch/so101_gazebo.launch.py")),launch_arguments={"headless":"true"}.items(),condition=simulate),
        IncludeLaunchDescription(PythonLaunchDescriptionSource(str(share/"launch/so101_move_group_headless.launch.py")),condition=simulate),
        Node(package="so101_gazebo_demo_py",executable="pick_place_state_machine",output="screen",
             arguments=["--mode",run_mode,"--plan-only-state",LaunchConfiguration("plan_only_state"),"--checkpoint",LaunchConfiguration("checkpoint"),"--session-id",LaunchConfiguration("session_id")]),
    ])
