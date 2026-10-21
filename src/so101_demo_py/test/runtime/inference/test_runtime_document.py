"""The runtime document: the run's counts and time limits, outside the campaign identity (campaign config version 2)."""

import hashlib
import json

import pytest

from test_config_identity import campaign_fixture, config_module, write_config
from test_phase_limit_config import KEYS


def write_document(tmp_path, **values):
    path = tmp_path / "runtime-document.json"
    path.write_text(json.dumps({"schema_version": 1, "kind": "ACT_CAMPAIGN_RUNTIME", **values}), encoding="utf-8")
    return path


def test_the_runtime_keys_are_the_nine_the_campaign_config_used_to_carry():
    assert set(config_module().RUNTIME_DOCUMENT_KEYS) == set(KEYS)


@pytest.mark.parametrize("name", sorted(KEYS))
def test_a_runtime_document_accepts_each_key_on_the_same_bounds_as_a_version_1_config(tmp_path, name):
    good, bad_values = KEYS[name]
    assert config_module().load_runtime_document(write_document(tmp_path, **{name: good}))[name] == good
    for bad in bad_values:
        with pytest.raises(ValueError, match="CAMPAIGN_RUNTIME_DOCUMENT_INVALID"):
            config_module().load_runtime_document(write_document(tmp_path, **{name: bad}))


@pytest.mark.parametrize("mutation", [{"extra": 1}, {"kind": "ACT_CONTAINER_CAMPAIGN"}, {"schema_version": 2},
                                      {"max_tasks_in_flight": 4}, {"gpu_uuid": "GPU-x"}])
def test_a_runtime_document_is_closed(tmp_path, mutation):
    path = write_document(tmp_path)
    document = json.loads(path.read_text()) | mutation
    path.write_text(json.dumps(document))
    with pytest.raises(ValueError, match="CAMPAIGN_RUNTIME_DOCUMENT_INVALID"):
        config_module().load_runtime_document(path)


def test_an_empty_runtime_document_is_valid_and_a_missing_one_is_not(tmp_path):
    assert config_module().load_runtime_document(write_document(tmp_path)) == {
        "schema_version": 1, "kind": "ACT_CAMPAIGN_RUNTIME"}
    with pytest.raises(ValueError, match="CAMPAIGN_RUNTIME_DOCUMENT_INVALID"):
        config_module().load_runtime_document(tmp_path / "absent.json")


@pytest.mark.parametrize("name", sorted(KEYS))
def test_a_version_2_campaign_config_refuses_every_runtime_key(tmp_path, name):
    document = campaign_fixture(tmp_path) | {"schema_version": 2}
    assert config_module().load_campaign_config(write_config(tmp_path, document))["schema_version"] == 2
    with pytest.raises(ValueError, match="CAMPAIGN_CONFIG_INVALID"):
        config_module().load_campaign_config(write_config(tmp_path, document | {name: KEYS[name][0]}))


def test_a_version_1_config_with_the_runtime_keys_still_loads(tmp_path):
    document = campaign_fixture(tmp_path) | {name: good for name, (good, _) in KEYS.items()}
    assert config_module().load_campaign_config(write_config(tmp_path, document))["processor_count"] == 4


def test_the_published_schema_refuses_a_runtime_key_in_a_version_2_config(tmp_path):
    import jsonschema
    from paths import PACKAGE_ROOT
    schema = json.loads((PACKAGE_ROOT / "config/act/campaign-runtime-schema.json").read_text())
    document = campaign_fixture(tmp_path)
    jsonschema.validate(document | {"schema_version": 2}, schema)
    jsonschema.validate(document | {"processor_count": 4}, schema)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(document | {"schema_version": 2, "processor_count": 4}, schema)


def test_two_runtime_documents_leave_the_campaign_config_hash_alone(tmp_path):
    config = write_config(tmp_path, campaign_fixture(tmp_path) | {"schema_version": 2})
    before = hashlib.sha256(config.read_bytes()).hexdigest()
    config_module().load_runtime_document(write_document(tmp_path, processor_count=2))
    config_module().load_runtime_document(write_document(tmp_path, processor_count=12))
    assert hashlib.sha256(config.read_bytes()).hexdigest() == before


def test_the_effective_limits_overlay_the_document_and_refuse_a_key_named_twice():
    from so101_demo.runtime.container_campaign.processing_limits import effective_limits, processor_count_for

    config = {"schema_version": 2}
    assert effective_limits(config) is config
    limits = effective_limits(config, {"schema_version": 1, "kind": "ACT_CAMPAIGN_RUNTIME", "processor_count": 3})
    assert limits == {"schema_version": 2, "processor_count": 3}
    assert processor_count_for(limits, queue_length=10, available_bytes=0) == 3
    with pytest.raises(ValueError, match="CAMPAIGN_RUNTIME_KEY_CONFLICT"):
        effective_limits({"processor_count": 6}, {"processor_count": 3})
