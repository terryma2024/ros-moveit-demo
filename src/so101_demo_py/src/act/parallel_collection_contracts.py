"""Closed functional and independent-W8 input contracts, with original refs.

This validates pre-run inputs and their disjoint scene lists. Rule references
are not passing quality results: the report verifier must recompute the current
business criteria from every original case, including FAILED/INVALID outcomes.
"""

import copy
import json
import re

from so101_demo.runtime.inference.config import _image, _open_regular, validate_file_ref
from so101_demo.runtime.parallel_ipc.frames import _pairs
from so101_demo.parallel_batch.contracts.common import _require_id


QUALITY_NAMES = frozenset({'recorder_lossless','frame_continuity','qc_valid_rate',
                           'teacher_physical_success_rate'})
IDENTITY_KEYS = frozenset({'source_sha256','runtime_config_sha256','collection_config_sha256',
                          'contact_policy_fingerprint','image_source_install','gpu_uuid'})
FUNCTIONAL_KEYS = frozenset({'schema_version','kind','run_id','worker_count','scene_manifest',
                            'controlled_identity'})
QUALIFICATION_KEYS = frozenset({'schema_version','kind','qualification_run_id','worker_count',
    'scene_manifest','functional_manifest','formal_split_manifest','controlled_identity','quality_rules'})


def _require(condition):
    if not condition:
        raise ValueError('contract shape')


def read_document(path, *, limit=16*1024*1024):
    with _open_regular(path) as stream:
        raw = stream.read(limit+1)
    _require(len(raw) <= limit)
    value = json.loads(raw.decode('utf-8'),object_pairs_hook=_pairs,
                       parse_constant=lambda name: (_ for _ in ()).throw(ValueError(name)))
    _require(type(value) is dict)
    return value


def validate_controlled_identity(identity):
    _require(type(identity) is dict and set(identity) == IDENTITY_KEYS)
    for name in IDENTITY_KEYS - {'image_source_install','gpu_uuid'}:
        _require(type(identity[name]) is str and re.fullmatch(r'[0-9a-f]{64}',identity[name]) is not None)
    images = identity['image_source_install']
    _require(type(images) is dict and set(images) == {'inference','shard'})
    for image in images.values():
        _image(image)
    _require(images['inference']['package_source_sha256'] == images['shard']['package_source_sha256'])
    _require(type(identity['gpu_uuid']) is str and re.fullmatch(
        r'GPU-[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}',identity['gpu_uuid']) is not None)
    return copy.deepcopy(identity)


def scene_ids(reference, *, count=None):
    path = validate_file_ref(reference)
    document = read_document(path)
    # Keep the existing scene artifact's scenarios/scene_id/split contract;
    # do not migrate its path or introduce a second scene-schema dispatcher.
    rows = document.get('scenarios')
    _require(type(rows) is list and bool(rows) and (count is None or len(rows) == count))
    ids = []
    for row in rows:
        _require(type(row) is dict and type(row.get('split')) is str and bool(row['split']))
        _require_id('scene_id',row.get('scene_id'))
        ids.append(row['scene_id'])
    _require(len(ids) == len(set(ids)))
    validate_file_ref(reference)  # reject input drift during the independent read
    return tuple(ids)


def validate_functional_contract(document):
    try:
        _require(type(document) is dict and set(document) == FUNCTIONAL_KEYS)
        _require(type(document['schema_version']) is int and document['schema_version'] == 1
                 and document['kind'] == 'ACT_COLLECTION_FUNCTIONAL_RUN')
        _require_id('run_id',document['run_id'])
        _require(type(document['worker_count']) is int and document['worker_count'] in (1,2))
        validate_controlled_identity(document['controlled_identity'])
        scene_ids(document['scene_manifest'],count=8)
        return copy.deepcopy(document)
    except (OSError,ValueError,TypeError,KeyError,UnicodeError) as error:
        raise ValueError('FUNCTIONAL_COLLECTION_CONTRACT_INVALID') from error


def validate_qualification_contract(document):
    try:
        _require(type(document) is dict and set(document) == QUALIFICATION_KEYS)
        _require(type(document['schema_version']) is int and document['schema_version'] == 1
                 and document['kind'] == 'ACT_PARALLEL_COLLECTION_GATE')
        _require_id('qualification_run_id',document['qualification_run_id'])
        _require(type(document['worker_count']) is int and document['worker_count'] == 8)
        validate_controlled_identity(document['controlled_identity'])
        qualification = set(scene_ids(document['scene_manifest'],count=40))
        functional = set(scene_ids(document['functional_manifest'],count=8))
        formal = set(scene_ids(document['formal_split_manifest']))
        _require(not qualification & functional and not qualification & formal and not functional & formal)
        rules = document['quality_rules']
        _require(type(rules) is dict and set(rules) == QUALITY_NAMES)
        for reference in rules.values():
            read_document(validate_file_ref(reference))
            validate_file_ref(reference)
        return copy.deepcopy(document)
    except (OSError,ValueError,TypeError,KeyError,UnicodeError) as error:
        raise ValueError('PARALLEL_QUALIFICATION_CONTRACT_INVALID') from error
