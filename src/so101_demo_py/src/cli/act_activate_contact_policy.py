"""Write a distinct ACT contact activation receipt after exact fingerprint approval."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from so101_demo.act.contact_calibration import (
    _canonical, _write_exclusive, analyze_manifests, make_activation_receipt,
    proposal_validation_mode, verify_disabled_proposal,
)
from so101_demo.act.contact_policy import SPOT_CHECK_CANDIDATE, VALIDATION_MODES


def main(arguments=None):
    parser = argparse.ArgumentParser(prog="act_activate_contact_policy")
    parser.add_argument("--proposal", required=True, type=Path)
    parser.add_argument("--offline", required=True, type=Path)
    parser.add_argument("--live", type=Path,
                        help="the sealed live cohort; required unless --validation-mode is given, refused with it")
    parser.add_argument("--validation-mode", choices=VALIDATION_MODES,
                        help="must match the proposal's recorded mode (offline spot-check, CP-3389)")
    parser.add_argument("--receipt-kind", choices=(SPOT_CHECK_CANDIDATE,),
                        help="spot_check_candidate: usable only by a frozen preselected_target_diagnostic input set; "
                             "--approved-by must be plan:... or agent:..., never the user")
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--policy-fingerprint", required=True)
    parser.add_argument("--approved-by", required=True)
    parser.add_argument("--approval-reference", required=True)
    parser.add_argument("--evidence-root", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    options = parser.parse_args(arguments)
    if (options.live is None) == (options.validation_mode is None):
        parser.error("exactly one of --live (default mode) or --validation-mode (offline spot-check mode) is required")
    proposal = json.loads(options.proposal.read_bytes())
    verify_disabled_proposal(proposal, validation_mode=options.validation_mode)
    metadata = json.loads(options.metadata.read_bytes())
    replay = analyze_manifests(options.offline, options.live, metadata, validation_mode=options.validation_mode)
    if _canonical(proposal) != _canonical(replay):
        raise ValueError("proposal does not match sealed evidence replay")
    receipt = make_activation_receipt(
        proposal, options.policy_fingerprint, approved_by=options.approved_by,
        approval_reference=options.approval_reference,
        evidence_root=options.evidence_root,
        approved_at=datetime.now(timezone.utc).isoformat(), receipt_kind=options.receipt_kind,
    )
    _write_exclusive(options.receipt, _canonical(receipt) + b"\n")
    print(receipt["policy_fingerprint"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
