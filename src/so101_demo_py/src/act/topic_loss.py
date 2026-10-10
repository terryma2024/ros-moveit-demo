"""The per-topic transport-loss gate (phase C): its document and the QC check that binds it.

Where the rule runs. A sealed episode holds the retained rows and the audit streams, not the raw topics of the bag, so a lost
`/joint_states` or `/clock` message cannot be seen from the episode. The scan of the raw bag (`offline/scan.py`) is the one place that
can: it judges every topic the episode uses against that topic's own continuity (a stamp grid, a publisher sequence, a step
match with another topic, the camera pair) over the episode window, and reconciles the recorder's aggregate "messages lost on the
transport layer" with what it found. It writes this document next to the episode. The QC check below makes the document part of
the QC verdict: the report names the document by digest, requires a PASS gate with no loss inside the window, and the QC rule version
changed with it, so a report or memo made without the gate is refused.

The check does not recompute the scan: it cannot, the episode has no raw topics. It is an authenticated record of a rule that ran
where the data was, in the same way the Teacher manifest is an input the QC reads and binds.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

KIND = "ACT_TOPIC_LOSS_GATE"
SCHEMA_VERSION = 1
#: v2 (CP-3394): with a per-topic breakdown, losses logged before the window starts are provably outside it; v1 documents are refused
RULE_VERSION = "topic_loss"
DOCUMENT_NAME = "topic-loss.json"
CHECK_NAME = "topic_loss_gate"
_FIELDS = frozenset({"kind", "schema_version", "rule_version", "identity", "window", "transport_lost", "topics",
                     "lost_in_window", "status", "reasons"})


def document_path(episode_root) -> Path:
    return Path(episode_root).parent / DOCUMENT_NAME


def canonical(document) -> bytes:
    return (json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def build_document(*, identity, window, transport_lost, topics, reasons) -> dict:
    """The gate document. `lost_in_window` counts the messages lost inside the window on topics the episode uses; the gate passes
    only with none, with the aggregate transport loss attributed, and with no reason recorded."""
    lost = sum(item["missing_in_window"] for item in topics.values() if item["used"])
    failed = bool(reasons) or lost > 0 or transport_lost.get("unattributed", 0) > 0 or transport_lost.get("reported") is None
    return {"kind": KIND, "schema_version": SCHEMA_VERSION, "rule_version": RULE_VERSION, "identity": identity,
            "window": window, "transport_lost": transport_lost, "topics": topics, "lost_in_window": lost,
            "status": "FAIL" if failed else "PASS", "reasons": list(reasons)}


def qc_check(episode_root, *, identity, path=None) -> dict:
    """The `topic_loss_gate` check of a QC report: {"status", "reason", "document_sha256", "rule_version", "lost_in_window"}.

    A missing, malformed, foreign-identity or old-rule document is an error, not a FAIL: the QC cannot grade an episode whose gate
    never ran.
    """
    target = document_path(episode_root) if path is None else Path(path)
    try:
        raw = target.read_bytes()
        document = json.loads(raw)
    except (OSError, ValueError) as error:
        raise ValueError("NATIVE_QC_TOPIC_LOSS_ABSENT") from error
    if (type(document) is not dict or set(document) != _FIELDS or document["kind"] != KIND
            or document["schema_version"] != SCHEMA_VERSION or document["rule_version"] != RULE_VERSION
            or raw != canonical(document)):
        raise ValueError("NATIVE_QC_TOPIC_LOSS_INVALID")
    wanted = {key: identity[key] for key in ("session_id", "reset_epoch", "attempt_id")}
    if document["identity"] != wanted:
        raise ValueError("NATIVE_QC_TOPIC_LOSS_IDENTITY_MISMATCH")
    lost = document["lost_in_window"]
    status = "PASS" if document["status"] == "PASS" and lost == 0 and not document["reasons"] else "FAIL"
    reason = "" if status == "PASS" else (document["reasons"][0] if document["reasons"] else "OFFLINE_TOPIC_LOSS")[:300]
    return {"status": status, "reason": reason, "document_sha256": hashlib.sha256(raw).hexdigest(),
            "rule_version": RULE_VERSION, "lost_in_window": lost}


def validate_check(check) -> None:
    from .contracts import sha256

    if (type(check) is not dict or set(check) != {"status", "reason", "document_sha256", "rule_version", "lost_in_window"}
            or check["status"] not in ("PASS", "FAIL") or type(check["reason"]) is not str
            or bool(check["reason"]) != (check["status"] == "FAIL") or check["rule_version"] != RULE_VERSION
            or type(check["lost_in_window"]) is not int or check["lost_in_window"] < 0
            or (check["status"] == "PASS" and check["lost_in_window"] != 0)):
        raise ValueError("topic loss check")
    sha256(check["document_sha256"])
