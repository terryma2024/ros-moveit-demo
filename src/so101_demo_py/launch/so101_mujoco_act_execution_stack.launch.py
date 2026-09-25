"""Headless ACT simulation stack; command authority stays in the unified child."""

from so101_demo.runtime.launch_composition import build_act_execution_stack_launch_description


def generate_launch_description():
    return build_act_execution_stack_launch_description()
