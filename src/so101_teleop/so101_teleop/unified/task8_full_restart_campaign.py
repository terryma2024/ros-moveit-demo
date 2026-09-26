"""Legacy import path for pick-place full restart campaign."""

import importlib
import sys

sys.modules[__name__] = importlib.import_module(
    "so101_teleop.unified.pick_place_full_restart_campaign"
)
