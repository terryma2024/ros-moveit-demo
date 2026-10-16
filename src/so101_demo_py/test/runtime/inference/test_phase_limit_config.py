"""The phase-2 and time-limit keys of the campaign config: optional, validated like the other limits, hashed, and in the schema."""

import hashlib
import json

import pytest

from test_config_identity import campaign_fixture, config_module, write_config

KEYS = {
    "processor_count": (4, [0, 17, -1, True, 4.0, "4", None]),
    "processing_max_attempts": (3, [0, 6, -1, True, 3.0, "3", None]),
    "processing_reserve_s": (1800, [0, -5, True, 1800.5, "1800", None]),
    "collect_timeout_s": (3000, [0, -1, True, 3000.5, "3000", None]),
    "process_timeout_s": (2000, [0, -1, True, 2000.5, "2000", None]),
    "verification_reserve_s": (600, [0, -1, True, 600.5, "600", None]),
    "batch_hard_timeout_s": (9000, [1799, 14401, 0, -1, True, "9000", None]),
    "processing_task_timeout_s": (1800, [1259, 0, -1, True, 1800.5, "1800", None]),
}


@pytest.mark.parametrize("name", sorted(KEYS))
def test_each_key_is_optional_validated_and_part_of_the_campaign_hash(tmp_path, name):
    good, bad_values = KEYS[name]
    document = campaign_fixture(tmp_path)
    plain = write_config(tmp_path, document)
    assert name not in config_module().load_campaign_config(plain)
    plain_hash = hashlib.sha256(plain.read_bytes()).hexdigest()
    limited = write_config(tmp_path, document | {name: good})
    assert config_module().load_campaign_config(limited)[name] == good
    assert hashlib.sha256(limited.read_bytes()).hexdigest() != plain_hash
    for bad in bad_values:
        with pytest.raises(ValueError, match="CAMPAIGN_CONFIG_INVALID"):
            config_module().load_campaign_config(write_config(tmp_path, document | {name: bad}))


@pytest.mark.parametrize("name", sorted(KEYS))
def test_the_published_schema_accepts_only_a_valid_value(tmp_path, name):
    import jsonschema
    from paths import PACKAGE_ROOT
    schema = json.loads((PACKAGE_ROOT / "config/act/campaign-runtime-schema.json").read_text())
    document = campaign_fixture(tmp_path)
    good, bad_values = KEYS[name]
    jsonschema.validate(document | {name: good}, schema)
    for bad in bad_values:
        if bad is None or (type(bad) is float and bad == int(bad)):
            continue   # JSON Schema integers include 4.0; the loader's `type is int` check is the stricter one
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(document | {name: bad}, schema)


def test_batch_hard_timeout_accepts_a_number_on_its_closed_bounds(tmp_path):
    from paths import PACKAGE_ROOT
    import jsonschema
    schema = json.loads((PACKAGE_ROOT / "config/act/campaign-runtime-schema.json").read_text())
    document = campaign_fixture(tmp_path)
    module = config_module()
    assert (module.BATCH_HARD_TIMEOUT_MIN_S, module.BATCH_HARD_TIMEOUT_MAX_S) == (1800, 14400)
    for good in (1800, 1800.5, 9000.25, 14400, 14400.0):
        loaded = module.load_campaign_config(write_config(tmp_path, document | {"batch_hard_timeout_s": good}))
        assert loaded["batch_hard_timeout_s"] == good
        jsonschema.validate(document | {"batch_hard_timeout_s": good}, schema)
    for bad in (1799.9, 14400.1):
        with pytest.raises(ValueError, match="CAMPAIGN_CONFIG_INVALID"):
            module.load_campaign_config(write_config(tmp_path, document | {"batch_hard_timeout_s": bad}))
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(document | {"batch_hard_timeout_s": bad}, schema)
