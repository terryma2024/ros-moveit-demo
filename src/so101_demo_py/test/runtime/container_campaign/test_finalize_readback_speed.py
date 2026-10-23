"""Finalize readback speed-ups (to-do 2b/3): each round read once by the intermediate passes, QC memo trust only where approved,
the larger end-of-campaign worker default. Synthetic evidence only."""

import json
import os

import pytest

from processed_fixture import echo_reader
from so101_demo.runtime.container_campaign import processing_verifier, readback_pool
from test_owner_retry import drive, retry_world
from test_processing_rounds import recorded_round

GIB = 1024**3


def counting_reader(calls):
    def read(output_dir, **kwargs):
        calls.append((os.path.basename(str(output_dir)), kwargs.get('trust_memo', False)))
        kwargs.pop('trust_memo', None)
        return echo_reader(output_dir, **kwargs)
    return read


def rounds_of(tmp_path):
    return [recorded_round(tmp_path, 0, dict(a=(1, 'INVALID'), b=(1, 'VALID'))), recorded_round(tmp_path, 1, dict(a=(2, 'VALID')))]


def verify(tmp_path, rounds, reader, **kwargs):
    return processing_verifier.verify_rounds(tmp_path / 'run', rounds, ['a', 'b'], readback_workers=1, processed_reader=reader, **kwargs)


def test_trust_memo_reaches_the_readback_only_when_asked(tmp_path):
    rounds = rounds_of(tmp_path)
    calls = []
    verify(tmp_path, rounds, counting_reader(calls))
    assert {flag for _, flag in calls} == {False}
    calls.clear()
    verify(tmp_path, rounds, counting_reader(calls), trust_memo=True)
    assert {flag for _, flag in calls} == {True}


def test_an_intermediate_pass_reads_each_round_once(tmp_path):
    rounds = rounds_of(tmp_path)
    calls, cache = [], {}
    reader = counting_reader(calls)
    first = verify(tmp_path, rounds[:1], reader, trust_memo=True, round_cache=cache)
    assert len(calls) == 2
    second = verify(tmp_path, rounds, reader, trust_memo=True, round_cache=cache)
    assert len(calls) == 3                    # round 0 came from the cache; only round 1's scene was read
    again = verify(tmp_path, rounds, reader, trust_memo=True, round_cache=cache)
    assert len(calls) == 3
    assert json.dumps(again, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert json.dumps(second, sort_keys=True) == json.dumps(verify(tmp_path, rounds, echo_reader), sort_keys=True)
    assert first['counts']['PROCESSED'] == 2


def test_a_cached_round_is_read_again_when_a_file_or_the_journal_changes(tmp_path):
    rounds = rounds_of(tmp_path)
    calls, cache = [], {}
    reader = counting_reader(calls)
    verify(tmp_path, rounds, reader, trust_memo=True, round_cache=cache)
    assert len(calls) == 3
    target = next(tmp_path.rglob('a-lease-1-proc-1'))
    victim = next(path for path in target.rglob('*') if path.is_file())
    stat = victim.stat()
    os.utime(victim, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))       # same bytes, new mtime: a different signature
    verify(tmp_path, rounds, reader, trust_memo=True, round_cache=cache)
    assert len(calls) == 5                    # round 0 was read again (both scenes); round 1 was still cached
    journal = tmp_path / 'run' / 'host' / 'retry-1' / 'processing-journal.jsonl'
    journal.write_text(journal.read_text() + '\n')
    with pytest.raises(ValueError, match='PROCESSING_JOURNAL_INVALID'):
        verify(tmp_path, rounds, reader, trust_memo=True, round_cache=cache)


def test_the_cache_is_never_used_by_an_untrusting_pass(tmp_path):
    rounds = rounds_of(tmp_path)
    calls, cache = [], {}
    reader = counting_reader(calls)
    verify(tmp_path, rounds, reader, trust_memo=True, round_cache=cache)
    calls.clear()
    verify(tmp_path, rounds, reader, round_cache=cache)
    assert len(calls) == 3 and {flag for _, flag in calls} == {False}


def test_the_owner_chooses_candidates_with_provisional_passes_and_writes_the_result_from_one_full_pass(tmp_path, monkeypatch):
    phase = retry_world(tmp_path, monkeypatch, outcomes=('INVALID', 'INVALID', 'VALID'))
    calls = []
    inner = phase.owner.verifier.verify_rounds

    def provisional(rounds, ids):
        calls.append(('provisional', len(rounds)))
        return processing_verifier.verify_rounds(phase.owner.root, rounds, ids, readback_workers=1, trust_memo=True,
                                                 processed_reader=lambda output, **kwargs: phase.outputs[str(output)])

    def full(rounds, ids):
        calls.append(('full', len(rounds)))
        return inner(rounds, ids)
    phase.owner.verifier.verify_rounds_provisional = provisional
    phase.owner.verifier.verify_rounds = full
    result = drive(phase)
    assert calls == [('provisional', 1), ('provisional', 2), ('provisional', 3), ('full', 3)]
    assert result['retry']['rounds_run'] == 2 and result['retry']['recovered'] == 1
    index = json.loads((phase.owner.root / 'collection-index.json').read_text())
    assert len(index['committed_episodes']) == 2


def test_a_verifier_without_the_provisional_pass_is_called_as_before(tmp_path, monkeypatch):
    phase = retry_world(tmp_path, monkeypatch)
    calls = []
    inner = phase.owner.verifier.verify_rounds
    phase.owner.verifier.verify_rounds = lambda rounds, ids: (calls.append(len(rounds)), inner(rounds, ids))[1]
    drive(phase)
    assert calls == [1, 2]


def test_the_end_of_campaign_default_is_larger_than_the_during_campaign_default():
    assert readback_pool.default_readback_workers(available_bytes=64 * GIB, cpu_count=32) == 4
    assert readback_pool.default_readback_workers(available_bytes=64 * GIB, cpu_count=32, finalize=True) == 16
    assert readback_pool.default_readback_workers(available_bytes=64 * GIB, cpu_count=64, finalize=True) == 16
    assert readback_pool.default_readback_workers(available_bytes=8 * GIB, cpu_count=32, finalize=True) == 2     # memory still binds
    assert readback_pool.default_readback_workers(available_bytes=64 * GIB, cpu_count=8, finalize=True) == 4     # so do the CPUs
    assert readback_pool.resolve_readback_workers(None, finalize=True) >= 1
    assert readback_pool.resolve_readback_workers(7, finalize=True) == 7


def test_the_verifier_uses_an_explicit_count_and_otherwise_the_finalize_default(tmp_path, monkeypatch):
    from so101_demo.runtime.container_campaign.result_verifier import ContainerWaveResultVerifier

    seen = []
    monkeypatch.setattr(readback_pool, 'default_readback_workers', lambda **kwargs: (seen.append(kwargs), 3)[1])
    verifier = ContainerWaveResultVerifier.__new__(ContainerWaveResultVerifier)
    verifier.finalize_readback_workers = None
    assert verifier._finalize_workers() == 3 and seen == [dict(finalize=True)]
    verifier.finalize_readback_workers = 5
    assert verifier._finalize_workers() == 5
