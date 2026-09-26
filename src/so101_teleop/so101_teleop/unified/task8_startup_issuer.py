"""Legacy import path for pick-place startup issuer."""

import importlib
import sys

sys.modules[__name__] = importlib.import_module(
    "so101_teleop.unified.pick_place_startup_issuer"
)
