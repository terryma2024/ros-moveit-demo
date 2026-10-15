import hashlib
import json

import pytest

from test_config_identity import campaign_fixture, config_module, write_config


def test_post_recording_cpu_shares_is_optional_validated_and_hashed(tmp_path):
    document = campaign_fixture(tmp_path)
    plain = write_config(tmp_path, document)
    plain_hash = hashlib.sha256(plain.read_bytes()).hexdigest()
    assert "post_recording_cpu_shares" not in config_module().load_campaign_config(plain)
    for good in (2, 64, 1024):
        limited = write_config(tmp_path, document | {"post_recording_cpu_shares": good})
        assert config_module().load_campaign_config(limited)["post_recording_cpu_shares"] == good
        assert hashlib.sha256(limited.read_bytes()).hexdigest() != plain_hash
    for bad in (0, 1, 1025, -1, True, 64.0, "64", None):
        with pytest.raises(ValueError, match="CAMPAIGN_CONFIG_INVALID"):
            config_module().load_campaign_config(write_config(tmp_path, document | {"post_recording_cpu_shares": bad}))


def test_published_campaign_schema_accepts_only_valid_post_recording_cpu_shares(tmp_path):
    import jsonschema
    from paths import PACKAGE_ROOT
    schema = json.loads((PACKAGE_ROOT / "config/act/campaign-runtime-schema.json").read_text())
    document = campaign_fixture(tmp_path)
    jsonschema.validate(document | {"post_recording_cpu_shares": 64}, schema)
    for bad in (1, 1025, True, "64", 64.5):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(document | {"post_recording_cpu_shares": bad}, schema)
