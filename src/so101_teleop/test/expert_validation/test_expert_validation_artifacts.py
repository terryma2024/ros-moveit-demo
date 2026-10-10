import hashlib

import pytest

from so101_teleop.expert_validation.artifacts import (
    ArtifactAccessError,
    ArtifactManifestEntry,
    CampaignBatchBinding,
    SealedArtifactManifest,
    ValidationArtifactRegistry,
)


def _entry(root, relative="worker/result.json", payload=b"result", **changes):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    values = dict(
        relative_path=relative,
        role="attempt-result",
        media_type="application/json",
        size_bytes=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
    )
    values.update(changes)
    return ArtifactManifestEntry(**values)


def _manifest(root, entry, **changes):
    values = dict(
        manifest_id="manifest-1",
        manifest_sha256="a" * 64,
        campaign_id="campaign-1",
        batch_id="batch-1",
        pool_generation=2,
        worker_id="worker-1",
        worker_generation=3,
        attempt_id="attempt-1",
        committed=True,
        entries=(entry,),
    )
    values.update(changes)
    return SealedArtifactManifest(**values)


def _binding(root, **changes):
    values = dict(
        campaign_id="campaign-1",
        batch_id="batch-1",
        batch_root=root.resolve(),
        owner_kind="ADAPTIVE_RUNNER",
        current_pool_generation=2,
        accepted_manifest_sha256s=frozenset({"a" * 64}),
    )
    values.update(changes)
    return CampaignBatchBinding(**values)


def test_registered_artifact_is_checksum_verified_and_readable(tmp_path):
    root = (tmp_path / "batch").resolve()
    entry = _entry(root)
    registry = ValidationArtifactRegistry()
    view = registry.register_manifest(_manifest(root, entry), _binding(root))[0]

    verified = registry.resolve_opaque_id(
        view.artifact_id,
        expected_campaign_id="campaign-1",
        expected_batch_id="batch-1",
        expected_worker_id="worker-1",
        expected_attempt_id="attempt-1",
    )
    assert verified.read_bytes() == b"result"
    assert view.role == "attempt-result"


def test_artifact_cannot_escape_bound_batch_root(tmp_path):
    root = (tmp_path / "batch").resolve()
    foreign = tmp_path / "foreign.json"
    foreign.write_bytes(b"foreign")
    entry = ArtifactManifestEntry(
        relative_path=str(foreign.resolve()),
        role="attempt-result",
        media_type="application/json",
        size_bytes=7,
        sha256=hashlib.sha256(b"foreign").hexdigest(),
    )
    with pytest.raises(ArtifactAccessError, match="ARTIFACT_PATH_INVALID"):
        ValidationArtifactRegistry().register_manifest(
            _manifest(root, entry), _binding(root)
        )


@pytest.mark.parametrize("relative", ["../foreign", "worker/../../foreign", ""])
def test_relative_path_traversal_is_rejected(tmp_path, relative):
    root = (tmp_path / "batch").resolve()
    entry = ArtifactManifestEntry(
        relative_path=relative,
        role="attempt-result",
        media_type="application/json",
        size_bytes=1,
        sha256="0" * 64,
    )
    with pytest.raises(ArtifactAccessError, match="ARTIFACT_PATH_INVALID"):
        ValidationArtifactRegistry().register_manifest(
            _manifest(root, entry), _binding(root)
        )


def test_worker_artifact_cannot_be_claimed_by_another_attempt(tmp_path):
    root = (tmp_path / "batch").resolve()
    registry = ValidationArtifactRegistry()
    artifact = registry.register_manifest(
        _manifest(root, _entry(root)), _binding(root)
    )[0]
    with pytest.raises(ArtifactAccessError, match="ARTIFACT_IDENTITY_MISMATCH"):
        registry.resolve_opaque_id(
            artifact.artifact_id,
            expected_attempt_id="attempt-2",
        )


def test_cross_campaign_batch_and_worker_are_rejected_on_resolve(tmp_path):
    root = (tmp_path / "batch").resolve()
    registry = ValidationArtifactRegistry()
    artifact = registry.register_manifest(
        _manifest(root, _entry(root)), _binding(root)
    )[0]
    for expected in (
        {"expected_campaign_id": "campaign-2"},
        {"expected_batch_id": "batch-2"},
        {"expected_worker_id": "worker-2"},
    ):
        with pytest.raises(ArtifactAccessError, match="ARTIFACT_IDENTITY_MISMATCH"):
            registry.resolve_opaque_id(artifact.artifact_id, **expected)


def test_unaccepted_uncommitted_and_old_generation_manifests_fail_closed(tmp_path):
    root = (tmp_path / "batch").resolve()
    entry = _entry(root)
    registry = ValidationArtifactRegistry()
    with pytest.raises(ArtifactAccessError, match="MANIFEST_NOT_ACCEPTED"):
        registry.register_manifest(
            _manifest(root, entry, manifest_sha256="b" * 64), _binding(root)
        )
    with pytest.raises(ArtifactAccessError, match="RESULT_NOT_COMMITTED"):
        registry.register_manifest(_manifest(root, entry, committed=False), _binding(root))
    with pytest.raises(ArtifactAccessError, match="POOL_GENERATION_MISMATCH"):
        registry.register_manifest(
            _manifest(root, entry, pool_generation=1), _binding(root)
        )


def test_symlink_checksum_and_media_type_are_rejected(tmp_path):
    root = (tmp_path / "batch").resolve()
    target = tmp_path / "target.json"
    target.write_bytes(b"result")
    link = root / "worker/result.json"
    link.parent.mkdir(parents=True)
    link.symlink_to(target)
    entry = ArtifactManifestEntry(
        "worker/result.json", "attempt-result", "application/json", 6,
        hashlib.sha256(b"result").hexdigest()
    )
    with pytest.raises(ArtifactAccessError, match="ARTIFACT_PATH_INVALID"):
        ValidationArtifactRegistry().register_manifest(
            _manifest(root, entry), _binding(root)
        )

    link.unlink()
    link.write_bytes(b"drift")
    with pytest.raises(ArtifactAccessError, match="ARTIFACT_CHECKSUM_MISMATCH"):
        ValidationArtifactRegistry().register_manifest(
            _manifest(root, entry), _binding(root)
        )
    bad_media = ArtifactManifestEntry(
        "worker/result.json", "attempt-result", "application/x-dangerous", 5,
        hashlib.sha256(b"drift").hexdigest()
    )
    with pytest.raises(ArtifactAccessError, match="ARTIFACT_MEDIA_TYPE"):
        ValidationArtifactRegistry().register_manifest(
            _manifest(root, bad_media), _binding(root)
        )


def test_shared_broker_and_recovery_roles_preserve_identity(tmp_path):
    root = (tmp_path / "batch").resolve()
    broker_entry = _entry(
        root, "broker/diagnostics.json", b"broker", role="broker-diagnostics"
    )
    recovery_entry = _entry(
        root, "worker/recovery.json", b"recover", role="worker-recovery"
    )
    registry = ValidationArtifactRegistry()
    broker = registry.register_manifest(
        _manifest(
            root,
            broker_entry,
            manifest_id="broker-manifest",
            worker_id=None,
            worker_generation=None,
            attempt_id=None,
        ),
        _binding(root),
    )[0]
    recovery = registry.register_manifest(
        _manifest(root, recovery_entry, manifest_id="recovery-manifest"),
        _binding(root),
    )[0]
    assert broker.worker_id is None
    assert broker.role == "broker-diagnostics"
    assert recovery.role == "worker-recovery"
