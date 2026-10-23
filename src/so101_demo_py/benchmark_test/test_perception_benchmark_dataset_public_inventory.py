"""The public inventory loaders and the inventory capability."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

from perception_benchmark_dataset_support import (
    _public_inventory_anchors,
    _skip_what_needs_the_pinned_rasterizer,  # noqa: F401  (pytest fixtures)
    _verified_unlocked_seal,
    build_fixture_archive,
)
import pytest

from so101_demo.perception_benchmark.dataset import archive as dataset_module_archive
from so101_demo.perception_benchmark.dataset import loading as dataset_module_loading
from so101_demo.perception_benchmark.dataset import pinned_files as dataset_module_pinned_files
from so101_demo.perception_benchmark.dataset import truth as dataset_module_truth
from so101_demo.perception_benchmark.dataset import verifier as dataset_module_verifier
from so101_demo.perception_benchmark.dataset.contracts import DatasetVerificationError, sha256_file
from so101_demo.perception_benchmark.dataset.loading import (
    load_dataset_inventory,
    load_truth_samples,
)
from so101_demo.perception_benchmark.dataset.verifier import DatasetArchiveVerifier


def _rewrite_inventory_document(root: Path, document: dict[str, object]) -> None:
    payload = (
        json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode("utf-8")
    (root / "inventory.json").chmod(0o644)
    (root / "inventory.json").write_bytes(payload)
    (root / "inventory.sha256").chmod(0o644)
    (root / "inventory.sha256").write_text(
        f"{hashlib.sha256(payload).hexdigest()}  inventory.json\n",
        encoding="ascii",
    )


def test_public_inventory_loader_reconstructs_and_reissues_verified_capability(
    tmp_path: Path,
) -> None:
    archive = build_fixture_archive(tmp_path, include_val=True)
    root = tmp_path / "val-open"
    DatasetArchiveVerifier().verify_and_extract_split(
        archive, sha256_file(archive), root, "val", None
    )

    inventory = load_dataset_inventory(root, **_public_inventory_anchors(root, "val"))

    assert inventory.dataset_root == root.resolve(strict=True)
    assert inventory.sample_count == 200
    assert inventory.scenario_counts == {
        "no_cup": 50,
        "one_cup_distractors": 50,
        "two_cups": 50,
        "cup_near_bottle": 50,
    }
    assert len(inventory.samples) == 200
    assert inventory._capability is not None
    assert b"capability" not in (root / "inventory.json").read_bytes()


@pytest.mark.parametrize(
    "mutation",
    (
        "extra-top-level",
        "missing-top-level",
        "extra-sample-field",
        "missing-sample-field",
        "path-escape",
        "wrong-split",
        "wrong-rasterizer",
        "wrong-count",
    ),
)
def test_public_inventory_loader_rejects_schema_or_sample_relaxation(
    tmp_path: Path, mutation: str
) -> None:
    archive = build_fixture_archive(tmp_path, include_val=True)
    root = tmp_path / "val-open"
    DatasetArchiveVerifier().verify_and_extract_split(
        archive, sha256_file(archive), root, "val", None
    )
    anchors = _public_inventory_anchors(root, "val")
    document = json.loads((root / "inventory.json").read_bytes())
    if mutation == "extra-top-level":
        document["extra"] = "forbidden"
    elif mutation == "missing-top-level":
        del document["archive_sha256"]
    elif mutation == "extra-sample-field":
        document["samples"][0]["extra"] = "forbidden"
    elif mutation == "missing-sample-field":
        del document["samples"][0]["truth_sha256"]
    elif mutation == "path-escape":
        document["samples"][0]["image_relpath"] = "../escape.png"
    elif mutation == "wrong-split":
        document["split"] = "training"
    elif mutation == "wrong-rasterizer":
        document["rasterizer"]["version"] = "0"
    else:
        document["sample_count"] = 199
    _rewrite_inventory_document(root, document)

    with pytest.raises(DatasetVerificationError):
        load_dataset_inventory(root, **anchors)


def test_public_inventory_loader_rejects_noncanonical_sidecar_tamper_and_symlink(
    tmp_path: Path,
) -> None:
    archive = build_fixture_archive(tmp_path, include_val=True)
    root = tmp_path / "val-open"
    DatasetArchiveVerifier().verify_and_extract_split(
        archive, sha256_file(archive), root, "val", None
    )
    anchors = _public_inventory_anchors(root, "val")
    canonical = (root / "inventory.json").read_bytes()
    (root / "inventory.json").chmod(0o644)
    (root / "inventory.json").write_bytes(canonical[:-1] + b" \n")
    with pytest.raises(DatasetVerificationError):
        load_dataset_inventory(root, **anchors)

    (root / "inventory.json").write_bytes(canonical)
    (root / "inventory.sha256").chmod(0o644)
    (root / "inventory.sha256").write_text("0" * 64 + "  inventory.json\n")
    with pytest.raises(DatasetVerificationError):
        load_dataset_inventory(root, **anchors)

    (root / "inventory.sha256").write_text(
        f"{hashlib.sha256(canonical).hexdigest()}  inventory.json\n"
    )
    linked = tmp_path / "linked-dataset"
    linked.symlink_to(root, target_is_directory=True)
    with pytest.raises(DatasetVerificationError):
        load_dataset_inventory(linked, **anchors)


def test_public_inventory_loader_rechecks_current_bytes_and_semantics(
    tmp_path: Path,
) -> None:
    archive = build_fixture_archive(tmp_path, include_val=True)
    root = tmp_path / "val-open"
    DatasetArchiveVerifier().verify_and_extract_split(
        archive, sha256_file(archive), root, "val", None
    )
    anchors = _public_inventory_anchors(root, "val")
    document = json.loads((root / "inventory.json").read_bytes())
    first = document["samples"][0]
    label_path = root / first["label_relpath"]
    label_path.chmod(0o644)
    label_path.write_text("0 0.1 0.1 0.2 0.1 0.15 0.2\n", encoding="utf-8")
    first["label_sha256"] = hashlib.sha256(label_path.read_bytes()).hexdigest()
    _rewrite_inventory_document(root, document)
    anchors["expected_inventory_sha256"] = hashlib.sha256(
        (root / "inventory.json").read_bytes()
    ).hexdigest()

    with pytest.raises(DatasetVerificationError, match="LABEL_TRUTH_POLYGON_MISMATCH"):
        load_dataset_inventory(root, **anchors)


def test_public_inventory_loader_binds_loaded_object_to_original_tree(
    tmp_path: Path,
) -> None:
    archive = build_fixture_archive(tmp_path, include_val=True)
    original = tmp_path / "val-open"
    DatasetArchiveVerifier().verify_and_extract_split(
        archive, sha256_file(archive), original, "val", None
    )
    inventory = load_dataset_inventory(original, **_public_inventory_anchors(original, "val"))
    moved = tmp_path / "moved-val-open"
    original.rename(moved)

    with pytest.raises(DatasetVerificationError):
        load_truth_samples(moved, "val", inventory)


def test_public_test_inventory_loader_rejects_changed_access_or_lock_chain(
    tmp_path: Path,
) -> None:
    archive = build_fixture_archive(tmp_path)
    seal = _verified_unlocked_seal(archive, tmp_path)
    root = tmp_path / "test-open"
    DatasetArchiveVerifier().verify_and_extract_split(
        archive, sha256_file(archive), root, "test", seal
    )
    assert seal.access_grant is not None
    anchors = _public_inventory_anchors(root, "test")
    access_log = seal.access_log_path
    access_log.write_bytes(access_log.read_bytes() + b"{}\n")

    with pytest.raises(DatasetVerificationError, match="INVENTORY_ACCESS_CHAIN_INVALID"):
        load_dataset_inventory(root, **anchors)

    access_log.write_bytes(access_log.read_bytes()[:-3])
    document = json.loads((root / "inventory.json").read_bytes())
    document["test_access"]["threshold_lock_sha256s"][0] = "d" * 64
    _rewrite_inventory_document(root, document)
    with pytest.raises(DatasetVerificationError, match="INVENTORY_EXTERNAL_ANCHOR_MISMATCH"):
        load_dataset_inventory(root, **anchors)


def test_public_test_inventory_loader_accepts_explicit_relocated_access_log(
    tmp_path: Path,
) -> None:
    archive = build_fixture_archive(tmp_path)
    seal = _verified_unlocked_seal(archive, tmp_path)
    producer_root = tmp_path / "producer-test-open"
    DatasetArchiveVerifier().verify_and_extract_split(
        archive, sha256_file(archive), producer_root, "test", seal
    )
    relocated_root = tmp_path / "relocated-test-open"
    shutil.copytree(producer_root, relocated_root)
    relocated_access_log = tmp_path / "relocated-test-access.jsonl"
    shutil.copy2(seal.access_log_path, relocated_access_log)
    seal.access_log_path.rename(tmp_path / "producer-access-log-moved.jsonl")

    inventory = load_dataset_inventory(
        relocated_root,
        **_public_inventory_anchors(relocated_root, "test"),
        expected_access_log_path=relocated_access_log,
    )

    assert len(load_truth_samples(relocated_root, "test", inventory)) == 200
    relocated_access_log.write_bytes(relocated_access_log.read_bytes() + b"{}\n")
    with pytest.raises(DatasetVerificationError, match="INVENTORY_ACCESS_CHAIN_INVALID"):
        load_truth_samples(relocated_root, "test", inventory)


def test_round1_public_inventory_loader_requires_all_external_val_anchors(
    tmp_path: Path,
) -> None:
    archive = build_fixture_archive(tmp_path, include_val=True)
    root = tmp_path / "val-open"
    DatasetArchiveVerifier().verify_and_extract_split(
        archive, sha256_file(archive), root, "val", None
    )

    with pytest.raises(TypeError):
        load_dataset_inventory(root)


def test_round1_public_inventory_loader_rejects_coherent_self_attested_rewrite_before_issuance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = build_fixture_archive(tmp_path)
    seal = _verified_unlocked_seal(archive, tmp_path)
    root = tmp_path / "test-open"
    DatasetArchiveVerifier().verify_and_extract_split(
        archive, sha256_file(archive), root, "test", seal
    )
    assert seal.access_grant is not None
    original_inventory_sha = hashlib.sha256((root / "inventory.json").read_bytes()).hexdigest()
    document = json.loads((root / "inventory.json").read_bytes())
    original_archive_sha = document["archive_sha256"]
    original_event_sha = document["test_access"]["event_sha256"]
    original_sealed_sha = document["test_access"]["sealed_member_inventory_sha256"]
    original_locks = tuple(document["test_access"]["threshold_lock_sha256s"])
    document["archive_sha256"] = "d" * 64
    document["test_access"]["sealed_member_inventory_sha256"] = "e" * 64
    document["test_access"]["threshold_lock_sha256s"] = ["f" * 64, "9" * 64]
    event_without_sha = {
        "event_type": "TEST_ACCESS_GRANTED",
        "granted_at": document["test_access"]["granted_at"],
        "sealed_member_inventory_sha256": "e" * 64,
        "threshold_lock_sha256s": ["f" * 64, "9" * 64],
    }
    rewritten_event_sha = hashlib.sha256(
        dataset_module_archive.canonical_json_bytes(event_without_sha)
    ).hexdigest()
    document["test_access"]["event_sha256"] = rewritten_event_sha
    seal.access_log_path.write_bytes(
        dataset_module_archive.canonical_json_bytes(
            {**event_without_sha, "event_sha256": rewritten_event_sha}
        )
    )
    _rewrite_inventory_document(root, document)

    def forbidden_issue(inventory: object) -> None:
        raise RuntimeError("capability issued before external anchors verified")

    monkeypatch.setattr(dataset_module_loading, "_issue_inventory", forbidden_issue)
    monkeypatch.setattr(dataset_module_verifier, "_issue_inventory", forbidden_issue)
    with pytest.raises(DatasetVerificationError, match="INVENTORY_EXTERNAL_ANCHOR_MISMATCH"):
        load_dataset_inventory(
            root,
            expected_split="test",
            expected_archive_sha256=original_archive_sha,
            expected_inventory_sha256=original_inventory_sha,
            expected_test_access_event_sha256=original_event_sha,
            expected_sealed_member_inventory_sha256=original_sealed_sha,
            expected_threshold_lock_sha256s=original_locks,
        )


def test_round1_public_val_inventory_rejects_test_access_anchors(
    tmp_path: Path,
) -> None:
    archive = build_fixture_archive(tmp_path, include_val=True)
    root = tmp_path / "val-open"
    DatasetArchiveVerifier().verify_and_extract_split(
        archive, sha256_file(archive), root, "val", None
    )
    inventory_payload = (root / "inventory.json").read_bytes()

    with pytest.raises(DatasetVerificationError, match="VAL_EXTERNAL_TEST_ANCHOR_CONFLICT"):
        load_dataset_inventory(
            root,
            expected_split="val",
            expected_archive_sha256=sha256_file(archive),
            expected_inventory_sha256=hashlib.sha256(inventory_payload).hexdigest(),
            expected_test_access_event_sha256="a" * 64,
            expected_sealed_member_inventory_sha256="b" * 64,
            expected_threshold_lock_sha256s=("c" * 64, "d" * 64),
            expected_access_log_path=tmp_path / "test-access.jsonl",
        )


@pytest.mark.parametrize(
    "mutation",
    ("extra-file", "extra-dir", "symlink", "special", "unknown-split", "hardlink"),
)
def test_round1_public_inventory_loader_rejects_every_unreferenced_tree_entry(
    tmp_path: Path, mutation: str
) -> None:
    archive = build_fixture_archive(tmp_path, include_val=True)
    root = tmp_path / "val-open"
    DatasetArchiveVerifier().verify_and_extract_split(
        archive, sha256_file(archive), root, "val", None
    )
    inventory_payload = (root / "inventory.json").read_bytes()
    if mutation == "extra-file":
        (root / "extra.txt").write_text("extra\n", encoding="utf-8")
    elif mutation == "extra-dir":
        (root / "extra").mkdir()
    elif mutation == "symlink":
        (root / "extra-link").symlink_to(root / "inventory.json")
    elif mutation == "special":
        os.mkfifo(root / "extra.fifo")
    elif mutation == "unknown-split":
        (root / "images/test").mkdir()
    else:
        os.link(root / "inventory.json", tmp_path / "external-inventory.json")

    with pytest.raises(DatasetVerificationError, match="INVENTORY_TREE_MISMATCH"):
        load_dataset_inventory(
            root,
            expected_split="val",
            expected_archive_sha256=sha256_file(archive),
            expected_inventory_sha256=hashlib.sha256(inventory_payload).hexdigest(),
        )


@pytest.mark.skipif(not hasattr(os, "fork"), reason="fork is unavailable")
def test_round1_inventory_capability_is_invalidated_across_fork_until_public_reload(
    tmp_path: Path,
) -> None:
    archive = build_fixture_archive(tmp_path, include_val=True)
    root = tmp_path / "val-open"
    inventory = DatasetArchiveVerifier().verify_and_extract_split(
        archive, sha256_file(archive), root, "val", None
    )
    inventory_sha = hashlib.sha256((root / "inventory.json").read_bytes()).hexdigest()
    read_fd, write_fd = os.pipe()
    child_pid = os.fork()
    if child_pid == 0:
        os.close(read_fd)
        outcome = b"ok"
        try:
            with pytest.raises(DatasetVerificationError, match="INVENTORY_CAPABILITY_INVALID"):
                dataset_module_truth._require_inventory_capability(inventory)
            reloaded = load_dataset_inventory(
                root,
                expected_split="val",
                expected_archive_sha256=sha256_file(archive),
                expected_inventory_sha256=inventory_sha,
            )
            dataset_module_truth._require_inventory_capability(reloaded)
        except BaseException as error:
            outcome = f"error:{type(error).__name__}:{error}".encode()
        os.write(write_fd, outcome)
        os.close(write_fd)
        os._exit(0)
    os.close(write_fd)
    outcome = os.read(read_fd, 4096)
    os.close(read_fd)
    _, status = os.waitpid(child_pid, 0)

    dataset_module_truth._require_inventory_capability(inventory)
    assert os.waitstatus_to_exitcode(status) == 0
    assert outcome == b"ok"


@pytest.mark.parametrize(
    "alias_base",
    (Path("/tmp"), Path(tempfile.gettempdir())),
    ids=("tmp-alias", "default-var-alias"),
)
def test_round2_public_dataset_loader_accepts_macos_system_ancestor_aliases(
    alias_base: Path,
) -> None:
    with tempfile.TemporaryDirectory(prefix="so101-public-dataset-", dir=alias_base) as temporary:
        workspace = Path(temporary)
        archive = build_fixture_archive(workspace, include_val=True)
        root = workspace / "val-open"
        DatasetArchiveVerifier().verify_and_extract_split(
            archive, sha256_file(archive), root, "val", None
        )

        loaded = load_dataset_inventory(root, **_public_inventory_anchors(root, "val"))

        assert loaded.dataset_root == root.resolve(strict=True)
        dataset_module_truth._require_inventory_capability(loaded)


def test_round2_pinned_reader_rejects_descendant_modified_during_same_fd_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "pinned"
    root.mkdir()
    target = root / "payload.bin"
    target.write_bytes(b"stable payload")
    real_read = os.read
    modified = False

    def mutate_after_read(descriptor: int, count: int) -> bytes:
        nonlocal modified
        payload = real_read(descriptor, count)
        if payload and not modified:
            modified = True
            target.write_bytes(payload + b" drift")
        return payload

    monkeypatch.setattr(os, "read", mutate_after_read)
    with dataset_module_pinned_files._PinnedDirectory.open(root) as pinned:
        with pytest.raises(ValueError, match="changed during pinned read"):
            pinned.read_file("payload.bin")


def test_round2_public_dataset_loader_accepts_complete_derived_truth_tree_and_reuses_it(
    tmp_path: Path,
) -> None:
    archive = build_fixture_archive(tmp_path, include_val=True)
    root = tmp_path / "val-open"
    inventory = DatasetArchiveVerifier().verify_and_extract_split(
        archive, sha256_file(archive), root, "val", None
    )
    anchors = _public_inventory_anchors(root, "val")
    first_truths = load_truth_samples(root, "val", inventory)

    reloaded = load_dataset_inventory(root, **anchors)
    second_truths = load_truth_samples(root, "val", reloaded)

    assert second_truths == first_truths
    dataset_module_truth._require_inventory_capability(reloaded)


@pytest.mark.parametrize(
    "mutation",
    ("partial", "missing", "extra", "wrong-split", "symlink", "hardlink", "tamper"),
)
def test_round2_public_dataset_loader_rejects_incomplete_or_tampered_truth_mask_tree(
    tmp_path: Path, mutation: str
) -> None:
    archive = build_fixture_archive(tmp_path, include_val=True)
    root = tmp_path / "val-open"
    inventory = DatasetArchiveVerifier().verify_and_extract_split(
        archive, sha256_file(archive), root, "val", None
    )
    anchors = _public_inventory_anchors(root, "val")
    load_truth_samples(root, "val", inventory)
    mask_root = root / "truth_masks/val"
    mask_paths = sorted(mask_root.iterdir())
    first_mask = mask_paths[0]
    if mutation == "partial":
        first_mask.unlink()
    elif mutation == "missing":
        mask_root.rename(tmp_path / "removed-val-masks")
    elif mutation == "extra":
        (mask_root / "extra.json").write_text("{}\n", encoding="utf-8")
    elif mutation == "wrong-split":
        mask_root.rename(mask_root.parent / "test")
    elif mutation == "symlink":
        outside = tmp_path / "outside-mask.json"
        outside.write_bytes(first_mask.read_bytes())
        first_mask.unlink()
        first_mask.symlink_to(outside)
    elif mutation == "hardlink":
        os.link(first_mask, tmp_path / "external-mask.json")
    else:
        first_mask.chmod(0o644)
        first_mask.write_bytes(first_mask.read_bytes() + b"tamper")

    with pytest.raises(DatasetVerificationError, match="INVENTORY_TREE_MISMATCH"):
        load_dataset_inventory(root, **anchors)
