from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        Node(
            package="fixed_pose_goal",
            executable="interactive_marker_pose_feedback",
            name="interactive_marker_pose_feedback",
            output="screen",
        ),
        Node(
            package="fixed_pose_goal",
            executable="fixed_pose_goal",
            name="fixed_pose_goal",
            output="screen",
        ),
    ])
