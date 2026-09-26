"""Legacy import path for pick-place neck sweep."""

import importlib
import sys

sys.modules[__name__] = importlib.import_module(
    "so101_demo.adapters.act.pick_place_neck_sweep"
)
