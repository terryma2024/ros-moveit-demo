"""Task 11A composition: turn closed inputs into the spec the unified service is asked to admit.

Everything here happens **before** the service exists, so a refusal costs nothing: no spawn, no reset,
no child process. The qualification contract is created atomically from the explicitly passed,
not-yet-existing path, and a formal run must present a live 40-scene contract.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from so101_demo.act.parallel_collection import (
    create_qualification_contract, require_collection_mode,
)

SPEC_KEYS = frozenset({
    "schema_version", "kind", "manifest_path", "manifest_sha256", "split_manifest_path",
    "calibration_report_path", "calibration_report_sha256", "policy_path", "policy_sha256",
    "activation_receipt_path", "activation_receipt_sha256", "collection_config_path",
    "collection_config_sha256", "runtime_config_path", "runtime_config_sha256", "evidence_root",
    "qualification", "qualification_contract_path", "worker_count", "resume", "wave_index_path",
})


def _digest(path) -> str:
    target = Path(path)
    if not target.is_file() or target.is_symlink():
        raise ValueError("FIXED_COLLECTION_INPUT_UNREADABLE")
    return hashlib.sha256(target.read_bytes()).hexdigest()


def _json(path) -> dict:
    try:
        document = json.loads(Path(path).read_bytes())
    except ValueError as error:
        raise ValueError("FIXED_COLLECTION_INPUT_INVALID") from error
    if not isinstance(document, dict):
        raise ValueError("FIXED_COLLECTION_INPUT_INVALID")
    return document


def require_worker_count(worker_count: int, runtime_config: dict) -> int:
    """The worker count must be explicit and match what the runtime config declares."""

    if type(worker_count) is not int or worker_count < 1:
        raise ValueError("FIXED_COLLECTION_WORKER_COUNT_INVALID")
    declared = runtime_config.get("worker_count")
    if declared is not None and declared != worker_count:
        raise ValueError("FIXED_COLLECTION_WORKER_COUNT_MISMATCH")
    return worker_count


def build_fixed_collection_spec(*, manifest, split_manifest=None, calibration_report, policy,
                                activation_receipt, collection_config, runtime_config, root,
                                qualification: bool, worker_count: int,
                                qualification_contract=None, resume: bool = False) -> dict:
    """Build the closed spec, creating the qualification contract before anything can spawn."""

    from pathlib import Path as _Path

    if type(qualification) is not bool or type(resume) is not bool:
        raise ValueError("FIXED_COLLECTION_FLAG_INVALID")
    evidence_root = _Path(root)
    if (not evidence_root.is_absolute() or not evidence_root.is_dir() or evidence_root.is_symlink()
            or ".." in evidence_root.parts):
        raise ValueError("FIXED_COLLECTION_ROOT_INVALID")
    manifest_document = _json(manifest)
    runtime_document = _json(runtime_config)
    require_worker_count(worker_count, runtime_document)
    kind = manifest_document.get("kind")

    contract_path = None
    if qualification:
        if qualification_contract is None:
            raise ValueError("QUALIFICATION_CONTRACT_PATH_REQUIRED")
        # created atomically from the not-yet-existing path, before any spawn
        contract_path = create_qualification_contract(
            qualification_contract,
            payload={"scenes": len(manifest_document.get("scenarios", []) or [])},
            kind=kind if kind in ("W1", "W2", "W8") else "W8")
        contract = _json(contract_path)
        require_collection_mode(manifest_kind=contract["kind"], qualification_mode=True)
    else:
        contract = _json(qualification_contract) if qualification_contract is not None else None
        require_collection_mode(manifest_kind=kind, qualification_mode=False, contract=contract)

    wave_index_path = None
    if resume:
        wave_index_path = str(evidence_root / "campaign-index.json")
        if not _Path(wave_index_path).is_file():
            raise ValueError("FIXED_COLLECTION_RESUME_INDEX_MISSING")

    return {"schema_version": 1, "kind": "act_fixed_collection",
            "manifest_path": str(manifest), "manifest_sha256": _digest(manifest),
            "split_manifest_path": None if split_manifest is None else str(split_manifest),
            "calibration_report_path": str(calibration_report),
            "calibration_report_sha256": _digest(calibration_report),
            "policy_path": str(policy), "policy_sha256": _digest(policy),
            "activation_receipt_path": str(activation_receipt),
            "activation_receipt_sha256": _digest(activation_receipt),
            "collection_config_path": str(collection_config),
            "collection_config_sha256": _digest(collection_config),
            "runtime_config_path": str(runtime_config),
            "runtime_config_sha256": _digest(runtime_config),
            "evidence_root": str(evidence_root), "qualification": qualification,
            "qualification_contract_path": contract_path, "worker_count": worker_count,
            "resume": resume, "wave_index_path": wave_index_path}
