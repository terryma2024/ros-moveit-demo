"""Explicit MuJoCo stack launcher."""

from so101_demo.runtime.launch_composition import build_launch_description


def generate_launch_description():
    return build_launch_description(backend="mujoco", pick_place=False)
