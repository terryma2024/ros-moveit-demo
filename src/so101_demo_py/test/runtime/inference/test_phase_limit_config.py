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
