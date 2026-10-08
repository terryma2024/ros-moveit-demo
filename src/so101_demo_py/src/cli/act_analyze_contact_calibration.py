"""Analyze explicitly sealed ACT contact cohorts into a disabled proposal."""

import argparse
import json
from pathlib import Path

from so101_demo.act.contact_calibration import (
    _canonical, _write_exclusive, analyze_manifests, proposal_validation_mode, verify_disabled_proposal,
)
from so101_demo.act.contact_policy import VALIDATION_MODES


def main(arguments=None):
    parser = argparse.ArgumentParser(prog="act_analyze_contact_calibration")
    parser.add_argument("--offline", required=True, type=Path)
    parser.add_argument("--live", type=Path,
                        help="the sealed live cohort; required unless --validation-mode is given, refused with it")
    parser.add_argument("--validation-mode", choices=VALIDATION_MODES,
                        help="explicit recorded deviation (CP-3389): fit offline, no live cohort, Teacher spot-checks pending")
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--proposal", required=True, type=Path)
    options = parser.parse_args(arguments)
    if (options.live is None) == (options.validation_mode is None):
        parser.error("exactly one of --live (default mode) or --validation-mode (offline spot-check mode) is required")
    metadata = json.loads(options.metadata.read_bytes())
    result = analyze_manifests(options.offline, options.live, metadata, validation_mode=options.validation_mode)
    verify_disabled_proposal(result, validation_mode=proposal_validation_mode(result))
    _write_exclusive(options.proposal, _canonical(result) + b"\n")
    print(result["policy_fingerprint"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
