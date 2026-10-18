"""The calibration gate of a closed-loop evaluation: the contact-policy activation receipt instead of a QUALIFIED report.

`act_session` execute asks for a QUALIFIED calibration report that is never produced. The human ruled (2026-10-18, design
2026-10-18-so101-act-native-rollout-design.md, D8) that a rollout evaluation gets the treatment collection got: the contact-policy
proposal and its user activation receipt are verified the way collection admission verifies them (the disabled proposal, then the
activation of exactly that payload, then the fingerprint equal on both), and the substitution is recorded in the evaluation record.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

RULING = ("Human ruling 2026-10-18 (design 2026-10-18-so101-act-native-rollout-design.md, D8): the contact-policy activation "
          "receipt is bound in place of the never-produced QUALIFIED calibration report, the treatment collection received "
          "(CP-3618, CP-3619; approved 2026-10-13); the substitution is recorded in this evaluation record.")
SUBSTITUTED_BY = "contact_activation_receipt"


def _regular(path) -> Path:
    target = Path(path)
    if not target.is_file() or target.is_symlink():
        raise ValueError("ROLLOUT_ACTIVATION_FILE_INVALID")
    return target


def contact_activation_substitution(receipt_path, proposal_path) -> dict:
    """Verify the receipt against its proposal and return the `artifacts.calibration` substitution block."""

    from .contact_calibration import verify_disabled_proposal
    from .contact_policy import verify_activation

    receipt_file, proposal_file = _regular(receipt_path), _regular(proposal_path)
    receipt_bytes, proposal_bytes = receipt_file.read_bytes(), proposal_file.read_bytes()
    try:
        receipt, proposal = json.loads(receipt_bytes), json.loads(proposal_bytes)
        verify_disabled_proposal(proposal)
        verify_activation(proposal["payload"], receipt)
        if proposal["policy_fingerprint"] != receipt["policy_fingerprint"]:
            raise ValueError("fingerprint differs between the proposal and the receipt")
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("ROLLOUT_ACTIVATION_NOT_VERIFIED") from error
    return {"substituted_by": SUBSTITUTED_BY, "path": str(receipt_file),
            "sha256": hashlib.sha256(receipt_bytes).hexdigest(), "policy_fingerprint": receipt["policy_fingerprint"],
            "proposal": {"path": str(proposal_file), "sha256": hashlib.sha256(proposal_bytes).hexdigest()},
            "ruling": RULING}
