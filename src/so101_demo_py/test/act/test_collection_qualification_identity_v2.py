"""Identity version 2: the GPU is the environment of a qualification run, not part of its controlled identity (multi-host design Q3)."""

import copy
import json

import pytest

from collection_qualification_world import GPU, build_world, install_controlled_qc
from so101_demo.act import collection_qualification_recompute as recompute
from so101_demo.act.parallel_collection_contracts import validate_controlled_identity
from so101_demo.act.parallel_qualification_verifier import (
    build_collection_qualification_report, verify_collection_qualification,
)
from test_parallel_qualification_report import controlled_frozen_reader

OTHER_GPU = 'GPU-00000000-0000-0000-0000-000000000000'


@pytest.fixture
def v2(tmp_path, monkeypatch):
    install_controlled_qc(monkeypatch)
    monkeypatch.setattr(recompute, 'read_frozen_inputs', controlled_frozen_reader)
    (tmp_path / 'world').mkdir()
    return build_world(tmp_path / 'world', identity_version=2)


def verify(world, **kwargs):
    kwargs.setdefault('registered_root', world.root)
    kwargs.setdefault('expected_identity', copy.deepcopy(world.contract['controlled_identity']))
    return verify_collection_qualification(world.report_path, **kwargs)


def test_a_version_2_identity_has_no_gpu_and_a_version_1_identity_still_validates(v2):
    identity = v2.contract['controlled_identity']
    assert 'gpu_uuid' not in identity
    validate_controlled_identity(identity)
    validate_controlled_identity(dict(identity, gpu_uuid=GPU))
    with pytest.raises(ValueError):
        validate_controlled_identity(dict(identity, gpu_uuid='not-a-gpu'))
    with pytest.raises(ValueError):
        validate_controlled_identity(dict(identity, extra=1))


def test_the_report_of_a_version_2_run_records_the_gpu_as_its_environment(v2):
    path = build_collection_qualification_report(v2.run, contract=v2.contract_path)
    report = json.loads(path.read_bytes())
    assert report['status'] == 'QUALIFIED' and report['reasons'] == []
    assert report['environment'] == {'gpu_uuid': GPU, 'gpu_model': None}
    assert 'gpu_uuid' not in report['controlled_identity']
    proof = verify(v2)
    assert proof['status'] == 'PASS' and proof['environment'] == {'gpu_uuid': GPU, 'gpu_model': None}


def test_a_version_1_report_has_no_environment_and_a_version_2_report_must_have_one(v2):
    build_collection_qualification_report(v2.run, contract=v2.contract_path)
    document = json.loads(v2.report_path.read_bytes())
    del document['environment']
    v2.report_path.write_bytes(recompute.canonical(document))
    with pytest.raises(ValueError, match='COLLECTION_QUALIFICATION_REPORT_INVALID'):
        verify(v2)


def test_another_host_with_another_gpu_has_the_same_identity_but_its_own_environment(v2):
    build_collection_qualification_report(v2.run, contract=v2.contract_path)
    assert verify(v2, expected_identity=copy.deepcopy(v2.contract['controlled_identity']))['environment']['gpu_uuid'] == GPU
    # an identity naming a GPU is a version 1 identity: it is not the version 2 identity and is refused
    with pytest.raises(ValueError, match='COLLECTION_QUALIFICATION_IDENTITY_MISMATCH'):
        verify(v2, expected_identity=dict(v2.contract['controlled_identity'], gpu_uuid=OTHER_GPU))


def test_a_shard_spec_naming_another_gpu_than_the_config_is_not_qualified(v2):
    spec = next(v2.run.glob('shard-wave-0-*-g1.json'))
    document = json.loads(spec.read_bytes())
    document['gpu_uuid'] = OTHER_GPU
    spec.write_bytes(recompute.canonical(document))
    path = build_collection_qualification_report(v2.run, contract=v2.contract_path)
    report = json.loads(path.read_bytes())
    assert report['status'] == 'NOT_QUALIFIED' and 'IDENTITY_MISMATCH:gpu_uuid' in report['reasons']
