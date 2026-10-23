"""TEST-ONLY synthetic quality rule files for the independent W8 gate contract.

No human has decided the pass counts of the QC valid rate or of the Teacher physical success rate. The values written here are
synthetic fixtures chosen so a test can exercise one branch; they are NOT approved, NOT a qualification rule and must never be
copied into a real gate contract. Every file name carries the `test-only-not-approved` marker so a stray copy is recognisable.
"""

import hashlib
import json
from pathlib import Path

#: gate name -> the code constant its `episode_rule` must equal (resolved lazily, the same constants the code uses)
EPISODE_RULE_OF = {'recorder_lossless': 'topic_loss', 'frame_continuity': 'act_data_qc', 'qc_valid_rate': 'act_data_qc',
                   'teacher_physical_success_rate': 'teacher_endpoint'}
NAMES = tuple(EPISODE_RULE_OF)
#: TEST-ONLY synthetic pass rules per gate (not approved values)
SYNTHETIC_PASS = {'recorder_lossless': {'kind': 'EVERY'}, 'frame_continuity': {'kind': 'EVERY'},
                  'qc_valid_rate': {'kind': 'AT_LEAST', 'numerator': 1, 'denominator': 2},
                  'teacher_physical_success_rate': {'kind': 'AT_LEAST', 'numerator': 1, 'denominator': 2}}


def synthetic_rule(name, **changes):
    """One TEST-ONLY rule document for gate `name`; `changes` replace top-level fields."""
    document = {'schema_version': 1, 'kind': 'ACT_COLLECTION_QUALITY_RULE', 'name': name,
                'episode_rule': EPISODE_RULE_OF[name], 'population': 'ALL_FROZEN_SCENES',
                'pass': dict(SYNTHETIC_PASS[name])}
    document.update(changes)
    return document


def write_rule(directory, name, document):
    path = Path(directory) / f'test-only-not-approved-{name}.json'
    path.write_text(json.dumps(document, sort_keys=True))
    return dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def write_synthetic_rules(directory, **per_name):
    """The four TEST-ONLY rule files of `directory` as contract refs; `per_name[name]` is a document replacing the default."""
    return {name: write_rule(directory, name, per_name.get(name, synthetic_rule(name))) for name in NAMES}


#: The pass rules the human decided on 2026-10-14 (D1 "Teacher >=38/40, QC >=34/40", D2 "only over valid episodes"): these ARE the
#: real values, unlike SYNTHETIC_PASS. The two rates are over all 40 frozen scenes; lossless and continuity are over the
#: episodes whose data is VALID with QC PASS, and every such episode must satisfy them.
DECIDED = {'recorder_lossless': ('QC_VALID_EPISODES', {'kind': 'EVERY'}),
           'frame_continuity': ('QC_VALID_EPISODES', {'kind': 'EVERY'}),
           'qc_valid_rate': ('ALL_FROZEN_SCENES', {'kind': 'AT_LEAST', 'numerator': 34, 'denominator': 40}),
           'teacher_physical_success_rate': ('ALL_FROZEN_SCENES', {'kind': 'AT_LEAST', 'numerator': 38, 'denominator': 40})}


def decided_rule(name, **changes):
    population, rule = DECIDED[name]
    return synthetic_rule(name, **{'population': population, 'pass': dict(rule), **changes})


def write_decided_rules(directory, **per_name):
    return {name: write_rule(directory, name, per_name.get(name, decided_rule(name))) for name in NAMES}
