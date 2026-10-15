"""Host readback of one phase-2 `processed-result.json` against the phase-1 record it was made from.

Phase 1 sealed a Teacher record (`result.json`, `PENDING_QC`) and a recording receipt. Phase 2 wrote, under
`<run>/processing/<scene>/<attempt>-proc-<n>/`, the episode, the QC report, the topic-loss document and `processed-result.json`.
This module is the Host's independent check of that document. It trusts nothing the processor wrote until it has re-read it:

* the document is the canonical one the processor publishes, of the closed key set, bound to the phase-1 `result.json` hash, to the
  recording receipt hash, to the lease and to the receipt's identity;
* `export_eligible` follows the single rule `result_store.export_eligible` (a Teacher PASS, a QC PASS, a trainable collection mode);
* a `VALID` data verdict is graded again from the files with the same function the processor used (`grade_episode`), without
  the QC memo, so the episode seal, the QC report and the topic-loss binding are re-verified exactly as the inline result readback
  did; an `INVALID` verdict must carry no QC binding, and an episode seal it names must still hash to what it names.

The result is a JSON-exact readback record; anything that does not agree raises `PROCESSED_RESULT_INVALID`.
"""

import hashlib
import json
from pathlib import Path

PROCESSED_KIND = "ACT_PROCESSED_RESULT"
PROCESSED_NAME = "processed-result.json"
READBACK_KIND = "ACT_PROCESSED_RESULT_READBACK"
REFUSAL = "PROCESSED_RESULT_INVALID"
_KEYS = frozenset({
    "kind", "schema_version", "task_id", "scene_id", "proc_attempt", "phase1_result_sha256", "receipt_sha256",
    "lease_identity", "identity", "status", "processor_rc", "diagnostic_fault", "artifacts", "act_data_status",
    "act_data_reason", "act_data_qc", "episode_seal_sha256", "export_eligible", "qc_report_path", "qc_report_sha256",
    "inputs_sha256", "scope_sha256", "audit_manifest_sha256", "collection_mode"})
_BINDING = ("qc_report_path", "qc_report_sha256", "inputs_sha256", "scope_sha256", "audit_manifest_sha256", "collection_mode")
_SHA256 = frozenset("0123456789abcdef")


def _is_sha256(value):
    return type(value) is str and len(value) == 64 and set(value) <= _SHA256


def canonical(document):
    """The bytes the processor publishes: sorted keys, compact separators, one trailing newline."""
    return json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False).encode() + b"\n"


def data_directory(output_dir, document):
    """Where the episode, the QC report and the topic-loss document of a processed result live."""
    base = Path(output_dir)
    return base if document["diagnostic_fault"] == "none" else base / "out"


def _regular(path):
    from so101_demo.act.result_store import _read_regular

    return _read_regular(Path(path))


def verify_processed_result(output_dir, *, sealed, scene_id, result_sha256, receipt_sha256, scope, inputs_manifest,
                            trust_memo=False, regrade=None):
    """The readback record of the processed result in `output_dir`, or `ValueError(PROCESSED_RESULT_INVALID)`.

    `sealed` is the phase-1 sealed attempt directory, `result_sha256` and `receipt_sha256` the phase-1 proof's hashes of its
    `result.json` and recording receipt. `regrade` is a seam for the data grading (default: `processing.grade_episode`)."""
    from so101_demo.act.result_store import export_eligible

    base, sealed = Path(output_dir), Path(sealed)
    try:
        raw = _regular(base / PROCESSED_NAME)
        document = json.loads(raw)
        if type(document) is not dict or raw != canonical(document) or set(document) != _KEYS:
            raise ValueError("document shape")
        if document["kind"] != PROCESSED_KIND or type(document["schema_version"]) is not int or document["schema_version"] != 1:
            raise ValueError("kind")
        phase1_raw = _regular(sealed / "result.json")
        if hashlib.sha256(phase1_raw).hexdigest() != result_sha256 or document["phase1_result_sha256"] != result_sha256:
            raise ValueError("phase-1 result binding")
        phase1 = json.loads(phase1_raw)
        receipt_raw = _regular(sealed / "raw" / "recording-receipt.json")
        if hashlib.sha256(receipt_raw).hexdigest() != receipt_sha256 or document["receipt_sha256"] != receipt_sha256:
            raise ValueError("receipt binding")
        receipt = json.loads(receipt_raw)
        lease = receipt["lease_identity"]
        if {name: lease[name] for name in phase1["lease_identity"]} != phase1["lease_identity"]:
            raise ValueError("lease identity")
        attempt, number = lease["attempt_id"], document["proc_attempt"]
        if (document["scene_id"] != scene_id or lease["point_id"] != scene_id or document["lease_identity"] != lease
                or document["identity"] != receipt["identity"] or receipt["identity"]["attempt_id"] != attempt
                or document["status"] != phase1["status"] or sealed.parent.name != attempt
                or type(number) is not int or number <= 0 or document["task_id"] != f"{scene_id}-proc-{number}"
                or base.name != f"{attempt}-proc-{number}" or base.parent.name != scene_id):
            raise ValueError("identity")
        fault = document["diagnostic_fault"]
        status, qc, mode = document["act_data_status"], document["act_data_qc"], document["collection_mode"]
        if (status not in ("VALID", "INVALID") or qc not in ("PASS", "FAIL", "NOT_RUN") or type(fault) is not str
                or document["export_eligible"] is not export_eligible(document["status"], qc, mode)):
            raise ValueError("verdict")
        episode = document["episode_seal_sha256"]
        out = data_directory(base, document)
        if episode is not None:
            if not _is_sha256(episode) or hashlib.sha256(_regular(out / "episode" / "seal.json")).hexdigest() != episode:
                raise ValueError("episode seal")
        if status == "INVALID":
            if qc != "NOT_RUN" or any(document[name] is not None for name in _BINDING) or document["export_eligible"]:
                raise ValueError("invalid verdict carries a binding")
        else:
            if document["act_data_reason"] is not None or episode is None or qc == "NOT_RUN":
                raise ValueError("valid verdict")
            if regrade is None:
                from so101_demo.runtime.act_processor.processing import grade_episode as regrade
            graded = regrade(out=out, qc_output=out / document["qc_report_path"], lease=lease, identity=document["identity"],
                             scope=Path(scope), inputs_manifest=Path(inputs_manifest), teacher_status=document["status"],
                             trust_memo=trust_memo)
            binding = graded["binding"] or {}
            if (graded["status"] != "VALID" or graded["qc"] != qc or graded["episode_sha256"] != episode
                    or any(binding.get(name) != document[name] for name in _BINDING)):
                raise ValueError("data verdict differs from the files")
        return dict(kind=READBACK_KIND, schema_version=1, status="PASS", scene_id=scene_id, task_id=document["task_id"],
                    proc_attempt=number, output_dir=str(base), data_dir=str(out),
                    processed_result=dict(path=PROCESSED_NAME, sha256=hashlib.sha256(raw).hexdigest()),
                    phase1_result_sha256=result_sha256, receipt_sha256=receipt_sha256, diagnostic_fault=fault,
                    processor_rc=document["processor_rc"], act_data_status=status, act_data_reason=document["act_data_reason"],
                    act_data_qc=qc, export_eligible=document["export_eligible"], episode_seal_sha256=episode,
                    **{name: document[name] for name in _BINDING})
    except (OSError, ValueError, TypeError, KeyError, AttributeError, UnicodeError) as error:
        raise ValueError(REFUSAL) from error
