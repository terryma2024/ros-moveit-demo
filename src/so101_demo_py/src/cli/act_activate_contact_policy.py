"""Write a distinct ACT contact activation receipt after exact fingerprint approval."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from so101_demo.act.contact_calibration import (
    _canonical, _write_exclusive, analyze_manifests, make_activation_receipt,
    verify_disabled_proposal,
)


def main(arguments=None):
    parser = argparse.ArgumentParser(prog="act_activate_contact_policy")
    parser.add_argument("--proposal", required=True, type=Path)
    parser.add_argument("--offline", required=True, type=Path)
    parser.add_argument("--live", required=True, type=Path)
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--policy-fingerprint", required=True)
    parser.add_argument("--approved-by", required=True)
    parser.add_argument("--approval-reference", required=True)
    parser.add_argument("--evidence-root", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    options = parser.parse_args(arguments)
    proposal = json.loads(options.proposal.read_bytes())
    verify_disabled_proposal(proposal)
    metadata = json.loads(options.metadata.read_bytes())
    replay = analyze_manifests(options.offline, options.live, metadata)
    if _canonical(proposal) != _canonical(replay):
        raise ValueError("proposal does not match sealed evidence replay")
    receipt = make_activation_receipt(
        proposal, options.policy_fingerprint, approved_by=options.approved_by,
        approval_reference=options.approval_reference,
        evidence_root=options.evidence_root,
        approved_at=datetime.now(timezone.utc).isoformat(),
    )
    _write_exclusive(options.receipt, _canonical(receipt) + b"\n")
    print(receipt["policy_fingerprint"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
