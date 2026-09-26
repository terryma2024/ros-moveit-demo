"""Legacy import path for the source-bound diagnostic contract."""

import importlib
import sys

sys.modules[__name__] = importlib.import_module(
    "so101_demo.act.grasp_contact_transition_diagnostic"
)
