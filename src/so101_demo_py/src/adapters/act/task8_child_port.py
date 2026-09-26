"""Legacy import path for pick-place child port."""

import importlib
import sys

sys.modules[__name__] = importlib.import_module(
    "so101_demo.adapters.act.pick_place_child_port"
)
