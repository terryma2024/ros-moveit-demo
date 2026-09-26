"""Legacy import path for pick-place phase orchestration."""

import importlib
import sys

sys.modules[__name__] = importlib.import_module(
    "so101_demo.act.pick_place_runner"
)
