"""Import only verifier-approved execute evidence referenced by journal commits."""

from dataclasses import dataclass, fields
import hashlib
import json
from pathlib import Path
from typing import Mapping

from so101_demo.parallel_batch.artifacts import ArtifactError, verify_attempt
from so101_demo.parallel_batch.contracts import AttemptIdentity, ContractError

from .artifacts import (
    ArtifactAccessError, ArtifactManifestEntry, ArtifactView, CampaignBatchBinding,
    SealedArtifactManifest, ValidationArtifactRegistry, _safe_regular,
)
from .coordinator_events import CampaignUpstreamBinding, CoordinatorProjectionError


_ROLES = {
    "initial-rgb.png": "task-rgb-before",
    "terminal-rgb.png": "task-rgb-after",
    "perception/input/rgb.npy": "task-rgb-raw",
    "perception/input/depth.npy": "task-depth-raw",
    "numeric/depth.json": "depth-evidence",
    "numeric/tf.json": "tf-evidence",
    "numeric/physical.json": "physical-evidence",
    "pose_accepted.json": "pose-accepted",
    "dynamic/dynamic-execute-manifest.json": "dynamic-execute",
    "dynamic/consumer-ready.json": "controller-readiness",
    "dynamic/reachability-observed.json": "planning-evidence",
    "attempt-result.json": "attempt-result",
    "workspace_identity.json": "workspace-identity",
    "attempt_result_manifest.json": "sealed-result",
}
_MEDIA = {
    ".json": "application/json", ".png": "image/png",
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".npy": "application/x-npy",
    ".ply": "model/ply", ".log": "text/plain", ".txt": "text/plain",
    ".mp4": "video/mp4",
}


@dataclass(frozen=True, slots=True)
class CommittedAttemptEvidence:
    identity: AttemptIdentity
    status: str
    artifacts: tuple[ArtifactView, ...]


def register_committed_attempt(
    event, binding: CampaignUpstreamBinding, selected_point_ids: tuple[str, ...],
    registry: ValidationArtifactRegistry,
) -> CommittedAttemptEvidence:
    """The journal, not a directory scan or a producer-owned required list, authorizes import."""
    try:
        if event.type != "RESULT_COMMITTED" or binding.owner_kind != "COORDINATOR":
            raise ValueError("COMMITTED_ATTEMPT_REQUIRED")
        raw_identity = event.payload["identity"]
        response = event.payload["response"]
        if not isinstance(raw_identity, Mapping) or not isinstance(response, Mapping):
            raise ValueError("RESULT_REFERENCE_INVALID")
        identity = AttemptIdentity(**{
            field.name: raw_identity[field.name] for field in fields(AttemptIdentity)
        })
        if (identity.batch_id != binding.batch_id
                or identity.point_id not in selected_point_ids
                or identity.coordinator_epoch > event.owner_epoch):
            raise ValueError("RESULT_IDENTITY_MISMATCH")
        sealed = (binding.batch_root / "workers" / identity.worker_id / "attempts"
                  / identity.point_id / identity.attempt_id / "sealed")
        location = response["location"]
        if not isinstance(location, str) or Path(location) != sealed:
            raise ValueError("RESULT_IDENTITY_MISMATCH")
        if raw_identity.get("location") != location:
            raise ValueError("RESULT_IDENTITY_MISMATCH")
        manifest_path = _safe_regular(sealed / "attempt_result_manifest.json", binding.batch_root)
        payload = manifest_path.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        if response["sha256"] != digest:
            raise ValueError("RESULT_REFERENCE_HASH_MISMATCH")
        manifest = json.loads(payload)
        # This verifies the whole inventory and mode-specific physical/dynamic semantics.
        # Do not replace it with just a manifest hash or trust producer.required.
        verify_attempt(sealed, identity)
        status = manifest["status"]
        if response["status"] != status:
            raise ValueError("RESULT_STATUS_MISMATCH")
        entries = []
        for item in (*manifest["files"], {
            "relative_path": "attempt_result_manifest.json", "size": len(payload),
            "sha256": digest,
        }):
            relative = item["relative_path"]
            path = sealed / relative
            entries.append(ArtifactManifestEntry(
                relative_path=path.relative_to(binding.batch_root).as_posix(),
                role=_ROLES.get(relative, f"evidence-{Path(relative).stem}"),
                media_type=_MEDIA.get(path.suffix.lower(), "application/octet-stream"),
                size_bytes=item["size"], sha256=item["sha256"],
            ))
        views = registry.register_manifest(SealedArtifactManifest(
            manifest_id=f"commit-{event.sequence}", manifest_sha256=digest,
            campaign_id=binding.campaign_id, batch_id=binding.batch_id,
            pool_generation=None, worker_id=identity.worker_id,
            worker_generation=identity.worker_generation, attempt_id=identity.attempt_id,
            committed=True, entries=tuple(entries),
        ), CampaignBatchBinding(
            campaign_id=binding.campaign_id, batch_id=binding.batch_id,
            batch_root=binding.batch_root, owner_kind="COORDINATOR",
            current_pool_generation=None, accepted_manifest_sha256s=frozenset({digest}),
        ))
        return CommittedAttemptEvidence(identity, status, views)
    except (KeyError, TypeError, ValueError, OSError, ArtifactError, ContractError,
            ArtifactAccessError) as error:
        raise CoordinatorProjectionError("COMMITTED_ATTEMPT_EVIDENCE_INVALID") from error
