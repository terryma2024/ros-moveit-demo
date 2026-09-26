"""Legacy import path for pick-place startup proof."""

import importlib
import sys

sys.modules[__name__] = importlib.import_module(
    "so101_teleop.unified.pick_place_startup_proof"
)
