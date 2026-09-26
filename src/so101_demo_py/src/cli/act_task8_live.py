"""Legacy console import path for pick-place validation."""

import importlib
import sys

sys.modules[__name__] = importlib.import_module(
    "so101_demo.cli.act_run_pick_place_validation"
)
