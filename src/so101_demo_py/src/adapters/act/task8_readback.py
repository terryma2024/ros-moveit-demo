"""Legacy import path for pick-place readback."""

import importlib
import sys

sys.modules[__name__] = importlib.import_module(
    "so101_demo.adapters.act.pick_place_readback"
)
