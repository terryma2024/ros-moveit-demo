"""R3-a review fix 8: the Teacher execution policy hash is part of the controlled identity, so runs under different policies (schema 5 and
schema 6, or schema 6 with different campaign seeds) never merge silently.

A schema 6 freeze must be pinned by the contract's identity; an older freeze is compared only when the identity names a policy."""

import json

import pytest

from so101_demo.act import collection_qualification_recompute as recompute
from so101_demo.act.collection_merge import comparable_identity
from so101_demo.act.parallel_collection_contracts import TEACHER_POLICY_IDENTITY_KEY, validate_controlled_identity

SHA5, SHA6, SHA6_OTHER_SEED = "5" * 64, "6" * 64, "7" * 64


def contract(**extra):
    return dict(controlled_identity=dict(runtime_config_sha256="1" * 64, collection_config_sha256="2" * 64,
                                         contact_policy_fingerprint="3" * 64, **extra), scene_manifest=dict(sha256="4" * 64))


def frozen_set(tmp_path, *, policy_sha=None, diversity=False):
    proposal = tmp_path / "contact-proposal.json"
    proposal.write_text(json.dumps(dict(policy_fingerprint="3" * 64)))
    document = dict(roles=dict(runtime_config=dict(sha256="1" * 64), collection_config=dict(sha256="2" * 64),
                               contact_proposal=dict(path="contact-proposal.json")), scene_manifest=dict(sha256="4" * 64))
    if policy_sha is not None:
        document["teacher_execution_policy"] = dict(policy_sha256=policy_sha, values=dict(schema_version=6 if diversity else 5,
                                                    **({"diversity": {"campaign_seed": 1}} if diversity else {})))
    return document, tmp_path / "inputs-manifest.json"


def problems(tmp_path, frozen_kwargs, identity_extra):
    frozen, manifest = frozen_set(tmp_path, **frozen_kwargs)
    return recompute.frozen_identity_problems(frozen, manifest, contract(**identity_extra))


def test_the_identity_key_name():
    assert TEACHER_POLICY_IDENTITY_KEY == "teacher_execution_policy_sha256"


def test_a_schema_6_freeze_must_be_pinned_by_the_identity(tmp_path):
    assert problems(tmp_path, dict(policy_sha=SHA6, diversity=True), {}) == [TEACHER_POLICY_IDENTITY_KEY]
    assert problems(tmp_path, dict(policy_sha=SHA6, diversity=True), {TEACHER_POLICY_IDENTITY_KEY: SHA6}) == []


def test_another_campaign_seed_is_another_policy_hash_and_does_not_match(tmp_path):
    assert problems(tmp_path, dict(policy_sha=SHA6_OTHER_SEED, diversity=True), {TEACHER_POLICY_IDENTITY_KEY: SHA6}) == [TEACHER_POLICY_IDENTITY_KEY]


def test_a_schema_5_freeze_does_not_match_a_schema_6_identity(tmp_path):
    assert problems(tmp_path, dict(policy_sha=SHA5), {TEACHER_POLICY_IDENTITY_KEY: SHA6}) == [TEACHER_POLICY_IDENTITY_KEY]


def test_an_older_freeze_is_unchanged_when_the_identity_names_no_policy_and_matches_when_it_names_its_own(tmp_path):
    assert problems(tmp_path, dict(policy_sha=SHA5), {}) == []
    assert problems(tmp_path, {}, {}) == []                                   # a frozen set the tests build without a policy binding
    assert problems(tmp_path, dict(policy_sha=SHA5), {TEACHER_POLICY_IDENTITY_KEY: SHA5}) == []


def test_the_identity_key_is_a_sha256_and_optional():
    from test_parallel_collection_contracts import identity as make_identity

    identity = make_identity()
    assert validate_controlled_identity(identity) == identity
    assert validate_controlled_identity({**identity, TEACHER_POLICY_IDENTITY_KEY: SHA6})[TEACHER_POLICY_IDENTITY_KEY] == SHA6
    for bad in ("abc", "G" * 64, 5, None):
        with pytest.raises(ValueError):
            validate_controlled_identity({**identity, TEACHER_POLICY_IDENTITY_KEY: bad})


def test_the_merge_compares_the_policy_hash_between_sources():
    base = {"runtime_config_sha256": "1" * 64, "gpu_uuid": "GPU-x"}
    five = comparable_identity({"controlled_identity": dict(base)})
    six = comparable_identity({"controlled_identity": {**base, TEACHER_POLICY_IDENTITY_KEY: SHA6}})
    other_seed = comparable_identity({"controlled_identity": {**base, TEACHER_POLICY_IDENTITY_KEY: SHA6_OTHER_SEED}})
    assert len({json.dumps(item, sort_keys=True) for item in (five, six, other_seed)}) == 3
    assert "gpu_uuid" not in six
