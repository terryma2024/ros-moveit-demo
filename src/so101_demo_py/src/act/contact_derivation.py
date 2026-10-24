"""Re-bind an approved contact calibration to a scene whose stripped physics fingerprint equals the approved scene's.

The approved contact activation receipt binds a policy payload, and the payload carries the sha256 of the scene file and of the
compiled model the calibration was collected on. The side-wrist-indoor scene adds only visual elements, so its stripped physics
fingerprint (`physics_fingerprint.stripped_physics_fingerprint`, record version 2) equals the old scene's, and the same calibration
(thresholds, evidence, motion policy, collector and analyzer hashes) applies to it. `derive_activation` writes the new payload with
the indoor scene and model pins, the new proposal over it, and a receipt that says `derived_by:
stripped_physics_fingerprint_equivalence` and cites the old receipt, the equivalence record and the fingerprint. Nothing is
re-measured, and the old proposal and receipt are only read.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .contact_calibration import _canonical, make_activation_receipt, verify_disabled_proposal
from .contact_policy import DERIVED_BY, canonical_policy_payload, policy_fingerprint, verify_activation

_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_OLD_SCENE, _NEW_SCENE = "old_nominal_side_wrist", "new_nominal_side_wrist_indoor"


def _is_sha(value) -> bool:
    return isinstance(value, str) and _HEX64.fullmatch(value) is not None and set(value) != {"0"}


def fresh_stripped_fingerprints(old_scene, new_scene) -> tuple[str, str]:
    """The stripped physics fingerprints of two scene files, recomputed now (an equivalence record is never taken on trust)."""
    from .physics_fingerprint import stripped_physics_fingerprint_of_file

    return stripped_physics_fingerprint_of_file(old_scene), stripped_physics_fingerprint_of_file(new_scene)


def check_equivalence_record(record_bytes: bytes, *, old_scene_sha256: str, new_scene_sha256: str, fresh_old: str, fresh_new: str) -> str:
    """The stripped fingerprint an equivalence record cites, after it agrees with the scene files and with fingerprints computed now."""

    def refuse(reason):
        raise ValueError("CONTACT_DERIVATION_EQUIVALENCE_INVALID: " + reason)

    try:
        record = json.loads(record_bytes)
        old, new = record["scenes"][_OLD_SCENE], record["scenes"][_NEW_SCENE]
        conclusion = record["conclusion"]
        cited_old, cited_new = old["v2"], new["v2"]
        recorded = (old["scene_sha256"], new["scene_sha256"])
    except (ValueError, KeyError, TypeError):
        refuse("shape")
    if conclusion.get("v2_old_nominal_equals_new_indoor_nominal") is not True or conclusion.get("all_stripped_arrays_identical") is not True:
        refuse("the record does not conclude an equivalence")
    if recorded != (old_scene_sha256, new_scene_sha256):
        refuse("the record is about other scene files")
    if cited_old.get("fingerprint_version") != 2 or cited_new.get("fingerprint_version") != 2:
        refuse("fingerprint version")
    fingerprint = cited_old.get("sha256")
    if not _is_sha(fingerprint) or cited_new.get("sha256") != fingerprint or fresh_old != fingerprint or fresh_new != fingerprint:
        refuse("the stripped fingerprints differ or do not match the files")
    return fingerprint


def derive_activation(old_proposal: dict, old_receipt: dict, *, old_receipt_bytes: bytes, equivalence_bytes: bytes,
                      stripped_fingerprint: str, old_pins: tuple[str, str], new_pins: tuple[str, str], approved_by: str,
                      approval_reference: str, evidence_root: Path, approved_at: str) -> tuple[dict, dict]:
    """`(new proposal, new receipt)` for the scene and model pins `new_pins` (scene sha256, model sha256).

    `old_pins` are the scene and model pins the old proposal must carry. The old receipt must approve the old proposal."""
    from .contact_calibration import proposal_validation_mode

    if not all(_is_sha(value) for value in (*new_pins, *old_pins)) or tuple(new_pins) == tuple(old_pins) or new_pins[0] == old_pins[0]:
        raise ValueError("CONTACT_DERIVATION_PINS_INVALID")
    if not _is_sha(stripped_fingerprint):
        raise ValueError("CONTACT_DERIVATION_FINGERPRINT_INVALID")
    try:
        mode = proposal_validation_mode(old_proposal)
        verify_disabled_proposal(old_proposal, validation_mode=mode)
        verify_activation(old_proposal["payload"], old_receipt)
        if old_receipt["policy_fingerprint"] != old_proposal["policy_fingerprint"] or "derived_by" in old_receipt:
            raise ValueError("fingerprint")
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("CONTACT_DERIVATION_OLD_RECEIPT_INVALID") from error
    payload = old_proposal["payload"]
    if (payload["scene_sha256"], payload["model_sha256"]) != tuple(old_pins):
        raise ValueError("CONTACT_DERIVATION_OLD_PINS_MISMATCH")
    new_payload = {**payload, "scene_sha256": new_pins[0], "model_sha256": new_pins[1]}
    canonical_policy_payload(new_payload)
    proposal = {key: value for key, value in old_proposal.items() if key != "proposal_sha256"}
    proposal["payload"] = new_payload
    proposal["policy_fingerprint"] = policy_fingerprint(new_payload)
    proposal["proposal_sha256"] = hashlib.sha256(_canonical(proposal)).hexdigest()
    verify_disabled_proposal(proposal, validation_mode=mode)
    receipt = make_activation_receipt_for_derived(proposal, approved_by=approved_by, approval_reference=approval_reference,
                                                  evidence_root=evidence_root, approved_at=approved_at,
                                                  old_receipt_sha256=hashlib.sha256(old_receipt_bytes).hexdigest(),
                                                  equivalence_record_sha256=hashlib.sha256(equivalence_bytes).hexdigest(),
                                                  stripped_fingerprint_sha256=stripped_fingerprint)
    return proposal, receipt


def make_activation_receipt_for_derived(proposal: dict, *, approved_by: str, approval_reference: str, evidence_root: Path,
                                        approved_at: str, old_receipt_sha256: str, equivalence_record_sha256: str,
                                        stripped_fingerprint_sha256: str) -> dict:
    """The receipt of a derived proposal: the closed receipt of `contact_calibration` plus the four derivation keys."""
    plain = make_activation_receipt(proposal, proposal["policy_fingerprint"], approved_by=approved_by,
                                    approval_reference=approval_reference, evidence_root=evidence_root, approved_at=approved_at)
    receipt = {**plain, "derived_by": DERIVED_BY, "old_receipt_sha256": old_receipt_sha256,
               "equivalence_record_sha256": equivalence_record_sha256, "stripped_fingerprint_sha256": stripped_fingerprint_sha256}
    verify_activation(proposal["payload"], receipt)
    return receipt
