"""Rejected legacy launcher with no equivalent unified composition."""


def generate_launch_description():
    raise RuntimeError(
        "so101_mujoco_teleop.launch.py cannot be mapped to so101_demo_py; "
        "launch so101_demo_py and so101_teleop explicitly"
    )
