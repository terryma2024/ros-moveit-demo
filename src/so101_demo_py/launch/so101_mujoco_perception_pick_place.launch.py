"""MuJoCo RGB-D perception-driven dynamic pick-place launcher."""

from so101_demo.runtime.launch_composition import (
    build_perception_pick_place_launch_description,
)


def generate_launch_description():
    return build_perception_pick_place_launch_description()
