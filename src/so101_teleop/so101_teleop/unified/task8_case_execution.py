"""Legacy import path for pick-place case execution."""

import importlib
import sys

sys.modules[__name__] = importlib.import_module(
    "so101_teleop.unified.pick_place_case_execution"
)
