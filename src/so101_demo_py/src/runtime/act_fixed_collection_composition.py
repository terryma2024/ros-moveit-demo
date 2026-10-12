"""Prepare collection inputs and operation specs for unified campaign admission."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from so101_demo.act.parallel_collection import (
    create_qualification_contract, require_collection_mode,
)


def _collection_runtime(path):
    """Resolve lease/domain budgets from the frozen collection runtime binding."""
    from ament_index_python.packages import get_package_share_directory
    from so101_demo.act.collection_config import load_collection_config
    from so101_demo.cli.mujoco_batch.request import _load_runtime_config

    share = Path(get_package_share_directory('so101_demo_py'))
    collection = load_collection_config(Path(path),package_share=share)
    return _load_runtime_config(share/collection['parallel_runtime']['path'])


def prepare_collection_operation(arguments, *, services):
    """Prepare a real operation without admitting, allocating or writing files.

    Generation is the next persistent validation generation. The unified entry
    compares and commits that allocation atomically with admission; a competing
    admission makes this proposal stale. No admitted context exists here.
    """
    from dataclasses import asdict
    import re

    from so101_demo.act.parallel_collection_contracts import (
        read_document,validate_functional_contract,validate_qualification_contract,
    )
    from so101_demo.runtime.container_campaign.paths import validate_registered_evidence_root
    from so101_demo.runtime.inference.config import load_campaign_config
    from so101_teleop.unified.admission import _COLLECTION_PAYLOAD_KEYS
    from so101_teleop.unified.contracts import Domain,OperationSpec
    from so101_teleop.unified.worker_slots import ActWorkerSlot

    if arguments.resume is not False:
        raise ValueError('ACT_CONTAINER_RESUME_FORBIDDEN')
    if (type(arguments.qualification) is not bool or type(arguments.worker_count) is not int
            or arguments.worker_count not in ((1,2,8) if arguments.qualification else (8,))):
        raise ValueError('COLLECTION_WORKER_COUNT_INVALID')
    workload = services.act_workload
    if workload is None:
        raise ValueError(f'ACT_COLLECTION_UNIFIED_SERVICE_UNAVAILABLE: {services.act_error}')
    root = Path(arguments.root)
    config_path = Path(arguments.campaign_config)
    config_digest = _digest(config_path)
    config = load_campaign_config(config_path,expected_sha256=config_digest)
    registered = validate_registered_evidence_root(config['evidence_root'],config['evidence_root'],
                                                  registration=workload.root_registration)
    if (not root.is_absolute() or root.resolve(strict=True) != root or not root.is_dir()
            or root == registered or not root.is_relative_to(registered)
            or not (root/'.campaign-layout.json').is_file()
            or (root/'host/launches.sqlite3').exists() or (root/'campaign-index.json').exists()):
        raise ValueError('COLLECTION_NEW_RUN_REQUIRED')
    campaign_id = arguments.campaign_id
    if type(campaign_id) is not str or re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]*',campaign_id) is None:
        raise ValueError('COLLECTION_CAMPAIGN_ID_INVALID')
    runtime = _collection_runtime(arguments.collection_config)
    if arguments.worker_count > runtime.max_worker_count or arguments.worker_count > len(runtime.ros_domain_ids):
        raise ValueError('COLLECTION_RUNTIME_WORKER_COUNT_INVALID')
    proposal = read_document(arguments.policy)
    fingerprint = proposal.get('policy_fingerprint')
    if type(fingerprint) is not str or re.fullmatch(r'[0-9a-f]{64}',fingerprint) is None:
        raise ValueError('COLLECTION_POLICY_INVALID')
    manifest = read_document(arguments.manifest)
    if arguments.qualification:
        contract = (validate_qualification_contract(manifest) if arguments.worker_count == 8
                    else validate_functional_contract(manifest))
        if contract['worker_count'] != arguments.worker_count or arguments.qualification_contract is not None:
            raise ValueError('COLLECTION_RUN_CONTRACT_MISMATCH')
    elif arguments.qualification_contract is None:
        raise ValueError('EIGHT_WORKER_QUALIFICATION_REQUIRED')
    with workload.arbiter.store._thread_lock:
        generation = workload.arbiter.store.execution_generation(Domain.VALIDATION)+1
    slots = []
    for index,domain in enumerate(runtime.ros_domain_ids[:arguments.worker_count]):
        worker_id = f'w{index:02d}'
        namespace = '/act/campaign_'+campaign_id.replace('-','_')+'/'+worker_id
        slots.append(asdict(ActWorkerSlot(campaign_id,worker_id,generation,domain,namespace,
                                         namespace+'/arm_controller')))
    payload = dict(campaign_id=campaign_id,backend='mujoco',worker_count=arguments.worker_count,
        contact_policy_fingerprint=fingerprint,proposal_path=str(arguments.policy),
        activation_receipt_path=str(arguments.activation_receipt),evidence_root=str(root),
        service_epoch=workload.service_epoch,resource_binding_id=workload.resource_binding_id,
        qualification_mode=arguments.qualification,
        qualification_receipt_path=str(arguments.qualification_contract)
            if arguments.qualification_contract is not None else None,
        worker_slots=slots,registered_evidence_root=str(registered),campaign_config_path=str(config_path),
        campaign_config_sha256=config_digest)
    for name,path in (('source',arguments.source),('manifest',arguments.manifest),
            ('runtime_config',arguments.runtime_config),('collection_config',arguments.collection_config),
            ('calibration_report',arguments.calibration)):
        payload[name+'_path'],payload[name+'_sha256'] = str(path),_digest(path)
    if config['controlled_runtime'] != dict(path=payload['runtime_config_path'],sha256=payload['runtime_config_sha256']):
        raise ValueError('CAMPAIGN_CONFIG_BINDING_MISMATCH')
    if set(payload) != _COLLECTION_PAYLOAD_KEYS:
        raise ValueError('FIXED_COLLECTION_PAYLOAD_SCHEMA_DRIFT')
    return OperationSpec(command_id='collection-'+campaign_id,domain=Domain.VALIDATION,
        kind='act_collection_start',payload=payload,runtime_id=workload.runtime_id,
        execution_generation=generation,
        deadline_ns=workload.clock_ns()+int(runtime.batch_hard_timeout_s*1e9))

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


def _require_payload_schema(payload: dict) -> dict:
    """Fail closed if the payload ever drifts from the key set admission enforces."""

    from so101_teleop.unified.admission import _ACT_PAYLOAD_KEYS

    if set(payload) != set(_ACT_PAYLOAD_KEYS):
        raise ValueError("FIXED_COLLECTION_PAYLOAD_SCHEMA_DRIFT")
    return payload


def build_fixed_collection_spec(*, context, manifest, split_manifest=None, calibration_report,
                                policy, activation_receipt, collection_config, runtime_config,
                                root, qualification: bool, worker_count: int,
                                qualification_contract=None, resume: bool = False) -> dict:
    """Build the spec the unified service admits: a kind plus exactly admission's payload keys.

    The fixed-collection metadata that admission has no key for lives in the evidence root beside the
    campaign index -- which is the convention `--resume` already relies on. The epoch, binding,
    proposal and children come from the admitted context, never from this builder.
    """

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
            kind=kind if kind in ("SINGLE_WORKER", "TWO_WORKER", "EIGHT_WORKER") else "EIGHT_WORKER")
        contract = _json(contract_path)
        require_collection_mode(manifest_kind=contract["kind"], qualification_mode=True)
    else:
        contract = _json(qualification_contract) if qualification_contract is not None else None
        require_collection_mode(manifest_kind=kind, qualification_mode=False, contract=contract)

    if resume:
        if not (_Path(root) / "campaign-index.json").is_file():
            raise ValueError("FIXED_COLLECTION_RESUME_INDEX_MISSING")

    operation = "act_collection_resume" if resume else "act_collection_start"
    payload = {
        "campaign_id": context.campaign_id, "backend": "mujoco", "worker_count": worker_count,
        "source_path": str(context.source_path), "source_sha256": _digest(context.source_path),
        "manifest_path": str(manifest), "manifest_sha256": _digest(manifest),
        "runtime_config_path": str(runtime_config),
        "runtime_config_sha256": _digest(runtime_config),
        "collection_config_path": str(collection_config),
        "collection_config_sha256": _digest(collection_config),
        "contact_policy_fingerprint": context.contact_policy_fingerprint,
        "proposal_path": str(context.proposal_path),
        "activation_receipt_path": str(activation_receipt),
        "evidence_root": str(evidence_root), "service_epoch": context.service_epoch,
        "resource_binding_id": context.resource_binding_id, "qualification_mode": qualification,
        "qualification_receipt_path": (contract_path if qualification else
                                       (str(qualification_contract)
                                        if qualification_contract is not None else None)),
        "children": list(context.children),
        "calibration_report_path": str(calibration_report),
        "calibration_report_sha256": _digest(calibration_report),
    }
    return {"kind": operation, "payload": _require_payload_schema(payload)}
