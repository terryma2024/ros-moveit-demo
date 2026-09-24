"""Analyze explicitly sealed ACT contact cohorts into a disabled proposal."""

import argparse
import json
from pathlib import Path

from so101_demo.act.contact_calibration import (
    _canonical, _write_exclusive, analyze_manifests, verify_disabled_proposal,
)


def main(arguments=None):
    parser = argparse.ArgumentParser(prog="act_analyze_contact_calibration")
    parser.add_argument("--offline", required=True, type=Path)
    parser.add_argument("--live", required=True, type=Path)
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--proposal", required=True, type=Path)
    options = parser.parse_args(arguments)
    metadata = json.loads(options.metadata.read_bytes())
    result = analyze_manifests(options.offline, options.live, metadata)
    verify_disabled_proposal(result)
    _write_exclusive(options.proposal, _canonical(result) + b"\n")
    print(result["policy_fingerprint"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
