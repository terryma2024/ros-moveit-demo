"""Rejected legacy launcher with no equivalent unified composition."""


def generate_launch_description():
    raise RuntimeError(
        "so101_moveit.launch.py cannot be mapped independently; "
        "use a so101_demo_py backend launcher"
    )
