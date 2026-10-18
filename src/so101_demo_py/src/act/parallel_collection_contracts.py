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
#: Human decision 2026-10-15: short eight-shard DEBUG runs may use the functional contract. The sets are closed and are not
#: evidence: a functional run has no gate contract, writes no qualification report and is refused by every qualification reader.
FUNCTIONAL_WORKER_COUNTS = (1,2,8)
FUNCTIONAL_SCENE_COUNTS = (8,16)
QUALITY_RULE_KEYS = frozenset({'schema_version','kind','name','episode_rule','population','pass'})
#: The populations a rule file may name. `ALL_FROZEN_SCENES` is every scene of the frozen list: FAILED, INVALID, no-pose and
#: unevidenced scenes stay in the denominator. `QC_VALID_EPISODES` (human decision D2, 2026-10-14) is the scenes whose data is
#: VALID with QC PASS; the scenes it leaves out are listed with a closed reason in the report, never skipped silently. Which gate
#: may name which population is fixed here, not in the rule file: a rate always runs over every frozen scene.
QUALITY_POPULATIONS = frozenset({'ALL_FROZEN_SCENES', 'QC_VALID_EPISODES'})
EPISODE_GATES = frozenset({'recorder_lossless', 'frame_continuity'})
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


#: Present in the identity of a campaign that names its camera rig (sha256 of the rig profile, `act.rig_profile`); absent for every
#: identity written before rig profiles existed, which is rig v1.
RIG_IDENTITY_KEY = 'rig_profile_sha256'


def validate_controlled_identity(identity):
    _require(type(identity) is dict and set(identity) - {RIG_IDENTITY_KEY} == IDENTITY_KEYS)
    for name in (IDENTITY_KEYS | ({RIG_IDENTITY_KEY} & set(identity))) - {'image_source_install','gpu_uuid'}:
        _require(type(identity[name]) is str and re.fullmatch(r'[0-9a-f]{64}',identity[name]) is not None)
    images = identity['image_source_install']
    _require(type(images) is dict and set(images) == {'inference','shard'})
    for image in images.values():
        _image(image)
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
        _require(type(document['worker_count']) is int and document['worker_count'] in FUNCTIONAL_WORKER_COUNTS)
        validate_controlled_identity(document['controlled_identity'])
        _require(len(scene_ids(document['scene_manifest'])) in FUNCTIONAL_SCENE_COUNTS)
        return copy.deepcopy(document)
    except (OSError,ValueError,TypeError,KeyError,UnicodeError) as error:
        raise ValueError('FUNCTIONAL_COLLECTION_CONTRACT_INVALID') from error


def validate_run_contract(document):
    """`(plane, contract)` of a qualification-mode run document: 'gate' (W8, 40 scenes) or 'functional' (debug).

    The plane follows the document's own kind, never the worker count: eight workers may carry either contract."""
    kind = document.get('kind') if type(document) is dict else None
    if kind == 'ACT_PARALLEL_COLLECTION_GATE':
        return 'gate',validate_qualification_contract(document)
    if kind == 'ACT_COLLECTION_FUNCTIONAL_RUN':
        return 'functional',validate_functional_contract(document)
    raise ValueError('COLLECTION_RUN_CONTRACT_KIND_INVALID')


def quality_episode_rule(name):
    """The per-episode rule version the code implements for gate `name`; a rule file may only name this one."""
    from so101_demo.act import episode_qc, topic_loss
    from so101_demo.parallel_batch import dynamic_manifest

    return {'recorder_lossless': topic_loss.RULE_VERSION, 'frame_continuity': episode_qc.QC_RULE_VERSION,
            'qc_valid_rate': episode_qc.QC_RULE_VERSION,
            'teacher_physical_success_rate': dynamic_manifest.RULE_VERSION}[name]


def validate_quality_rule(name, document):
    """One gate's rule file: a closed document that names the code's own episode rule and a complete, integer pass value.

    The code never supplies a count. A missing, valueless, open or unknown-keyed document is refused, so the gate contract cannot
    be admitted with a rule that would later decide nothing.
    """
    try:
        _require(name in QUALITY_NAMES and type(document) is dict and set(document) == QUALITY_RULE_KEYS)
        _require(type(document['schema_version']) is int and document['schema_version'] == 1
                 and document['kind'] == 'ACT_COLLECTION_QUALITY_RULE' and document['name'] == name)
        _require(document['episode_rule'] == quality_episode_rule(name))
        _require(document['population'] in QUALITY_POPULATIONS)
        _require(name in EPISODE_GATES or document['population'] == 'ALL_FROZEN_SCENES')
        rule = document['pass']
        _require(type(rule) is dict and rule.get('kind') in ('EVERY','AT_LEAST'))
        if rule['kind'] == 'EVERY':
            _require(set(rule) == {'kind'})
        else:
            _require(set(rule) == {'kind','numerator','denominator'}
                     and type(rule['numerator']) is int and type(rule['denominator']) is int
                     and 0 < rule['numerator'] <= rule['denominator'])
        # every valid episode must satisfy a per-episode gate: a count over them would loosen the judgement
        _require(document['population'] != 'QC_VALID_EPISODES' or rule['kind'] == 'EVERY')
        return copy.deepcopy(document)
    except (ValueError,TypeError,KeyError,ImportError) as error:
        raise ValueError('QUALITY_RULE_INVALID') from error


def validate_qualification_contract(document, *, check_rules=True):
    """The closed W8 gate contract. `check_rules=False` leaves each rule file's content to `validate_quality_rule`, called by
    the report recomputation, which turns an undefined rule into a named reason instead of an unreadable contract."""
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
        for name,reference in rules.items():
            if check_rules:
                validate_quality_rule(name,read_document(validate_file_ref(reference)))
            validate_file_ref(reference)
        return copy.deepcopy(document)
    except (OSError,ValueError,TypeError,KeyError,UnicodeError) as error:
        raise ValueError('PARALLEL_QUALIFICATION_CONTRACT_INVALID') from error
