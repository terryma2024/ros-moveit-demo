"""Derive the contact activation of the side-wrist-indoor rig from the approved side-wrist one (stripped fingerprint equivalence).

Run it as `python -m so101_demo.cli.act_derive_contact_activation`. It only reads the old proposal, the old receipt, the equivalence
record and the installed scene files; it writes a NEW proposal and a NEW receipt (never over an existing file) and re-measures
nothing. See `so101_demo.act.contact_derivation`.
"""

import argparse
import hashlib
from datetime import datetime, timezone
import json
from pathlib import Path

from so101_demo.act import contact_collector, contact_derivation
from so101_demo.act.contact_calibration import _canonical, _write_exclusive
from so101_demo.act.rig_files import rig_model_files


def main(arguments=None):
    parser = argparse.ArgumentParser(prog="act_derive_contact_activation")
    parser.add_argument("--old-proposal", required=True, type=Path)
    parser.add_argument("--old-receipt", required=True, type=Path)
    parser.add_argument("--equivalence-record", required=True, type=Path)
    parser.add_argument("--share", required=True, type=Path, help="the package share (or package root) holding assets/mujoco/act")
    parser.add_argument("--approved-by", required=True)
    parser.add_argument("--approval-reference", required=True)
    parser.add_argument("--evidence-root", required=True, type=Path)
    parser.add_argument("--proposal-out", required=True, type=Path)
    parser.add_argument("--receipt-out", required=True, type=Path)
    options = parser.parse_args(arguments)
    for target in (options.proposal_out, options.receipt_out):
        if target.exists() or target.is_symlink():
            raise FileExistsError(str(target))
    old_scene = options.share / rig_model_files("side-wrist").scene
    new_scene = options.share / rig_model_files("side-wrist-indoor").scene
    new_pins = contact_collector.rig_identity("side-wrist-indoor")
    old_pins = contact_collector.rig_identity("side-wrist")
    # the new pins are the identity of the installed indoor files, not a claim
    import mujoco

    from so101_demo.adapters.act.physics import model_sha256
    if (hashlib.sha256(new_scene.read_bytes()).hexdigest(), model_sha256(mujoco.MjModel.from_xml_path(str(new_scene)))) != new_pins:
        raise ValueError("CONTACT_DERIVATION_PINS_INVALID: the installed indoor scene is not the pinned one")
    old_receipt_bytes = options.old_receipt.read_bytes()
    equivalence_bytes = options.equivalence_record.read_bytes()
    fresh_old, fresh_new = contact_derivation.fresh_stripped_fingerprints(old_scene, new_scene)
    fingerprint = contact_derivation.check_equivalence_record(
        equivalence_bytes, old_scene_sha256=hashlib.sha256(old_scene.read_bytes()).hexdigest(),
        new_scene_sha256=new_pins[0], fresh_old=fresh_old, fresh_new=fresh_new)
    proposal, receipt = contact_derivation.derive_activation(
        json.loads(options.old_proposal.read_bytes()), json.loads(old_receipt_bytes), old_receipt_bytes=old_receipt_bytes,
        equivalence_bytes=equivalence_bytes, stripped_fingerprint=fingerprint, old_pins=old_pins, new_pins=new_pins,
        approved_by=options.approved_by, approval_reference=options.approval_reference, evidence_root=options.evidence_root,
        approved_at=datetime.now(timezone.utc).isoformat())
    _write_exclusive(options.proposal_out, _canonical(proposal) + b"\n")
    _write_exclusive(options.receipt_out, _canonical(receipt) + b"\n")
    print(receipt["policy_fingerprint"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
