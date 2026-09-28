"""Task 8P2: the measurement contract is bound to frozen identities before measuring."""

import hashlib
import json
from pathlib import Path

import pytest

from so101_demo.act.task8_measurement_contract import (
    bind_measurement_contract, close_measurement_batch, load_measurement_contract,
)

PACKAGE = Path(__file__).resolve().parents[1]
TEMPLATE = PACKAGE / "config/act/task8-calibration-measurement-contract-v1.json"
ANCHORS = ["default", "left", "forward"]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def identities():
    return {"source_provenance_sha256": "a" * 64, "runtime_config_sha256": "b" * 64,
            "anchors_sha256": _sha(PACKAGE / "config/act/task8-live-anchors.yaml"),
            "contact_policy_fingerprint": "c" * 64, "act_profile_sha256": "d" * 64}


def test_bind_records_every_source_hash_and_refuses_the_unbound_template(tmp_path, identities):
    output = tmp_path / "contract.json"
    bound = bind_measurement_contract(TEMPLATE, identities, output)
    assert bound == output and output.is_file()
    document = load_measurement_contract(output, expected_hashes=identities)
    assert document["identities"] == identities
    assert document["source_hashes"]["template"] == _sha(TEMPLATE)
    with pytest.raises(ValueError):
        load_measurement_contract(TEMPLATE, expected_hashes=identities)   # template is unbound


def test_bind_refuses_to_overwrite_and_rejects_wrong_identity(tmp_path, identities):
    output = tmp_path / "contract.json"
    bind_measurement_contract(TEMPLATE, identities, output)
    with pytest.raises(ValueError):
        bind_measurement_contract(TEMPLATE, identities, output)
    mismatched = dict(identities, runtime_config_sha256="e" * 64)
    with pytest.raises(ValueError, match="MEASUREMENT_CONTRACT_IDENTITY_MISMATCH"):
        load_measurement_contract(output, expected_hashes=mismatched)


def test_bound_contract_carries_the_frozen_thresholds(tmp_path, identities):
    bound = bind_measurement_contract(TEMPLATE, identities, tmp_path / "contract.json")
    document = load_measurement_contract(bound, expected_hashes=identities)
    assert document["thresholds"]["search"]["min_consecutive_lock_frames"] == 3
    assert document["thresholds"]["fov"]["sample_period_s"] == 0.002
    assert document["thresholds"]["collision"]["full_request_budget_ms"] == 25
    assert document["thresholds"]["collision"]["full_request_count"] == 4
    # the contract carries exactly the three frozen anchors, in the template order
    assert document["anchors"] == ANCHORS
    assert sorted(document["anchors"]) == sorted(ANCHORS)


def test_batch_close_is_one_way_and_identity_bound(tmp_path):
    root = tmp_path / "batch"
    identity = {"source_provenance_sha256": "a" * 64, "contract_sha256": "b" * 64,
                "session_id": "s", "reset_epoch": 1, "attempt_id": "attempt-1"}
    sealed = close_measurement_batch(root, identity)
    assert Path(sealed).is_file()
    with pytest.raises(ValueError):
        close_measurement_batch(root, identity)
    document = json.loads(Path(sealed).read_text())
    assert document["identity"] == identity
    assert document["status"] == "CLOSED"
