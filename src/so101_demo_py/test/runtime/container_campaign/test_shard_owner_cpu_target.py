"""The shard owner offers its exact registered container, and only that, to the CPU weight controller."""

import pytest

from so101_demo.runtime.container_campaign import shard_owner as module
from test_shard_owner import fixture


def test_no_target_before_the_container_is_bound(tmp_path):
    owner, _, _, _ = fixture(tmp_path, (0, ''))
    assert owner.cpu_target() is None


def test_target_names_the_registered_container_and_verifies_its_identity_before_use(tmp_path, monkeypatch):
    owner, _, _, _ = fixture(tmp_path, (0, ''))
    key = object()
    owner.owner, owner.original_cpu_shares = type('Key', (), {'container_id': 'c' * 64})(), 512
    registered = owner.owner
    seen = []
    monkeypatch.setattr(owner, 'inspect', lambda container_id: seen.append(container_id) or {'doc': True})
    monkeypatch.setattr(module, 'container_key_from_inspect', lambda document, launch_generation: registered)
    target = owner.cpu_target()
    assert target.container_id == 'c' * 64 and target.original_cpu_shares == 512 and target.docker is owner.docker
    target.verify()
    assert seen == ['c' * 64]
    monkeypatch.setattr(module, 'container_key_from_inspect', lambda document, launch_generation: key)
    with pytest.raises(ValueError, match='SHARD_CONTAINER_IDENTITY_CHANGED'):
        target.verify()
