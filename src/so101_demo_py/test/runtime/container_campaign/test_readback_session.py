"""One verifier session per task readback: the same result as before, and the same refusals, with the repeated audit skipped.

`verify_container_task_registration` used to open a verifier session inside `ActCollectionResultVerifier.verify` and close it
before its own parity call of `verify_episode_physical_audit`, so that call recomputed what the session had just computed. It now
joins one session for both. Fixtures here are the synthetic sealed episodes of `test_task_commit_readback` (real producers, a
controlled QC recomputation); nothing is read from a host path.
"""

import contextlib
import json

import pytest

from test_task_commit_readback import INVALID, build_task, verify
from so101_demo.act import qc_session, result_store
from so101_demo.act.qc_session import qc_session as session_scope, session_memo


def old_session_scope(monkeypatch):
    """The readback as it was: no enclosing session, so the verifier opens its own and closes it before the parity call."""
    monkeypatch.setattr(result_store, 'joined_session', contextlib.nullcontext)


def chain(error):
    parts = []
    while error is not None:
        parts.append(f'{type(error).__name__}:{error}')
        error = error.__cause__
    return parts


def episode_file(world, name):
    return world.location/'episode'/name


def test_the_proof_is_identical_with_one_session_and_with_the_old_split_sessions(tmp_path, monkeypatch):
    world = build_task(tmp_path, monkeypatch)
    new = verify(world)
    old_session_scope(monkeypatch)
    old = verify(world)
    assert new == old and json.dumps(new, sort_keys=True) == json.dumps(old, sort_keys=True)
    assert new['kind'] == 'ACT_CONTAINER_TASK_READBACK' and new['status'] == 'PASS'


# The synthetic episode has no rows (every .jsonl is empty), so a "removed event" is the events file itself, a "changed sample" is a
# sample row that the sealed bytes do not contain, and the truncation hits the audit manifest. Each must be refused by both paths.

def tamper_remove_the_events(path):
    path.unlink()


def tamper_add_a_sample(path):
    path.write_text(json.dumps(dict(sample=1)) + '\n')


def tamper_truncate(path):
    path.write_bytes(path.read_bytes()[:path.stat().st_size // 2])


@pytest.mark.parametrize('tamper, name', [(tamper_remove_the_events, 'audit/events.jsonl'),
                                          (tamper_add_a_sample, 'records.jsonl'),
                                          (tamper_truncate, 'audit/audit-manifest.json')])
def test_a_tampered_episode_is_refused_with_the_same_chain_by_both_paths(tmp_path, monkeypatch, tamper, name):
    world = build_task(tmp_path, monkeypatch)
    path = episode_file(world, name)
    assert path.is_file(), name
    tamper(path)
    with pytest.raises(ValueError, match=INVALID) as new:
        verify(world)
    old_session_scope(monkeypatch)
    with pytest.raises(ValueError, match=INVALID) as old:
        verify(world)
    assert chain(new.value) == chain(old.value)


def test_the_verifier_and_the_parity_audit_share_one_session(tmp_path, monkeypatch):
    world = build_task(tmp_path, monkeypatch)
    seen = {}
    real = result_store.ActCollectionResultVerifier.verify

    def verifying(self, *args, **kwargs):
        seen['verifier'] = qc_session.active()
        return real(self, *args, **kwargs)

    def parity(verdict, episode_root, scope, *, trust_independent_qc_memo):
        seen['parity'] = qc_session.active()

    monkeypatch.setattr(result_store.ActCollectionResultVerifier, 'verify', verifying)
    monkeypatch.setattr(result_store, '_parity_physical_audit', parity)
    verify(world)
    assert seen['verifier'] is not None and seen['verifier'] is seen['parity']
    assert qc_session.active() is None


def test_a_caller_s_session_is_joined_not_replaced(tmp_path, monkeypatch):
    world = build_task(tmp_path, monkeypatch)
    with session_scope() as outer:
        verify(world)
        assert qc_session.active() is outer
    assert outer.misses > 0


def parity_fixture(tmp_path, status):
    episode = tmp_path/'episode'
    episode.mkdir()
    (episode/'seal.json').write_text(json.dumps(dict(status=status)))
    (episode/'audit').mkdir()
    (episode/'audit'/'audit-manifest.json').write_text('{}')
    scope = tmp_path/'scope.json'
    scope.write_text('{}')
    return episode, scope


def counting_audit(monkeypatch, *, fail=False):
    from so101_demo.act import episode_qc
    calls = []

    @session_memo(lambda episode_root, audit_manifest, scope: (str(episode_root), str(audit_manifest), str(scope)))
    def audit(episode_root, audit_manifest, scope):
        calls.append(episode_root)
        if fail:
            raise ValueError('ORIGINAL_AUDIT_INVALID')

    monkeypatch.setattr(episode_qc, 'verify_episode_physical_audit', audit)
    return audit, calls


VALID = dict(act_data_status='VALID', episode_seal_sha256='a'*64)


def test_the_parity_audit_is_a_hit_after_the_session_ran_it_and_runs_without_one(tmp_path, monkeypatch):
    episode, scope = parity_fixture(tmp_path, 'PASSED')
    audit, calls = counting_audit(monkeypatch)
    with session_scope():
        audit(episode, episode/'audit'/'audit-manifest.json', scope)
        result_store._parity_physical_audit(VALID, episode, scope, trust_independent_qc_memo=False)
    assert len(calls) == 1
    result_store._parity_physical_audit(VALID, episode, scope, trust_independent_qc_memo=False)
    assert len(calls) == 2


@pytest.mark.parametrize('verdict, status, trust', [(dict(VALID, act_data_status='INVALID'), 'PASSED', False),
                                                    (dict(VALID, episode_seal_sha256=None), 'PASSED', False),
                                                    (VALID, 'FAILED', False), (VALID, 'PASSED', True)])
def test_the_parity_audit_is_still_skipped_exactly_where_it_was(tmp_path, monkeypatch, verdict, status, trust):
    episode, scope = parity_fixture(tmp_path, status)
    _, calls = counting_audit(monkeypatch)
    result_store._parity_physical_audit(verdict, episode, scope, trust_independent_qc_memo=trust)
    assert calls == []


def test_a_failing_audit_is_not_remembered_and_raises_every_time(tmp_path, monkeypatch):
    episode, scope = parity_fixture(tmp_path, 'PASSED')
    audit, calls = counting_audit(monkeypatch, fail=True)
    with session_scope():
        for _ in range(2):
            with pytest.raises(ValueError, match='ORIGINAL_AUDIT_INVALID'):
                result_store._parity_physical_audit(VALID, episode, scope, trust_independent_qc_memo=False)
    assert len(calls) == 2


def test_a_file_changed_after_the_session_ran_the_audit_is_audited_again(tmp_path, monkeypatch):
    from so101_demo.act.qc_session import tree_signature, file_signature
    episode, scope = parity_fixture(tmp_path, 'PASSED')
    calls = []

    @session_memo(lambda episode_root, audit_manifest, scope: (str(episode_root), tree_signature(episode_root), file_signature(scope)))
    def audit(episode_root, audit_manifest, scope):
        calls.append(1)

    from so101_demo.act import episode_qc
    monkeypatch.setattr(episode_qc, 'verify_episode_physical_audit', audit)
    with session_scope():
        audit(episode, episode/'audit'/'audit-manifest.json', scope)
        (episode/'audit'/'extra.jsonl').write_text('{}')
        result_store._parity_physical_audit(VALID, episode, scope, trust_independent_qc_memo=False)
    assert len(calls) == 2
