"""The candidate CLI refuses unsafe or unsupported measurement starts."""

import json
import time
from pathlib import Path

import pytest

from so101_demo.cli.measure_parallel_resources import main


def write(path: Path, document) -> str:
    import hashlib
    path.parent.mkdir(mode=0o700, exist_ok=True)
    path.write_text(json.dumps(document, sort_keys=True))
    path.chmod(0o600)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def config_path():
    return (Path(__file__).resolve().parents[1]
            / "config/mujoco/parallel_batch_v2.yaml")


def authorization_document(tmp_path, **changes):
    document = {
        "schema_version": 2, "operator_uid": __import__("os").getuid(),
        "dispatch_id": "dispatch-a", "task_id": "task-a", "source_commit": "a" * 40,
        "execution_identity_sha256": "b" * 64, "worker_count": 2,
        "catalog_sha256": "c" * 64, "seed": 7, "lifecycle": "FULL_RESTART",
        "maximum_batches": 1, "batch_deadline_s": 5400.0,
        "expires_at_ns": time.time_ns() + 3_600_000_000_000,
        "batch_root": str(tmp_path / "batches"), "owned_scope_sha256": "d" * 64,
        "safety_policy_sha256": "e" * 64, "intent": "CALIBRATION_ONLY",
        "calibration_sha256": None,
    }
    document.update(changes)
    return document


def argv(tmp_path, digest, *, intent="CALIBRATION_ONLY", evidence_root=None):
    return ["--authorization", str(tmp_path / "private/authorization.json"),
            "--authorization-sha256", digest, "--config", str(config_path()),
            "--batch-id", "batch-a", "--evidence-root", str(evidence_root or tmp_path),
            "--intent", intent]


def test_cli_refuses_wrong_hash_and_missing_authorization(tmp_path, capsys):
    assert main(["--authorization", str(tmp_path / "missing.json"),
                 "--authorization-sha256", "f" * 64, "--config", str(config_path()),
                 "--batch-id", "batch-a", "--evidence-root", str(tmp_path),
                 "--intent", "CALIBRATION_ONLY"]) == 1
    assert "REFUSED" in capsys.readouterr().err
    path = tmp_path / "private/authorization.json"
    write(path, authorization_document(tmp_path))
    assert main(argv(tmp_path, "f" * 64)) == 1


def test_cli_refuses_intent_mismatch_and_expiry(tmp_path, capsys):
    path = tmp_path / "private/authorization.json"
    digest = write(path, authorization_document(tmp_path))
    assert main(argv(tmp_path, digest, intent="QUALIFICATION")) == 1
    assert "AUTHORIZATION_INTENT_MISMATCH" in capsys.readouterr().err
    expired = write(path, authorization_document(tmp_path, expires_at_ns=1))
    assert main(argv(tmp_path, expired)) == 1
    assert "AUTHORIZATION_EXPIRED" in capsys.readouterr().err


def test_cli_refuses_candidate_config_with_deployment_refs(tmp_path, capsys):
    document = authorization_document(tmp_path)
    path = tmp_path / "private/authorization.json"
    digest = write(path, document)
    tampered = tmp_path / "config/tampered.yaml"
    tampered.parent.mkdir(mode=0o700, exist_ok=True)
    text = (config_path().read_text()
            .replace("approved_profile_path: null", "approved_profile_path: /sealed/profile.json")
            .replace("approved_profile_sha256: null",
                     "approved_profile_sha256: " + "a" * 64)
            .replace("promotion_record_path: null",
                     "promotion_record_path: /sealed/promotion.json"))
    tampered.write_text(text)
    assert main(["--authorization", str(path), "--authorization-sha256", digest,
                 "--config", str(tampered), "--batch-id", "batch-a",
                 "--evidence-root", str(tmp_path), "--intent", "CALIBRATION_ONLY"]) == 1
    assert "CANDIDATE_CONFIG_MUST_HAVE_NULL_DEPLOYMENT" in capsys.readouterr().err


def test_cli_refuses_batch_root_outside_evidence_root(tmp_path, capsys):
    path = tmp_path / "private/authorization.json"
    digest = write(path, authorization_document(tmp_path, batch_root="/data/elsewhere"))
    assert main(argv(tmp_path, digest)) == 1
    assert "BATCH_ROOT_OUTSIDE_EVIDENCE_ROOT" in capsys.readouterr().err


def test_cli_fails_closed_without_the_owned_runtime(tmp_path, capsys):
    path = tmp_path / "private/authorization.json"
    digest = write(path, authorization_document(tmp_path))
    assert main(argv(tmp_path, digest)) == 1
    stderr = capsys.readouterr().err
    assert "MEASUREMENT_CAPABILITY_MISSING" in stderr or "MEASUREMENT_RUNTIME_UNAVAILABLE" in stderr
