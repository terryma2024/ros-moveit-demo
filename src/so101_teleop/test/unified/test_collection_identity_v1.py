"""The v1 controlled identity of a container collection start: pinned before the v2 changes.

A v1 campaign config keeps its identity after the logic/runtime split: the runtime-class keys are in the file hash but not in
the controlled identity, `gpu_uuid` and the images are, and the rig profile is only when named.
"""

import sys

from teleop_paths import DEMO_TEST_IMPORT_PATH

for _candidate in DEMO_TEST_IMPORT_PATH:
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

from test_config_identity import campaign_fixture
from so101_teleop.unified.admission import _collection_identity

PAYLOAD = dict(source_sha256="1" * 64, runtime_config_sha256="2" * 64, collection_config_sha256="3" * 64,
               contact_policy_fingerprint="4" * 64)
RUNTIME_KEYS = dict(processor_count=6, processing_max_attempts=3, processing_reserve_s=1800, collect_timeout_s=3000,
                    process_timeout_s=2000, verification_reserve_s=600, batch_hard_timeout_s=9000,
                    processing_task_timeout_s=1800, retry_invalid_max_rounds=2, max_concurrent_recordings=4,
                    max_tasks_in_flight=4, min_assignment_gap_s=1.0)


def test_v1_identity_has_the_six_keys_with_the_gpu_and_the_images(tmp_path):
    config = campaign_fixture(tmp_path)
    identity = _collection_identity(PAYLOAD, config)
    assert set(identity) == {*PAYLOAD, "gpu_uuid", "image_source_install"}
    assert identity["gpu_uuid"] == config["gpu_uuid"]
    assert identity["image_source_install"] == dict(inference=config["teacher_service"]["image"],
                                                    shard=config["shard_image"])


def test_v1_identity_ignores_every_runtime_class_key(tmp_path):
    config = campaign_fixture(tmp_path)
    assert _collection_identity(PAYLOAD, config | RUNTIME_KEYS) == _collection_identity(PAYLOAD, config)


def test_v1_identity_names_the_rig_profile_only_when_the_config_does(tmp_path):
    config = campaign_fixture(tmp_path)
    assert "rig_profile_sha256" not in _collection_identity(PAYLOAD, config)
    assert _collection_identity(PAYLOAD, config | dict(rig_profile_sha256="5" * 64))["rig_profile_sha256"] == "5" * 64


def test_a_version_2_config_has_the_identity_without_the_gpu(tmp_path):
    config = campaign_fixture(tmp_path) | {"schema_version": 2}
    identity = _collection_identity(PAYLOAD, config)
    assert set(identity) == {*PAYLOAD, "image_source_install"}
    assert _collection_identity(PAYLOAD, config | {"gpu_uuid": "GPU-other"}) == identity      # another GPU, the same identity
