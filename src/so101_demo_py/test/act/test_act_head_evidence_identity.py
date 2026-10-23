"""Bounded copies and byte limits remain enforced after online codec removal."""
import pytest
from so101_demo.act.head_evidence_identity import bounded_payload, canonical_bytes


def test_bounded_payload_owns_nested_originals_before_caller_changes():
    original = {'operation': 'ORIGINAL', 'identity': {'pid': 12}, 'samples': [1, 2]}
    copy = bounded_payload(original)
    original['identity']['pid'] = 99
    original['samples'][0] = 3
    assert copy == {'operation': 'ORIGINAL', 'identity': {'pid': 12}, 'samples': [1, 2]}


@pytest.mark.parametrize('payload', [
    {'huge': 'x'*2_000_000}, {'escape': '\x7f'*11000}, {'nan': float('nan')},
    {'infinity': float('inf')}, {'bytes': b'x'}, {'integer': 2**64}, {1: 'non-string'},
])
def test_unbounded_or_non_json_evidence_cannot_enter_serialization(payload):
    with pytest.raises(ValueError):
        bounded_payload(payload)


def test_escaped_unicode_bounds_agree_with_canonical_bytes():
    payload = {'text': '\x7f'*1000 + '💡'*1000, 'rows': [True, None, -0.]}
    assert len(canonical_bytes(bounded_payload(payload))) <= 65536
