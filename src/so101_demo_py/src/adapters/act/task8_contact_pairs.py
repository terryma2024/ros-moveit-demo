"""Legacy import path for version-one phase contact allowlists."""

import importlib
import sys

sys.modules[__name__] = importlib.import_module(
    "so101_demo.adapters.act.phase_contact_allowlist"
)
